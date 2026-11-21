"""Demo locations so the app works with no webcam (Person 1).

    python -m clearpath.demo                    # real Tampa Bay overhead imagery
    python -m clearpath.demo real "Palm St bus stop" photos/palm-bus --where "Next to the hydrant, facing the shelter"
    python -m clearpath.demo real "Palm St bus stop" photos/palm-bus --eval   # also give Person 2 the pairs
    python -m clearpath.demo list

Real: takes a folder of your own neighborhood photos named
    reference.*   the route before the storm, clear     (required)
    blocked.*     the same spot with storm debris        (required)
    cleared.*     the same spot after cleanup           (optional)
(.jpg/.jpeg/.png/.webp), re-encodes them (rotation fixed, EXIF/GPS removed) into
data/demo/<slug>/ and registers the location. Either way the app offers "Demo photo"
for these locations, which is the backup run if the camera fails on stage.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

from . import config, geo
from .capture import _to_jpeg
from .store import Store

DEMO = config.DATA / "demo"
EVAL_REAL = config.DATA / "eval" / "real"
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
# output file in data/demo/<slug>/  ->  accepted input names (without extension)
REAL_FILES = {
    "reference.jpg": ("reference", "clear"),
    "initial.jpg": ("blocked", "initial"),
    "followup.jpg": ("cleared", "followup", "follow_up"),
}


def demo_photo(reference_path: str | Path, phase: str) -> Path | None:
    p = Path(reference_path).parent / ("initial.jpg" if phase == "initial" else "followup.jpg")
    return p if p.exists() and p.parent.parent == DEMO else None


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:40] or "location"


def seed(store: Store | None = None) -> int:
    """Register the verified Tampa Bay presets, reusing downloaded imagery when available."""
    from . import satellite

    store = store or Store()
    existing = {loc["name"] for loc in store.locations()}
    added = 0
    failures = []
    for site in satellite.PRESETS:
        name = site["name"]
        if name in existing:
            continue
        lat, lon = site["lat"], site["lon"]
        directory = satellite.SITES_DIR / satellite.slug(name)
        reference = directory / "reference.jpg"
        try:
            if not reference.is_file() or not satellite.imagery_for(reference, reference):
                if config.OFFLINE:
                    raise RuntimeError("Imagery isn't cached and offline mode is enabled.")
                satellite.make_site(name, lat, lon, site["before"], site["after"], register=False)
            info = satellite.imagery_for(reference, reference)
            location_id = store.add_location(name, reference, satellite._describe_reference(info))
            satellite._connect(store, location_id, directory, lat, lon)
            added += 1
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"{name}: {exc}")
    if failures:
        raise RuntimeError("Some demo locations couldn't be loaded. " + " ".join(failures))
    return added


def _find(folder: Path, stems: tuple[str, ...]) -> Path | None:
    files = {p.stem.lower(): p for p in folder.iterdir() if p.is_file()}
    for s in stems:
        p = files.get(s)
        if p is None:
            continue
        if p.suffix.lower() in (".heic", ".heif"):
            raise ValueError(f"{p.name} is HEIC. Re-save it as JPEG (iPhone: Settings > Camera > Formats > "
                             "Most Compatible, or export as JPEG).")
        if p.suffix.lower() in IMAGE_EXT:
            return p
    return None


def add_real(name: str, folder: str | Path, where: str = "", store: Store | None = None,
             to_eval: bool = False, lat: float | None = None, lon: float | None = None,
             address: str = "") -> int:
    """Register a location from your own before/after-storm photos. Returns the new location id."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder} is not a folder")
    found = {out: _find(folder, stems) for out, stems in REAL_FILES.items()}
    missing = [REAL_FILES[k][0] for k in ("reference.jpg", "initial.jpg") if not found[k]]
    if missing:
        raise FileNotFoundError(f"{folder} needs {' and '.join(m + '.jpg' for m in missing)} "
                                "(plus cleared.jpg for the after-cleanup step, optional)")
    store = store or Store()
    if name.strip() in {l["name"] for l in store.locations()}:
        raise ValueError(f"A location called {name!r} already exists.")
    d = DEMO / slug(name)
    if d.exists():
        shutil.rmtree(d)  # left over from an older database; the database is the source of truth
    gps = geo.exif_gps(found["reference.jpg"].read_bytes())  # read before EXIF is stripped
    for out, src in found.items():
        if src:
            _to_jpeg(src.read_bytes(), d / out)
    if to_eval:
        export_eval(d, slug(name))
    desc = f"Real photos. Stand: {where.strip()}" if where.strip() else "Real photos."
    loc_id = store.add_location(name, d / "reference.jpg", desc)
    if lat is None and address:
        hit = geo.geocode(address)
        lat, lon = (hit[0], hit[1]) if hit else (None, None)
    if lat is None and gps:
        lat, lon = gps
    if lat is not None and lon is not None:
        from .pipeline import add_geo
        add_geo(store, loc_id, lat, lon)
    return loc_id


def export_eval(demo_dir: Path, pair_slug: str, root: Path | None = None) -> list[str]:
    """Hand Person 2 labeled pairs: reference+blocked (obstructed), reference+cleared (clear)."""
    root = root or EVAL_REAL
    labels = root / "labels.csv"
    fields = ["pair_id", "label", "obstruction", "hard_case"]
    rows = list(csv.DictReader(open(labels, encoding="utf-8"))) if labels.exists() else []
    made = []
    for capture_file, suffix, label in (("initial.jpg", "blocked", "obstructed"), ("followup.jpg", "cleared", "clear")):
        if not (demo_dir / capture_file).exists():
            continue
        pid = f"{pair_slug}-{suffix}"
        (root / pid).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(demo_dir / "reference.jpg", root / pid / "reference.jpg")
        shutil.copyfile(demo_dir / capture_file, root / pid / "capture.jpg")
        rows = [r for r in rows if r["pair_id"] != pid]
        rows.append({"pair_id": pid, "label": label, "obstruction": "", "hard_case": ""})
        made.append(pid)
    root.mkdir(parents=True, exist_ok=True)
    with open(labels, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m clearpath.demo", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("real", help="add a location from your own photos (before, after the storm, after cleanup)")
    r.add_argument("name", help='location name as it should appear in the app, e.g. "Palm St bus stop"')
    r.add_argument("folder", help="folder holding reference.jpg (before), blocked.jpg (after the storm) and optionally cleared.jpg")
    r.add_argument("--where", default="", help="where you stood, so anyone can retake it from the same spot")
    r.add_argument("--eval", action="store_true", help="also copy the pairs to data/eval/real/ for Person 2")
    r.add_argument("--lat", type=float, help="latitude (default: GPS from reference.jpg, if the phone saved it)")
    r.add_argument("--lon", type=float, help="longitude")
    r.add_argument("--address", default="", help="street address to look up instead of --lat/--lon")
    sub.add_parser("list", help="show locations and whether each has demo photos")
    args = ap.parse_args(argv)

    config.ensure_dirs()
    if args.cmd == "real":
        try:
            add_real(args.name, args.folder, args.where, to_eval=args.eval, lat=args.lat, lon=args.lon,
                     address=args.address)
        except (FileNotFoundError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"added {args.name!r} with real photos" + (f"; eval pairs in {EVAL_REAL}" if args.eval else ""))
        return 0
    if args.cmd == "list":
        for l in Store().locations():
            ref = l["reference_path"]
            ok = "ok " if Path(ref).exists() else "MISSING"
            demo_ = ", ".join(ph for ph in ("initial", "follow_up") if demo_photo(ref, ph)) or "camera/upload only"
            print(f"{ok:7s} {l['name']:32s} demo photos: {demo_}")
        return 0
    try:
        print(f"added {seed()} demo locations")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
