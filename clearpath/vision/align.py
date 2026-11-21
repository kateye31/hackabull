"""Load images and line a capture up with its clear-path reference.

Photos are handheld, so the capture is never taken from exactly the same spot.
ORB keypoints + a RANSAC homography warp the capture onto the reference. The
obstruction itself won't match, but the buildings, edges and pavement around it
usually give enough points. If not, we compare unaligned and say so.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

WORK_SIDE = 640  # longest side used for comparison


def load_rgb(path: Path | str, max_side: int = WORK_SIDE) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    h, w = img.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def align(reference: np.ndarray, capture: np.ndarray, min_inliers: int = 30):
    """Return (capture warped into the reference frame, valid-pixel mask, info)."""
    h, w = reference.shape[:2]
    if capture.shape[:2] != (h, w):
        capture = cv2.resize(capture, (w, h), interpolation=cv2.INTER_AREA)
    g0 = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
    g1 = cv2.cvtColor(capture, cv2.COLOR_RGB2GRAY)
    H, info = _orb_homography(g0, g1, w, h, min_inliers)
    if H is None:
        H, ecc_info = _ecc_affine(g0, g1)
        info.update(ecc_info)
    if H is None:
        return capture, np.ones((h, w), bool), {"aligned": False, **info}

    warped = cv2.warpPerspective(capture, H, (w, h), borderValue=0)
    valid = cv2.warpPerspective(np.ones((h, w), np.uint8), H, (w, h), flags=cv2.INTER_NEAREST) > 0
    valid = cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    info.pop("reason", None)
    return warped, valid, {"aligned": True, **info}


def _orb_homography(g0, g1, w, h, min_inliers):
    orb = cv2.ORB_create(3000)
    k0, d0 = orb.detectAndCompute(g0, None)
    k1, d1 = orb.detectAndCompute(g1, None)
    if d0 is None or d1 is None or len(k0) < 10 or len(k1) < 10:
        return None, {"method": "orb", "inliers": 0, "reason": "too few features"}
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d0, k=2)
    good = [m for m, n in (p for p in matches if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < min_inliers:
        return None, {"method": "orb", "inliers": len(good), "reason": "too few matches"}
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k0[m.trainIdx].pt for m in good])
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    n_in = int(inl.sum()) if inl is not None else 0
    if H is None or n_in < min_inliers or not _sane(H, w, h):
        return None, {"method": "orb", "inliers": n_in, "reason": "no reliable transform"}
    return H, {"method": "orb", "inliers": n_in}


def _ecc_affine(g0, g1, min_corr: float = 0.6):
    """Intensity-based fallback for small handheld shifts/rotations. Robust to brightness changes."""
    s = 0.5
    h, w = g0.shape
    if min(h, w) < 2:
        return None, {"reason": "image too small for ECC"}
    a = cv2.GaussianBlur(cv2.resize(g0, None, fx=s, fy=s), (5, 5), 0).astype(np.float32)
    b = cv2.GaussianBlur(cv2.resize(g1, None, fx=s, fy=s), (5, 5), 0).astype(np.float32)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        corr, warp = cv2.findTransformECC(a, b, warp, cv2.MOTION_AFFINE,
                                          (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
    except cv2.error:
        return None, {"ecc": "did not converge"}
    if not np.isfinite(corr) or corr < min_corr:
        return None, {"ecc_corr": round(float(corr), 3), "reason": "ECC correlation too low"}
    warp[:, 2] /= s
    # ECC maps reference -> capture coordinates; invert to warp the capture onto the reference
    try:
        H = np.linalg.inv(np.vstack([warp, [0, 0, 1]]))
    except np.linalg.LinAlgError:
        return None, {"reason": "singular ECC transform"}
    if not _sane(H, w, h):
        return None, {"reason": "no reliable ECC transform"}
    return H, {"method": "ecc", "ecc_corr": round(float(corr), 3)}


def _sane(H, w, h) -> bool:
    """Reject wild homographies (flips, huge zooms) that RANSAC sometimes returns."""
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
    area = cv2.contourArea(out, oriented=True)
    return 0.5 * w * h < area < 2.0 * w * h and cv2.isContourConvex(out)
