"""DINOv2 patch comparison.

DINOv2 turns each 14x14 patch of an image into a feature vector that describes
*what* is there (pavement, grass, a scooter) more than exact pixel colours. We
compare the reference and capture patch by patch with cosine similarity; patches
that stopped looking like the clear path are flagged. The evaluation measures
whether the features are less sensitive to lighting and small shifts than pixels.

The model (~90 MB) downloads from Hugging Face on first use.
"""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from .. import config

GRID_W, GRID_H = 32, 24          # patches across / down
PATCH_THRESHOLD = 0.45           # cosine *distance* that counts as a changed patch
MIN_REGION_PATCHES = 3           # changed regions smaller than this are treated as noise
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


class DinoUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _model(model_id: str):
    try:
        from transformers import AutoModel
    except ImportError as e:
        raise DinoUnavailable(f"torch/transformers not installed: {e}")
    try:
        m = AutoModel.from_pretrained(model_id).eval()
    except Exception as e:  # offline, no cache, etc.
        raise DinoUnavailable(f"could not load {model_id}: {e}") from e
    return m


def available() -> bool:
    try:
        _model(config.DINO_MODEL)
        return True
    except DinoUnavailable:
        return False


def _tensor(rgb: np.ndarray, patch_size: int):
    import torch
    x = cv2.resize(rgb, (GRID_W * patch_size, GRID_H * patch_size), interpolation=cv2.INTER_AREA)
    x = x.astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0)


def patch_features(rgb: np.ndarray, model_id: str | None = None) -> np.ndarray:
    """L2-normalised patch features in processed-image grid order."""
    try:
        import torch
    except (ImportError, OSError) as exc:
        raise DinoUnavailable(f"could not import torch: {exc}") from exc
    model_id = model_id or config.DINO_MODEL
    model = _model(model_id)
    patch_size = getattr(model.config, "patch_size", None)
    if not isinstance(patch_size, int) or patch_size <= 0:
        raise DinoUnavailable(f"{model_id} does not expose a DINOv2 patch size")
    tensor = _tensor(rgb, patch_size)
    grid_h, grid_w = (side // patch_size for side in tensor.shape[-2:])
    with torch.inference_mode():
        tokens = model(pixel_values=tensor).last_hidden_state[0, 1:]  # drop CLS token
    if tokens.shape[0] != grid_h * grid_w:
        raise DinoUnavailable(f"{model_id} returned {tokens.shape[0]} patch tokens for a {grid_w}x{grid_h} grid")
    f = tokens.detach().cpu().numpy().reshape(grid_h, grid_w, -1)
    return f / np.linalg.norm(f, axis=-1, keepdims=True).clip(1e-6)


@lru_cache(maxsize=8)
def _reference_features(model_id: str, shape: tuple[int, ...], pixels: bytes) -> np.ndarray:
    return patch_features(np.frombuffer(pixels, dtype=np.uint8).reshape(shape), model_id)


def compare(reference: np.ndarray, capture_aligned: np.ndarray, valid: np.ndarray) -> dict:
    model_id = config.DINO_MODEL
    fr = _reference_features(model_id, reference.shape, reference.tobytes())
    fc = patch_features(capture_aligned, model_id)
    dist = np.clip(1.0 - (fr * fc).sum(-1), 0.0, 2.0)
    grid_h, grid_w = dist.shape
    v = cv2.resize(valid.astype(np.float32), (grid_w, grid_h), interpolation=cv2.INTER_AREA) > 0.9
    patch_mask = (dist >= PATCH_THRESHOLD) & v
    # Largest connected changed region: an object is one solid region; lighting changes
    # and leftover misalignment scatter small ones. This separates them better than total area.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(patch_mask.astype(np.uint8), connectivity=8)
    # hide specks (1-2 patches) from the overlay and the total; they are almost always noise
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_REGION_PATCHES
    largest = float(stats[keep, cv2.CC_STAT_AREA].max() / v.sum()) if keep.any() else 0.0
    patch_mask = keep[labels]
    frac = float(patch_mask[v].mean()) if v.any() else 0.0
    h, w = reference.shape[:2]
    heat = cv2.resize(np.clip(dist / 0.8, 0, 1).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    heat[~valid] = 0
    mask = cv2.resize(patch_mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
    return {
        "method": "dinov2",
        "model_id": model_id,
        "patch_threshold": PATCH_THRESHOLD,
        "changed_fraction": frac,
        "largest_region": largest,
        "score": float(np.clip(largest / 0.15, 0, 1)),
        "heat": heat,
        "mask": mask & valid,
        "mean_patch_distance": float(dist[v].mean()) if v.any() else 0.0,
    }
