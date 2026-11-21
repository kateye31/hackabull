"""Line up the after image with the before image.

ORB keypoints + RANSAC fit a rotation/translation/scale transform from the after image
into the before image's pixel frame. Flooding changes a lot of the scene, but roofs,
road markings and trees usually give enough stable matches. If matching fails we fall
back to the identity (assume the images are already co-registered, as with most
georeferenced satellite tiles).
"""
from __future__ import annotations

import cv2
import numpy as np


def estimate(before_rgb: np.ndarray, after_rgb: np.ndarray, max_features: int = 4000):
    g0 = cv2.cvtColor(before_rgb, cv2.COLOR_RGB2GRAY)
    g1 = cv2.cvtColor(after_rgb, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(max_features)
    k0, d0 = orb.detectAndCompute(g0, None)
    k1, d1 = orb.detectAndCompute(g1, None)
    if d0 is None or d1 is None or len(k0) < 10 or len(k1) < 10:
        return None, 0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d0)
    if len(matches) < 10:
        return None, 0
    src = np.float32([k1[m.queryIdx].pt for m in matches])
    dst = np.float32([k0[m.trainIdx].pt for m in matches])
    m, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if m is None:
        return None, 0
    return m, int(inliers.sum())


def align(before: np.ndarray, after: np.ndarray, min_inliers: int = 25):
    """Return (after warped into the before frame, valid-pixel mask, info dict).

    Matching uses the first three bands; the warp is applied to every band, so a
    4-band (RGB + near-infrared) image keeps its NIR band lined up too.
    """
    h, w = before.shape[:2]
    if after.shape[:2] != (h, w):
        after = cv2.resize(after, (w, h), interpolation=cv2.INTER_AREA)
    m, n_in = estimate(np.ascontiguousarray(before[..., :3]), np.ascontiguousarray(after[..., :3]))
    if m is None or n_in < min_inliers:
        return after, np.ones((h, w), bool), {"method": "identity", "inliers": n_in}
    warped = cv2.warpAffine(after, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    valid = cv2.warpAffine(np.ones((h, w), np.uint8), m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    valid = cv2.erode(valid, np.ones((5, 5), np.uint8)) > 0
    angle = float(np.degrees(np.arctan2(m[1, 0], m[0, 0])))
    return warped, valid, {
        "method": "orb+ransac",
        "inliers": n_in,
        "shift_px": [round(float(m[0, 2]), 2), round(float(m[1, 2]), 2)],
        "rotation_deg": round(angle, 3),
    }
