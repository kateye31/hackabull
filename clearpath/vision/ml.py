"""Hugging Face models on top of the DINOv2 change map, and the damage equations.

* CLIP (openai/clip-vit-base-patch32), zero-shot: which kind of storm damage the after-storm
  photo shows, as ranked suggestions. ~0.3 s per photo on a laptop CPU.
* SegFormer (nvidia/segformer-b0-finetuned-ade-512-512): which pixels of the BEFORE-storm photo
  are walkable/drivable surface (road, sidewalk, path, ...). ~0.3 s.

Equations (W = walkable surface before the storm, C = DINOv2 change mask after alignment):

    blocked share          B  = |W ∩ C| / |W|
    clear width (per row)  rᵧ = |Wᵧ \\ C| / |Wᵧ|       for rows y with walkable surface
    narrowest clear width  N  = 10th percentile of rᵧ over the rows nearest the camera
    damage index           DI = 100 · B · weight(type)   (0 = untouched, 100 = fully covered by the worst kind)

Suggested severity: impassable if N < 0.25 or B ≥ 0.6; partly blocked if B ≥ 0.15; otherwise minor.
Downed power lines are always treated as critical. Every number is a suggestion for the reviewer.

We tried an open-vocabulary detector (OWL-ViT) first: 10-17 s per photo on a laptop CPU and it
missed both debris photos in our test, so CLIP + segmentation is what ships.
"""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from .. import config
from ..contracts import IMPASSABLE, MINOR, PARTLY

# plain-language prompts for CLIP, keyed by our damage types (contracts.OBSTRUCTION_TYPES)
DAMAGE_PROMPTS = {
    "Fallen tree or limbs": "a photo of a fallen tree or large branches blocking a street or sidewalk",
    "Storm debris pile": "a photo of a pile of storm debris, boards and trash on a street",
    "Flooding or standing water": "a photo of a flooded street with standing water",
    "Downed power line": "a photo of downed power lines and a broken utility pole",
    "Fallen sign, pole or fence": "a photo of a fallen sign or fence on a sidewalk",
    "Vehicle, boat or object in right-of-way": "a photo of a car, boat or trash bin pushed into the street by a storm",
    "Damaged road or sidewalk": "a photo of a cracked or washed-out road",
    "Sand or sediment on road": "a photo of sand or mud covering a street after a storm surge",
    "Illegal dumping or bulk trash": "a photo of furniture, mattresses and bulk trash piled at the curb",
    "Construction or barrier": "a photo of construction barriers or cones blocking a sidewalk",
    "Damaged roof or structure": "a photo of a house with a damaged roof or a blue tarp",
    "None": "a photo of a clear, undamaged street",
}
# how much a fully covered route of this type matters (used in the damage index)
TYPE_WEIGHT = {
    "Downed power line": 1.0,
    "Flooding or standing water": 0.9,
    "Fallen tree or limbs": 0.8,
    "Storm debris pile": 0.7,
    "Damaged road or sidewalk": 0.7,
    "Fallen sign, pole or fence": 0.5,
    "Vehicle, boat or object in right-of-way": 0.5,
    "Sand or sediment on road": 0.6,
    "Illegal dumping or bulk trash": 0.5,
    "Construction or barrier": 0.4,
    "Damaged roof or structure": 0.3,     # beside the route rather than on it
    "Other": 0.5,
}
# ADE20K labels that count as surface people walk, roll or drive on
WALKABLE = ("road", "sidewalk", "path", "floor", "earth", "dirt track", "runway", "stairway", "stairs", "step")


class MLUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return config.ML != "off"


@lru_cache(maxsize=1)
def _clip():
    try:
        from transformers import pipeline
        return pipeline("zero-shot-image-classification", model=config.CLIP_MODEL, device=-1)
    except Exception as e:
        raise MLUnavailable(f"could not load {config.CLIP_MODEL}: {e}")


@lru_cache(maxsize=1)
def _seg():
    try:
        from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
        proc = AutoImageProcessor.from_pretrained(config.SEG_MODEL)
        model = SegformerForSemanticSegmentation.from_pretrained(config.SEG_MODEL).eval()
    except Exception as e:
        raise MLUnavailable(f"could not load {config.SEG_MODEL}: {e}")
    ids = [i for i, name in model.config.id2label.items() if name in WALKABLE]
    return proc, model, ids


def available() -> bool:
    if not enabled():
        return False
    try:
        _clip()
        _seg()
        return True
    except MLUnavailable:
        return False


def classify_damage(rgb: np.ndarray, top: int = 3) -> list[dict]:
    """Ranked damage-type suggestions [{type, score}] for an after-storm photo."""
    from PIL import Image
    clf = _clip()
    inv = {v: k for k, v in DAMAGE_PROMPTS.items()}
    out = clf(Image.fromarray(rgb), candidate_labels=list(DAMAGE_PROMPTS.values()))
    return [{"type": inv[o["label"]], "score": round(float(o["score"]), 3)} for o in out[:top]]


def walkable_mask(rgb: np.ndarray) -> np.ndarray:
    """Boolean mask of walkable/drivable surface (SegFormer, ADE20K classes)."""
    import torch
    from PIL import Image
    proc, model, ids = _seg()
    with torch.no_grad():
        logits = model(**proc(images=Image.fromarray(rgb), return_tensors="pt")).logits
    lab = torch.nn.functional.interpolate(logits, size=rgb.shape[:2], mode="bilinear", align_corners=False).argmax(1)[0]
    return np.isin(lab.numpy(), ids)


def damage_metrics(walkable: np.ndarray, changed: np.ndarray, damage_type: str | None = None,
                   valid: np.ndarray | None = None) -> dict:
    """The equations in the module docstring. walkable/changed/valid are HxW boolean masks."""
    h, w = walkable.shape
    walk = walkable.copy()
    if valid is not None:
        walk &= valid
    note = ""
    if walk.sum() < 0.02 * h * w:  # segmentation found no walkway: use the lower half as a stand-in
        walk = np.zeros_like(walk)
        walk[h // 2:] = True
        if valid is not None:
            walk &= valid
        note = "No walkway found in the before-storm photo; used the lower half of the image instead."
    covered = walk & changed
    B = float(covered.sum() / max(walk.sum(), 1))
    rows = [y for y in range(h // 3, h) if walk[y].sum() >= max(8, 0.02 * w)]  # nearest two thirds
    if rows:
        r = np.array([1.0 - covered[y].sum() / walk[y].sum() for y in rows])
        N = float(np.percentile(r, 10))
    else:
        N = 1.0 - B
    weight = TYPE_WEIGHT.get(damage_type or "Other", 0.5)
    DI = round(100 * B * weight, 1)
    if damage_type == "Downed power line":
        severity = IMPASSABLE
    elif N < 0.25 or B >= 0.6:
        severity = IMPASSABLE
    elif B >= 0.15:
        severity = PARTLY
    else:
        severity = MINOR
    return {"walkable_share": round(float(walk.mean()), 3), "blocked_share": round(B, 3),
            "narrowest_clear_width": round(N, 3), "damage_index": DI, "type_weight": weight,
            "suggested_severity": severity, "note": note}


def analyse(reference: np.ndarray, capture_aligned: np.ndarray, changed: np.ndarray, valid: np.ndarray) -> dict:
    """Everything the reviewer sees under 'Damage analysis'. Raises MLUnavailable if models can't load."""
    if not enabled():
        raise MLUnavailable("CLEARPATH_ML=off")
    suggestions = classify_damage(capture_aligned)
    top = next((s["type"] for s in suggestions if s["type"] != "None"), None)
    walk = walkable_mask(reference)
    if walk.shape != changed.shape:
        walk = cv2.resize(walk.astype(np.uint8), changed.shape[::-1], interpolation=cv2.INTER_NEAREST) > 0
    m = damage_metrics(walk, changed, top, valid)
    if m["blocked_share"] < 0.02:  # nothing covers the walkway: don't invent a damage type or severity
        top = None if suggestions[0]["type"] == "None" or m["blocked_share"] == 0 else top
        m["suggested_severity"] = "Looks clear"
        m["damage_index"] = 0.0
    return {"suggestions": suggestions, "likely_type": top, **m,
            "models": {"classifier": config.CLIP_MODEL, "segmentation": config.SEG_MODEL}}
