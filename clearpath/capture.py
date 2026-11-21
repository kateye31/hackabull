"""Saving photos (Person 1). Webcam frames and uploads both come through here."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from . import config
from .contracts import PHASES, SavedCapture

MAX_SIDE = 1600


def _to_jpeg(image_bytes: bytes, dest: Path) -> Path:
    """Re-encode as JPEG: fixes phone rotation, drops EXIF (GPS etc.), caps size."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=90)
    return dest


def save_capture(image_bytes: bytes, inspection_id: str, phase: str) -> SavedCapture:
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {PHASES}")
    t = datetime.now(timezone.utc)
    dest = config.CAPTURES / inspection_id / f"{phase}_{t:%Y%m%dT%H%M%S}.jpg"
    _to_jpeg(image_bytes, dest)
    return SavedCapture(inspection_id=inspection_id, phase=phase, image_path=dest,
                        captured_at=t.isoformat(timespec="seconds"))


def save_reference(image_bytes: bytes, name: str) -> Path:
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:40] or "location"
    t = datetime.now(timezone.utc)
    return _to_jpeg(image_bytes, config.REFERENCES / f"{slug}_{t:%Y%m%dT%H%M%S}.jpg")
