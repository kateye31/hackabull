"""Satellite / aerial checks (Person 2).

A top-down satellite image and a street-level photo can't be compared pixel to pixel: the
viewpoints share almost nothing. So the satellite view is used three ways:

1. compare_aerial(): BEFORE-storm aerial (USGS NAIP) vs AFTER-storm aerial (NOAA post-storm
   flights or a drone photo taken straight down). Same viewpoint, so the same DINOv2 change
   map used for ground photos works, plus RemoteCLIP for what kind of change it is.
2. RemoteCLIP (MVRL/remote-clip-vit-base-patch32, CLIP retrained on aerial imagery, loaded with
   open_clip) scores scene descriptions. On a single image it is unreliable: on a normal
   pre-storm tile of our demo area it called one block "a flooded residential area" at 0.78.
   So we only report how each description's score SHIFTS between before and after.
3. consistency(): does the view from above support what the ground photo shows? A fallen tree
   reported where there's almost no canopy, or flooding far from low ground, gets a flag.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .. import config

REMOTE_CLIP = "MVRL/remote-clip-vit-base-patch32"
AERIAL_LABELS = {
    "trees": "dense trees over houses and streets",
    "open": "houses and streets with few trees",
    "flooded": "a flooded residential area",
    "debris": "streets blocked by fallen trees and debris",
    "roof_damage": "houses with damaged roofs and blue tarps",
    "water_body": "a lake or river",
}


class AerialUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _remoteclip():
    if config.ML == "off":
        raise AerialUnavailable("CLEARPATH_ML=off")
    try:
        import open_clip
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32")
        sd = load_file(hf_hub_download(REMOTE_CLIP, "model.safetensors"))
        sd = {k[len("model."):] if k.startswith("model.") else k: v for k, v in sd.items()}
        missing, _ = model.load_state_dict(sd, strict=False)
        if missing:
            raise AerialUnavailable(f"RemoteCLIP weights incomplete ({len(missing)} missing)")
        model.eval()
        tok = open_clip.get_tokenizer("ViT-B-32")
        with torch.no_grad():
            tf = model.encode_text(tok([f"an aerial image of {t}" for t in AERIAL_LABELS.values()]))
            tf = tf / tf.norm(dim=-1, keepdim=True)
        return model, preprocess, tf
    except AerialUnavailable:
        raise
    except Exception as e:
        raise AerialUnavailable(f"RemoteCLIP unavailable: {e}")


def scene_scores(path: Path | str) -> dict:
    """{label: probability} for one aerial image. Use only as half of a before/after shift."""
    from PIL import Image
    model, preprocess, tf = _remoteclip()
    import torch
    with torch.no_grad():
        f = model.encode_image(preprocess(Image.open(path).convert("RGB")).unsqueeze(0))
        f = f / f.norm(dim=-1, keepdim=True)
        p = (100 * f @ tf.T).softmax(-1)[0].tolist()
    return {k: round(v, 3) for k, v in zip(AERIAL_LABELS, p)}


def compare_aerial(before: Path | str, after: Path | str, overlay: Path | str) -> dict:
    """Change between two top-down images of the same spot."""
    from . import compare
    r = compare(before, after, overlay, aerial=True)
    out = {"verdict": r.verdict, "changed_fraction": r.changed_fraction, "largest_region": r.largest_region,
           "method": r.method, "aligned": r.aligned, "overlay_path": str(r.overlay_path), "shift": None}
    try:
        b, a = scene_scores(before), scene_scores(after)
        shift = {k: round(a[k] - b[k], 3) for k in AERIAL_LABELS}
        out["shift"] = dict(sorted(shift.items(), key=lambda kv: -kv[1]))
        out["scores_before"], out["scores_after"] = b, a
    except AerialUnavailable as e:
        out["shift_note"] = str(e)
    return out


def consistency(location: dict, damage_type: str | None) -> list[str]:
    """Plain-language notes on whether the view from above supports the ground report."""
    notes = []
    canopy = location.get("canopy")
    if canopy is None:
        return ["No satellite view of this spot yet, so nothing to check the photo against."]
    if damage_type == "Fallen tree or limbs":
        if canopy < 0.05:
            notes.append(f"From above there's almost no tree canopy here ({canopy:.0%}). "
                         "Check the photo really is from this spot.")
        else:
            notes.append(f"Consistent: {canopy:.0%} tree canopy around this spot before the storm.")
    elif canopy >= 0.35:
        notes.append(f"Heavy tree canopy here ({canopy:.0%}): look for hanging branches and wires too.")
    aerial = location.get("aerial_result") or {}
    if aerial.get("verdict") == "obstructed":
        notes.append(f"The after-storm aerial also shows change here ({aerial['largest_region']:.0%} of the view).")
    elif aerial.get("verdict") == "clear" and damage_type:
        notes.append("The after-storm aerial shows little change from above; damage may be under the canopy "
                     "or at ground level only.")
    return notes
