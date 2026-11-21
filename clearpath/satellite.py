"""Before/after aerial imagery for a neighborhood location (Person 3).

Two free, no-key sources, both Web-Mercator XYZ tiles so a before and an after
image of the same lat/lon line up pixel-for-pixel (to within a few metres):

* ``esri:YYYY-MM-DD`` / ``esri:latest``: Esri World Imagery **Wayback**, ~199
  archived versions of the World Imagery basemap since 2014. Picks the newest
  release on or before the date. Capture date/source/resolution come from the
  matching metadata service. Attribution required (see ATTRIBUTION).
* ``noaa:milton`` / ``noaa:helene`` / ``noaa:<layer-id>``: NOAA NGS Emergency
  Response Imagery, aerial photos flown days after a hurricane. Public domain.
  Coverage is flight strips, so we try each layer whose bounding box contains
  the point and keep the first one that actually has imagery there.

Typical neighborhood story: reference = Esri before the storm, initial = NOAA
right after (debris, fallen trees, flooding), follow-up = Esri today (cleared).

    python -m clearpath.satellite --demo                      # Tampa Bay preset sites
    python -m clearpath.satellite --name "My street" --lat 27.77 --lon -82.77 \\
        --before esri:2024-09-01 --after noaa:milton --followup esri:latest

Images are written as data/demo/<slug>/{reference,initial,followup}.jpg plus
site.json (sources, capture dates, attribution), so the app's "Demo photo"
button works for these locations with no other changes.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import config

TILE = 256
UA = {"User-Agent": "neighborhood-hazard-hackathon-demo/0.1"}
CACHE = config.DATA / "satellite"
SITES_DIR = config.DATA / "demo"   # same folder as clearpath.demo, so demo_photo() finds them

WAYBACK_CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
NOAA_EVENTS = {
    "milton": "https://storms.ngs.noaa.gov/storms/milton/services/WMTSCapabilities.xml",
    "helene": "https://storms.ngs.noaa.gov/storms/helene/services/WMTSCapabilities.xml",
    "ian": "https://storms.ngs.noaa.gov/storms/ian/services/WMTSCapabilities.xml",
    "idalia": "https://storms.ngs.noaa.gov/storms/idalia/services/WMTSCapabilities.xml",
}
ATTRIBUTION = {
    "esri": "Imagery: Esri World Imagery Wayback (Esri, Maxar, Earthstar Geographics, and the GIS User Community).",
    "noaa": "Imagery: NOAA National Geodetic Survey Emergency Response Imagery (public domain).",
}

# Preset demo sites around Tampa Bay, hit by Hurricanes Helene (Sep 26, 2024) and
# Milton (Oct 9, 2024). Check each one with `--preview` and move the point onto a
# street that shows visible debris in the "after" image before you present.
PRESETS = [
    # City of Tampa (matches the Tampa Connect channel in config/channels.json)
    {"name": "Davis Islands residential streets (Tampa)", "lat": 27.9265, "lon": -82.4555,
     "before": "esri:2024-09-19", "after": "noaa:milton", "followup": "esri:latest"},
    {"name": "South Tampa near Bayshore (Tampa)", "lat": 27.8935, "lon": -82.4890,
     "before": "esri:2024-09-19", "after": "noaa:milton", "followup": "esri:latest"},
    # Pinellas beach town: the most visible storm sand/debris on streets. Not City of Tampa,
    # so it needs its own channel (City of Madeira Beach) before you "send" a report for it.
    {"name": "Madeira Beach residential street (Pinellas)", "lat": 27.7975, "lon": -82.7905,
     "before": "esri:2024-09-19", "after": "noaa:helene", "followup": "esri:latest"},
]


@dataclass
class Imagery:
    source: str          # "esri" | "noaa"
    layer: str           # Wayback release number or NOAA layer id
    label: str           # human-readable, e.g. "Esri Wayback 2024-09-19"
    captured: str        # best-known capture date (YYYY-MM-DD) or ""
    detail: str          # provider / resolution, if known
    attribution: str
    lat: float
    lon: float
    zoom: int


# --------------------------------------------------------------------------- tiles

def _get(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _cached(name: str, url: str, max_age_days: float = 7) -> bytes:
    p = CACHE / name
    if p.exists() and (datetime.now().timestamp() - p.stat().st_mtime) < max_age_days * 86400:
        return p.read_bytes()
    data = _get(url)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return data


def _world_px(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = TILE * 2 ** z
    r = math.radians(lat)
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


def _tile(template: str, z: int, x: int, y: int, key: str) -> Image.Image | None:
    p = CACHE / "tiles" / key / str(z) / str(x) / f"{y}.img"
    if p.exists():
        data = p.read_bytes()
    else:
        try:
            data = _get(template.format(z=z, x=x, y=y))
        except Exception:
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    if len(data) < 200:  # NOAA serves a tiny transparent PNG where there's no coverage
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None


def mosaic(template: str, key: str, lat: float, lon: float, zoom: int = 19, size: int = 768) -> Image.Image | None:
    """Square image of ``size`` px centred on lat/lon. None if any tile is missing."""
    cx, cy = _world_px(lat, lon, zoom)
    x0, y0 = int(cx - size / 2), int(cy - size / 2)
    canvas = Image.new("RGB", (size, size))
    for ty in range(y0 // TILE, (y0 + size - 1) // TILE + 1):
        for tx in range(x0 // TILE, (x0 + size - 1) // TILE + 1):
            t = _tile(template, zoom, tx, ty, key)
            if t is None:
                return None
            canvas.paste(t.resize((TILE, TILE)), (tx * TILE - x0, ty * TILE - y0))
    return canvas


# --------------------------------------------------------------------------- Esri Wayback

def esri_releases() -> list[dict]:
    """[{num, date, url, metadata}] oldest first."""
    cfg = json.loads(_cached("waybackconfig.json", WAYBACK_CONFIG, max_age_days=3))
    out = []
    for num, item in cfg.items():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", item["itemTitle"])
        if m:
            out.append({"num": num, "date": m.group(1), "url": item["itemURL"],
                        "metadata": item.get("metadataLayerUrl", "")})
    return sorted(out, key=lambda r: r["date"])


def esri_release(on_or_before: str) -> dict:
    rels = esri_releases()
    if on_or_before == "latest":
        return rels[-1]
    ok = [r for r in rels if r["date"] <= on_or_before]
    if not ok:
        raise ValueError(f"No Esri Wayback release on or before {on_or_before} (first is {rels[0]['date']}).")
    return ok[-1]


def esri_capture_info(release: dict, lat: float, lon: float) -> tuple[str, str]:
    """(capture date, 'provider · resolution') from the release's metadata service; best effort."""
    if not release.get("metadata"):
        return "", ""
    for layer in range(0, 13):  # 0 = finest resolution; the first hit is what's shown at high zoom
        q = (f"{release['metadata']}/{layer}/query?geometry={lon},{lat}&geometryType=esriGeometryPoint"
             "&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=SRC_DATE2,NICE_DESC,SRC_RES"
             "&returnGeometry=false&f=json")
        try:
            feats = json.loads(_get(q, timeout=15)).get("features", [])
        except Exception:
            return "", ""
        if feats:
            a = feats[0]["attributes"]
            date = (datetime.fromtimestamp(a["SRC_DATE2"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    if a.get("SRC_DATE2") else "")
            res = f"{a['SRC_RES']:.2g} m/px" if a.get("SRC_RES") else ""
            return date, " · ".join(s for s in (a.get("NICE_DESC") or "", res) if s)
    return "", ""


def esri_image(lat: float, lon: float, on_or_before: str, zoom: int = 19, size: int = 768):
    rel = esri_release(on_or_before)
    tmpl = rel["url"].replace("{level}", "{z}").replace("{row}", "{y}").replace("{col}", "{x}")
    img = mosaic(tmpl, f"esri-{rel['num']}", lat, lon, zoom, size)
    if img is None:
        raise RuntimeError(f"Esri Wayback {rel['date']} has no tiles at {lat},{lon} zoom {zoom}.")
    captured, detail = esri_capture_info(rel, lat, lon)
    return img, Imagery("esri", rel["num"], f"Esri Wayback {rel['date']}", captured, detail,
                        ATTRIBUTION["esri"], lat, lon, zoom)


# --------------------------------------------------------------------------- NOAA NGS

def noaa_layers(event: str) -> list[dict]:
    """[{id, date, bbox:(w,s,e,n)}] for a storm's WMTS capabilities."""
    xml = _cached(f"noaa-{event}.xml", NOAA_EVENTS[event], max_age_days=30).decode("utf-8", "replace")
    out = []
    for block in re.findall(r"<Layer>(.*?)</Layer>", xml, re.S):
        ident = re.search(r"<ows:Identifier>(.*?)<", block)
        lo = re.search(r"LowerCorner>([-\d.]+) ([-\d.]+)<", block)
        hi = re.search(r"UpperCorner>([-\d.]+) ([-\d.]+)<", block)
        if ident and lo and hi:
            lid = ident.group(1)
            d = re.match(r"(\d{4})(\d{2})(\d{2})", lid)
            out.append({"id": lid, "date": f"{d.group(1)}-{d.group(2)}-{d.group(3)}" if d else "",
                        "bbox": (float(lo.group(1)), float(lo.group(2)), float(hi.group(1)), float(hi.group(2)))})
    return out


def noaa_image(lat: float, lon: float, which: str, zoom: int = 19, size: int = 768):
    if which in NOAA_EVENTS:
        cands = [l for l in noaa_layers(which)
                 if l["bbox"][0] <= lon <= l["bbox"][2] and l["bbox"][1] <= lat <= l["bbox"][3]]
    else:  # explicit layer id like 20241011d-rgb
        d = re.match(r"(\d{4})(\d{2})(\d{2})", which)
        cands = [{"id": which, "date": f"{d.group(1)}-{d.group(2)}-{d.group(3)}" if d else ""}]
    for layer in cands:
        img = mosaic(f"https://stormscdn.ngs.noaa.gov/{layer['id']}/{{z}}/{{x}}/{{y}}",
                     f"noaa-{layer['id']}", lat, lon, zoom, size)
        if img is not None:
            return img, Imagery("noaa", layer["id"], f"NOAA NGS {layer['id']}", layer["date"],
                                "NOAA aerial survey, post-storm", ATTRIBUTION["noaa"], lat, lon, zoom)
    raise RuntimeError(f"No NOAA '{which}' imagery covers {lat},{lon} (tried {len(cands)} layers).")


def image(lat: float, lon: float, spec: str, zoom: int = 19, size: int = 768):
    """spec: 'esri:2024-09-01' | 'esri:latest' | 'noaa:milton' | 'noaa:<layer-id>'."""
    src, _, arg = spec.partition(":")
    if src == "esri":
        return esri_image(lat, lon, arg or "latest", zoom, size)
    if src == "noaa":
        return noaa_image(lat, lon, arg or "milton", zoom, size)
    raise ValueError(f"Unknown imagery source {spec!r}")


# --------------------------------------------------------------------------- sites

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def make_site(name: str, lat: float, lon: float, before: str, after: str | None, followup: str | None = None,
              zoom: int = 19, size: int = 768, register: bool = True) -> Path:
    """Fetch reference/initial/(followup) images, write site.json, optionally register a Location."""
    d = SITES_DIR / slug(name)
    d.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "lat": lat, "lon": lon, "zoom": zoom, "images": {}}
    for fname, spec in (("reference.jpg", before), ("initial.jpg", after), ("followup.jpg", followup)):
        if not spec:
            continue
        img, info = image(lat, lon, spec, zoom, size)
        after = meta["images"].get("initial.jpg", {}).get("captured", "")
        if fname == "followup.jpg" and info.captured and after and info.captured <= after:
            # e.g. Esri's newest imagery here predates the storm: it would fake a "cleared" result.
            meta["skipped_followup"] = (f"{info.label} was captured {info.captured}, not after the "
                                        f"{after} image; take a real follow-up photo instead.")
            (d / fname).unlink(missing_ok=True)
            continue
        img.save(d / fname, quality=90)
        meta["images"][fname] = {"spec": spec, **asdict(info)}
    (d / "site.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if register:
        from .store import Store
        store = Store()
        if name not in {l["name"] for l in store.locations()}:
            ref = meta["images"]["reference.jpg"]
            store.add_location(name, d / "reference.jpg",
                               f"Aerial site at {lat:.5f}, {lon:.5f}. Reference: {ref['label']}"
                               + (f" (captured {ref['captured']})" if ref["captured"] else "") + ".")
    return d


def site_meta(reference_path: str | Path) -> dict | None:
    """site.json next to a reference image, if this location came from make_site()."""
    p = Path(reference_path).parent / "site.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def imagery_for(reference_path: str | Path, image_path: str | Path) -> dict | None:
    image_path = Path(image_path)
    if image_path.resolve().parent != Path(reference_path).resolve().parent:
        return None
    meta = site_meta(reference_path)
    return (meta or {}).get("images", {}).get(image_path.name)


def maps_link(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=19/{lat:.6f}/{lon:.6f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="fetch the Tampa Bay preset sites")
    ap.add_argument("--name"); ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float)
    ap.add_argument("--before", default="esri:2024-09-19")
    ap.add_argument("--after", default="noaa:milton")
    ap.add_argument("--followup", default="esri:latest")
    ap.add_argument("--zoom", type=int, default=19)
    ap.add_argument("--preview", action="store_true", help="write images but don't register a location")
    ap.add_argument("--reference-only", action="store_true", help="fetch only the before image for ground photo uploads")
    ap.add_argument("--list-esri", action="store_true", help="print Esri Wayback release dates")
    a = ap.parse_args(argv)
    config.ensure_dirs()
    if a.list_esri:
        for r in esri_releases():
            print(r["date"], r["num"])
        return
    sites = PRESETS if a.demo else [{"name": a.name, "lat": a.lat, "lon": a.lon,
                                     "before": a.before, "after": a.after, "followup": a.followup}]
    if not a.demo and (a.name is None or a.lat is None or a.lon is None):
        ap.error("--name, --lat and --lon are required (or use --demo)")
    for s in sites:
        try:
            after = None if a.reference_only else s["after"]
            followup = None if a.reference_only else s.get("followup")
            d = make_site(s["name"], s["lat"], s["lon"], s["before"], after, followup,
                          zoom=a.zoom, register=not a.preview)
            meta = json.loads((d / "site.json").read_text())
            print(f"OK  {s['name']} -> {d}")
            for f, info in meta["images"].items():
                print(f"      {f:14} {info['label']:28} captured {info['captured'] or '?'}  {info['detail']}")
            if meta.get("skipped_followup"):
                print(f"      followup.jpg   SKIPPED: {meta['skipped_followup']}")
        except Exception as e:
            print(f"ERR {s['name']}: {e}")


if __name__ == "__main__":
    main()
