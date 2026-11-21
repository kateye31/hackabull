"""Where things are: GPS from photos, satellite imagery before the storm, tree-risk, geocoding.

* exif_gps(): read GPS from a phone photo BEFORE capture.py strips EXIF, so a resident's
  report lands on the right neighborhood spot without them picking it.
* satellite_image(): a before-storm aerial image around a spot, from USGS NAIP aerial imagery
  (about 0.6 m per pixel, US public domain, no API key), with the coarser USGS basemap as fallback. Hugging Face hosts models, not imagery
  of arbitrary neighborhoods, so imagery comes from here by coordinates.
* canopy_fraction(): how much of the area around a route is tree canopy, from the aerial
  image (excess-green index). More canopy over a route = more likely blocked after a storm.
* geocode(): address -> (lat, lon) via OpenStreetMap Nominatim (1 request, generic client name).
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
from PIL import Image

from . import config

EARTH_R = 6_371_000.0
IMAGERY = (  # tried in order
    ("USGS NAIP", "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"),
    ("USGS basemap", "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export"),
)
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres: d = 2R·asin(√(sin²(Δφ/2) + cos φ1 cos φ2 sin²(Δλ/2)))."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def nearest(spots: list[dict], lat: float, lon: float, max_m: float | None = None) -> tuple[dict | None, float | None]:
    """Closest spot that has coordinates, if within max_m metres."""
    max_m = config.MATCH_RADIUS_M if max_m is None else max_m
    best, best_d = None, None
    for s in spots:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if best_d is None or d < best_d:
            best, best_d = s, d
    if best is None or best_d > max_m:
        return None, best_d
    return best, best_d


def _ratio(v) -> float:
    try:
        return float(v)
    except TypeError:  # older Pillow: (num, den)
        return v[0] / v[1]


def exif_gps(image_bytes: bytes) -> tuple[float, float] | None:
    """(lat, lon) from a photo's EXIF, or None. Call before the photo is re-encoded."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        gps = img.getexif().get_ifd(0x8825)  # GPSInfo
        if not gps or 2 not in gps or 4 not in gps:
            return None
        lat = sum(_ratio(x) / 60 ** i for i, x in enumerate(gps[2]))
        lon = sum(_ratio(x) / 60 ** i for i, x in enumerate(gps[4]))
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lon = -lon
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            return None
        return lat, lon
    except Exception:
        return None


def bbox(lat: float, lon: float, half_m: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) in degrees for a square half_m metres from the centre."""
    dlat = half_m / 111_320.0
    dlon = half_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def satellite_image(lat: float, lon: float, dest: Path, half_m: float = 75, size: int = 512) -> Path | None:
    """Fetch (or reuse) an aerial image centred on lat/lon. Returns the path, or None offline/on failure."""
    dest = Path(dest)
    if dest.exists():
        return dest
    if config.OFFLINE:
        return None
    import requests
    w, s, e, n = bbox(lat, lon, half_m)
    params = {"bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 3857, "size": f"{size},{size}",
              "format": "jpg", "f": "image"}
    img = None
    for _, url in IMAGERY:
        try:
            r = requests.get(url, params=params, headers={"User-Agent": config.USER_AGENT}, timeout=20)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            if np.asarray(img).std() > 3:  # not a blank tile
                break
            img = None
        except Exception:
            img = None
    if img is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=90)
    return dest


def canopy_fraction(image_path: Path | str, radius_frac: float = 0.5) -> float:
    """Share of the area around the centre that looks like tree canopy.

    Excess-green index on chromatic coordinates: ExG = 2g − r − b, with r = R/(R+G+B) etc.
    Vegetation has ExG > 0.05; pavement, roofs and water sit near or below 0.
    Dark green (canopy) is separated from bright lawn by brightness < 0.45.
    """
    rgb = np.asarray(Image.open(image_path).convert("RGB"), np.float32) / 255.0
    total = rgb.sum(-1) + 1e-6
    r, g, b = (rgb[..., i] / total for i in range(3))
    exg = 2 * g - r - b
    bright = rgb.mean(-1)
    canopy = (exg > 0.05) & (bright < 0.45)
    h, w = canopy.shape
    yy, xx = np.ogrid[:h, :w]
    inside = (yy - h / 2) ** 2 + (xx - w / 2) ** 2 <= (radius_frac * min(h, w)) ** 2
    return float(canopy[inside].mean())


def tree_risk(canopy: float | None) -> str:
    if canopy is None:
        return "unknown"
    return "high" if canopy >= 0.35 else "medium" if canopy >= 0.15 else "low"


def geocode(address: str) -> tuple[float, float, str] | None:
    """Address -> (lat, lon, display name) from OpenStreetMap Nominatim, or None."""
    if config.OFFLINE or not address.strip():
        return None
    import requests
    try:
        r = requests.get(NOMINATIM, params={"q": address, "format": "json", "limit": 1},
                         headers={"User-Agent": config.USER_AGENT}, timeout=15)
        r.raise_for_status()
        hits = r.json()
    except Exception:
        return None
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0].get("display_name", "")


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Move north_m / east_m metres from a point (small distances)."""
    return (lat + north_m / 111_320.0,
            lon + east_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6)))
