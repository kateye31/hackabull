"""Paths and settings. Override with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("CLEARPATH_DATA", ROOT / "data"))
DB_PATH = DATA / "clearpath.db"
CAPTURES = DATA / "captures"
REFERENCES = DATA / "references"
OVERLAYS = DATA / "overlays"
REPORTS = DATA / "reports"
CHANNELS_FILE = ROOT / "config" / "channels.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

# "auto" = DINOv2 when it can load, otherwise the OpenCV baseline
VISION_METHOD = os.environ.get("CLEARPATH_VISION", "auto")
DINO_MODEL = os.environ.get("CLEARPATH_DINO", "facebook/dinov2-small")


def ensure_dirs():
    for d in (DATA, CAPTURES, REFERENCES, OVERLAYS, REPORTS):
        d.mkdir(parents=True, exist_ok=True)
