"""OpenCV baseline: pixel and colour differences after lighting normalisation.

Fast and needs no model, but sensitive to shadows, lighting and small camera moves.
That weakness is the reason DINOv2 exists in this project; evaluate.py measures it.
"""
from __future__ import annotations

import cv2
import numpy as np

DIFF_THRESHOLD = 38      # 0-255 combined difference that counts as "changed"
MIN_BLOB_FRAC = 0.002    # ignore changed blobs smaller than this share of the image


def _normalise(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.GaussianBlur(cv2.merge([l, a, b]), (7, 7), 0)


def diff_map(reference: np.ndarray, capture: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Per-pixel change strength in 0-255."""
    r = _normalise(reference).astype(np.int16)
    c = _normalise(capture).astype(np.int16)
    # match mean brightness of L channel inside the valid area
    shift = int(np.median(c[..., 0][valid]) - np.median(r[..., 0][valid])) if valid.any() else 0
    c[..., 0] -= shift
    d = np.abs(r - c)
    strength = 0.5 * d[..., 0] + 1.0 * d[..., 1] + 1.0 * d[..., 2]
    strength = np.clip(strength, 0, 255).astype(np.uint8)
    strength[~valid] = 0
    return strength


def changed_mask(strength: np.ndarray) -> np.ndarray:
    m = (strength >= DIFF_THRESHOLD).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    min_px = MIN_BLOB_FRAC * m.size
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    return keep[lab]


def compare(reference: np.ndarray, capture_aligned: np.ndarray, valid: np.ndarray) -> dict:
    strength = diff_map(reference, capture_aligned, valid)
    mask = changed_mask(strength) & valid
    frac = float(mask[valid].mean()) if valid.any() else 0.0
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    largest = float(stats[1:, cv2.CC_STAT_AREA].max() / max(valid.sum(), 1)) if n > 1 else 0.0
    return {
        "method": "opencv",
        "changed_fraction": frac,
        "largest_region": largest,
        "score": float(np.clip(largest / 0.15, 0, 1)),
        "heat": strength.astype(np.float32) / 255.0,
        "mask": mask,
    }
