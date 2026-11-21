"""Demo locations so the app works with no webcam (Person 1).

    python -m clearpath.demo                    # four synthetic routes after a storm
    python -m clearpath.demo real "Palm St bus stop" photos/palm-bus --where "Next to the hydrant, facing the shelter"
    python -m clearpath.demo real "Palm St bus stop" photos/palm-bus --eval   # also give Person 2 the pairs
    python -m clearpath.demo list

Synthetic: creates four neighborhood routes under data/demo/<slug>/ with reference.jpg
(before the storm), initial.jpg (storm damage: fallen tree, debris, branches, flooding),
followup.jpg (after cleanup, different light/angle).

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

import cv2
import numpy as np

from . import config, geo
from .capture import _to_jpeg
from .store import Store

DEMO = config.DATA / "demo"
EVAL_REAL = config.DATA / "eval" / "real"
SPOTS = [
    # seeds picked so DINOv2 says obstructed after the storm and clear after cleanup
    ("Palm Street sidewalk", "tree", 3),
    ("Bayview Avenue curb ramp", "debris", 5),             # OpenCV baseline misses this one: good for the pitch
    ("Walkway to the community center", "branches", 3),
    ("5th Avenue bus stop", "water", 6),
]
# where the demo spots sit around config.DEMO_CENTER (metres north, east)
SPOT_OFFSETS_M = [(0, 0), (180, -120), (-150, 160), (90, 260)]
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
    from evaluation.make_synthetic import obstacle, recapture, scene

    store = store or Store()
    existing = {l["name"] for l in store.locations()}
    made = 0
    for name, kind, seed_ in SPOTS:
        if name in existing:
            continue
        rng = np.random.default_rng(seed_)
        base, path = scene(rng)
        ref = np.clip(base, 0, 255).astype(np.uint8)
        blocked = base.copy()
        obstacle(blocked, rng, path, kind)
        d = DEMO / name.lower().replace(" ", "-")
        d.mkdir(parents=True, exist_ok=True)
        for fname, img in (("reference.jpg", ref), ("initial.jpg", recapture(blocked, rng, hard=False)),
                           ("followup.jpg", recapture(base, rng, hard=False))):
            cv2.imwrite(str(d / fname), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        loc_id = store.add_location(name, d / "reference.jpg", f"Demo route after a storm (synthetic). Damage: {kind}.")
        north, east = SPOT_OFFSETS_M[len(existing) + made] if len(existing) + made < len(SPOT_OFFSETS_M) else (0, 0)
        lat, lon = geo.offset(*config.DEMO_CENTER, north, east)
        from .pipeline import add_geo  # satellite image + canopy; skipped quietly when offline
        add_geo(store, loc_id, lat, lon)
        made += 1
    return made


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
    print(f"added {seed()} demo locations")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def synthetic_after_aerial(before_path: str | Path, seed: int = 0) -> bytes:
    """A SYNTHETIC after-storm aerial for demos: the real before-storm tile with drawn storm damage
    (fallen tree crowns across the middle, a muddy flood patch, scattered debris). Not real imagery."""
    img = cv2.cvtColor(cv2.imread(str(before_path)), cv2.COLOR_BGR2RGB).astype(np.float32)
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    flood = np.zeros((h, w), np.uint8)
    cv2.ellipse(flood, (int(w * 0.62), int(h * 0.62)), (int(w * 0.2), int(h * 0.12)), 15, 0, 360, 1, -1)
    f = cv2.GaussianBlur(flood.astype(np.float32), (0, 0), 6)[..., None]
    img = img * (1 - 0.85 * f) + np.array([118, 104, 78], np.float32) * (0.85 * f)
    for _ in range(4):  # fallen crowns: dark green blobs with a brown trunk
        cx, cy = int(rng.uniform(0.25, 0.6) * w), int(rng.uniform(0.25, 0.6) * h)
        ang = rng.uniform(0, np.pi)
        L = int(rng.uniform(0.08, 0.14) * w)
        p2 = (int(cx + L * np.cos(ang)), int(cy + L * np.sin(ang)))
        cv2.line(img, (cx, cy), p2, (92, 68, 44), 4)
        cv2.circle(img, p2, int(L * 0.45), (38, 70, 34), -1)
    for _ in range(25):  # debris: small light/dark fragments
        x, y = int(rng.uniform(0.2, 0.8) * w), int(rng.uniform(0.2, 0.8) * h)
        cv2.rectangle(img, (x, y), (x + int(rng.integers(3, 9)), y + int(rng.integers(2, 6))),
                      tuple(int(v) for v in rng.choice([(200, 190, 170), (70, 70, 75), (40, 90, 170)])), -1)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    return buf.tobytes()
