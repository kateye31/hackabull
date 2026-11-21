"""DINOv2 patch comparison.

DINOv2 turns each 14x14 patch of an image into a feature vector that describes
*what* is there (pavement, grass, a scooter) more than exact pixel colours. We
compare the reference and capture patch by patch with cosine similarity; patches
that stopped looking like the clear path are flagged. Lighting changes and small
shifts move pixels a lot but features only a little, which is why this beats the
pixel baseline on real photos.

The model (~90 MB) downloads from Hugging Face on first use.
"""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from .. import config

PATCH = 14
GRID_W, GRID_H = 32, 24          # patches across / down -> 448 x 336 input
PATCH_THRESHOLD = 0.45           # cosine *distance* that counts as a changed patch
MIN_REGION_PATCHES = 3           # changed regions smaller than this are treated as noise
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


class DinoUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _model():
    try:
        import torch
        from transformers import AutoModel
    except ImportError as e:
        raise DinoUnavailable(f"torch/transformers not installed: {e}")
    try:
        m = AutoModel.from_pretrained(config.DINO_MODEL).eval()
    except Exception as e:  # offline, no cache, etc.
        raise DinoUnavailable(f"could not load {config.DINO_MODEL}: {e}")
    return m


def available() -> bool:
    try:
        _model()
        return True
    except DinoUnavailable:
        return False


def _tensor(rgb: np.ndarray):
    import torch
    x = cv2.resize(rgb, (GRID_W * PATCH, GRID_H * PATCH), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0)


def patch_features(rgb: np.ndarray) -> np.ndarray:
    """(GRID_H, GRID_W, D) L2-normalised patch features."""
    import torch
    with torch.inference_mode():  # per call: grad mode is thread-local and Streamlit uses worker threads
        out = _model()(pixel_values=_tensor(rgb)).last_hidden_state[0, 1:]  # drop CLS token
    f = out.detach().numpy().reshape(GRID_H, GRID_W, -1)
    return f / np.linalg.norm(f, axis=-1, keepdims=True).clip(1e-6)


def compare(reference: np.ndarray, capture_aligned: np.ndarray, valid: np.ndarray) -> dict:
    fr = patch_features(reference)
    fc = patch_features(capture_aligned)
    dist = 1.0 - (fr * fc).sum(-1)                                     # (GRID_H, GRID_W)
    v = cv2.resize(valid.astype(np.float32), (GRID_W, GRID_H), interpolation=cv2.INTER_AREA) > 0.9
    patch_mask = (dist >= PATCH_THRESHOLD) & v
    # Largest connected changed region: an object is one solid region; lighting changes
    # and leftover misalignment scatter small ones. This separates them better than total area.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(patch_mask.astype(np.uint8), connectivity=8)
    largest = float(stats[1:, cv2.CC_STAT_AREA].max() / max(v.sum(), 1)) if n > 1 else 0.0
    # hide specks (1-2 patches) from the overlay and the total; they are almost always noise
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_REGION_PATCHES
    patch_mask = keep[labels]
    frac = float(patch_mask[v].mean()) if v.any() else 0.0
    h, w = reference.shape[:2]
    heat = cv2.resize(np.clip(dist / 0.8, 0, 1).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    heat[~valid] = 0
    mask = cv2.resize(patch_mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
    return {
        "method": "dinov2",
        "changed_fraction": frac,
        "largest_region": largest,
        "score": float(np.clip(largest / 0.15, 0, 1)),
        "heat": heat,
        "mask": mask & valid,
        "mean_patch_distance": float(dist[v].mean()) if v.any() else 0.0,
    }
