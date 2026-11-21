"""Water masks: which pixels in one image look like water.

Two methods:
  * rgb  - colour + smoothness rules. Catches clear/blue water (pools, ponds) and muddy
           brown floodwater. Cheap and good enough for a demo; expect false positives on
           brown roofs and dirt, which the before/after comparison mostly cancels out.
  * rgbn - NDWI = (green - NIR) / (green + NIR) > threshold, for 4-band imagery
           (e.g. Sentinel-2 or Maxar with a near-infrared band). Much more reliable.

Swap in a trained segmentation model here later; detect.py only needs a boolean mask.
"""
from __future__ import annotations

import cv2
import numpy as np

# OpenCV hue runs 0-179 (degrees / 2)
CLEAR_HUE = (85, 130)    # cyan to blue
CLEAR_MIN_VALUE = 60    # very dark blue shadows can resemble smooth water
MUDDY_HUE = (9, 30)      # tan / brown
MAX_LOCAL_STD = 10.0     # water is smooth; grass, trees, debris are not


def local_std(gray: np.ndarray, k: int = 7) -> np.ndarray:
    g = gray.astype(np.float32)
    mean = cv2.blur(g, (k, k))
    sq = cv2.blur(g * g, (k, k))
    return np.sqrt(np.maximum(sq - mean * mean, 0))


def water_mask_rgb(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    smooth = local_std(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)) < MAX_LOCAL_STD
    clear = (h >= CLEAR_HUE[0]) & (h <= CLEAR_HUE[1]) & (s >= 70) & (v >= CLEAR_MIN_VALUE)
    muddy = (h >= MUDDY_HUE[0]) & (h <= MUDDY_HUE[1]) & (s >= 40) & (s <= 190) & (v >= 50) & (v <= 210)
    return clean((clear | muddy) & smooth)


def water_mask_ndwi(rgbn: np.ndarray, threshold: float = 0.0) -> np.ndarray:
    g = rgbn[..., 1].astype(np.float32)
    nir = rgbn[..., 3].astype(np.float32)
    ndwi = (g - nir) / np.maximum(g + nir, 1e-6)
    return clean(ndwi > threshold)


def water_mask(img: np.ndarray, bands: str = "rgb") -> np.ndarray:
    if bands == "rgbn":
        return water_mask_ndwi(img)
    return water_mask_rgb(img[..., :3])


def clean(mask: np.ndarray, k: int = 3) -> np.ndarray:
    m = mask.astype(np.uint8)
    kernel = np.ones((k, k), np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
    return m > 0
