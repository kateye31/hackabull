"""Paths and settings. Override with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    """KEY=value lines from a git-ignored .env file (e.g. GEMINI_API_KEY); real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")
DATA = Path(os.environ.get("CLEARPATH_DATA", ROOT / "data")).resolve()
DB_PATH = DATA / "clearpath.db"
CAPTURES = DATA / "captures"
REFERENCES = DATA / "references"
OVERLAYS = DATA / "overlays"
REPORTS = DATA / "reports"
SATELLITE = DATA / "satellite"
RESOURCES = DATA / "resources"   # cached OpenStreetMap lookups
CHANNELS_FILE = ROOT / "config" / "channels.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

# "auto" = DINOv2 when it can load, otherwise the OpenCV baseline
VISION_METHOD = os.environ.get("CLEARPATH_VISION", "auto")
DINO_MODEL = os.environ.get("CLEARPATH_DINO", "facebook/dinov2-small")

# Extra Hugging Face models: CLIP suggests the damage type, SegFormer finds the walkable surface.
# "auto" = use them when they load; "off" = skip (tests, slow laptops).
ML = os.environ.get("CLEARPATH_ML", "auto")
CLIP_MODEL = os.environ.get("CLEARPATH_CLIP", "openai/clip-vit-base-patch32")
SEG_MODEL = os.environ.get("CLEARPATH_SEG", "nvidia/segformer-b0-finetuned-ade-512-512")

# Network lookups (satellite imagery, OpenStreetMap). "1" = never call out (tests, no Wi-Fi).
OFFLINE = os.environ.get("CLEARPATH_OFFLINE", "0") == "1"
# Generic client name for public map services; never put personal details here.
USER_AGENT = "ClearPath-hackathon/0.2 (storm damage reporting demo)"
# Where demo locations are placed on the map (lat, lon). Default: a residential area of Tampa, FL.
DEMO_CENTER = tuple(float(v) for v in os.environ.get("CLEARPATH_DEMO_CENTER", "28.0006,-82.4594").split(","))
# How far from a known spot a GPS-tagged report can be and still be matched to it.
MATCH_RADIUS_M = float(os.environ.get("CLEARPATH_MATCH_RADIUS_M", "250"))


def ensure_dirs():
    for d in (DATA, CAPTURES, REFERENCES, OVERLAYS, REPORTS, SATELLITE, RESOURCES):
        d.mkdir(parents=True, exist_ok=True)
