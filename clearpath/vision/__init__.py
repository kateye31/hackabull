"""Person 2's entry point: compare a capture with its clear-path reference.

    from clearpath.vision import compare
    result = compare(reference_path, capture_path, overlay_path)   # -> ComparisonResult
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .. import config
from ..contracts import ComparisonResult
from . import baseline, dino
from .align import align, load_rgb

# Verdict cut-offs on the LARGEST changed region (share of the image).
# Set from synthetic pairs only - re-tune on real neighborhood photos with evaluation/evaluate.py.
OBSTRUCTED_AT = {"dinov2": 0.05, "opencv": 0.05}
CLEAR_BELOW = {"dinov2": 0.02, "opencv": 0.015}


def verdict(method: str, largest_region: float) -> str:
    if largest_region >= OBSTRUCTED_AT[method]:
        return "obstructed"
    if largest_region < CLEAR_BELOW[method]:
        return "clear"
    return "uncertain"


def compare(reference_path, capture_path, overlay_path, method: str | None = None) -> ComparisonResult:
    """method: "dinov2", "opencv" or "auto" (DINOv2 if it loads, else OpenCV).

    The OpenCV baseline always runs too; its numbers go in details["opencv"] so the
    app and the evaluation can show both side by side.
    """
    method = method or config.VISION_METHOD
    ref = load_rgb(reference_path)
    cap = load_rgb(capture_path)
    cap_al, valid, align_info = align(ref, cap)

    base = baseline.compare(ref, cap_al, valid)
    primary = base
    fallback_reason = None
    if method in ("auto", "dinov2"):
        try:
            primary = dino.compare(ref, cap_al, valid)
        except dino.DinoUnavailable as e:
            if method == "dinov2":
                raise
            fallback_reason = str(e)

    overlay_path = Path(overlay_path)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(overlay_path), cv2.cvtColor(make_overlay(cap_al, primary["heat"], primary["mask"]), cv2.COLOR_RGB2BGR))

    m = primary["method"]
    details = {
        "alignment": align_info,
        "opencv": {"changed_fraction": round(base["changed_fraction"], 4),
                   "largest_region": round(base["largest_region"], 4), "score": round(base["score"], 4),
                   "verdict": verdict("opencv", base["largest_region"])},
    }
    if m == "dinov2":
        details["dinov2"] = {"changed_fraction": round(primary["changed_fraction"], 4),
                             "largest_region": round(primary["largest_region"], 4),
                             "score": round(primary["score"], 4),
                             "mean_patch_distance": round(primary["mean_patch_distance"], 4),
                             "verdict": verdict("dinov2", primary["largest_region"])}
    if fallback_reason:
        details["fallback"] = f"DINOv2 unavailable, used OpenCV baseline ({fallback_reason})"

    return ComparisonResult(
        method=m,
        score=round(primary["score"], 4),
        changed_fraction=round(primary["changed_fraction"], 4),
        largest_region=round(primary["largest_region"], 4),
        verdict=verdict(m, primary["largest_region"]),
        overlay_path=overlay_path,
        aligned=align_info["aligned"],
        details=details,
    )


def make_overlay(rgb: np.ndarray, heat: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Dim the unchanged scene, tint changed areas red, outline them."""
    out = rgb.astype(np.float32)
    out[~mask] *= 0.55
    red = np.zeros_like(out)
    red[..., 0] = 255
    a = (np.clip(heat, 0, 1) * 0.55 * mask)[..., None]
    out = out * (1 - a) + red * a
    out = out.clip(0, 255).astype(np.uint8)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (255, 230, 0), 2)
    return out
