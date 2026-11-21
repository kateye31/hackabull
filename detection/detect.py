"""Find NEW water after a storm and turn it into issues for the crew map.

A scene folder holds:
    before.png, after.png     required  (north-up; same area)
    scene.json                required  {"bounds": [[south, west], [north, east]], "gsd_m": 0.5}
    roads.png, buildings.png  optional  white = road / building, in the BEFORE image frame
                                        (rasterise from OpenStreetMap for real scenes)

Pipeline: align after -> before, water mask on each, new water = after AND NOT before,
drop tiny blobs, then label each blob: on a road -> flooded_road, touching a house ->
flooded_building (one issue per house), otherwise standing_water.

Writes into the scene folder:
    after_aligned.png   overlay.png (red = new water, blue = water that was already there)
    crops/<id>_before.png, crops/<id>_after.png
    detections.json     -> loaded by the app at startup

    python -m detection.detect data/scenes/demo
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from . import align as align_mod
from .water import water_mask

MIN_BLOB_M2 = 40.0        # ignore puddles smaller than this
ROAD_MIN_M2 = 25.0        # this much water on a road makes it a flooded_road
ROAD_SEGMENT_M = 80.0     # split long flooded streets into one issue per ~80 m stretch
BEFORE_WATER_BUFFER_PX = 4  # shoreline wiggle room around water that was already there


def read_rgb(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def read_mask(path: Path, shape) -> np.ndarray | None:
    if not path.exists():
        return None
    m = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if m.shape != shape:
        m = cv2.resize(m, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return m > 127


def write_rgb(path: Path, rgb: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    code = cv2.COLOR_RGBA2BGRA if rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR
    cv2.imwrite(str(path), cv2.cvtColor(rgb, code))


class GeoFrame:
    """Pixel <-> lat/lon for a north-up image covering `bounds`."""

    def __init__(self, bounds, shape):
        (self.s, self.w), (self.n, self.e) = bounds
        self.h, self.wpx = shape[:2]

    def latlon(self, x: float, y: float):
        lat = self.n - (y / self.h) * (self.n - self.s)
        lon = self.w + (x / self.wpx) * (self.e - self.w)
        return round(lat, 6), round(lon, 6)


def find_new_water(before, after_aligned, valid, bands="rgb", min_px=1):
    before_w = water_mask(before, bands)
    after_w = water_mask(after_aligned, bands) & valid
    k = 2 * BEFORE_WATER_BUFFER_PX + 1
    grown = cv2.dilate(before_w.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    new = after_w & ~grown
    new = cv2.morphologyEx(new.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(new, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    return before_w, after_w, keep[lab]


def detect(scene_dir: Path, bands: str = "rgb") -> dict:
    meta = json.loads((scene_dir / "scene.json").read_text())
    gsd = float(meta.get("gsd_m", 0.5))
    px_m2 = gsd * gsd
    before = read_rgb(scene_dir / "before.png")
    after = read_rgb(scene_dir / "after.png")
    if bands == "rgb":
        before, after = before[..., :3], after[..., :3]
    shape = before.shape[:2]
    geo = GeoFrame(meta["bounds"], shape)

    after_al, valid, align_info = align_mod.align(before, after)
    before_w, after_w, new = find_new_water(before, after_al, valid, bands, min_px=int(MIN_BLOB_M2 / px_m2))

    roads = read_mask(scene_dir / "roads.png", shape)
    bmask = read_mask(scene_dir / "buildings.png", shape)
    if bmask is not None:
        _, bld_lab, bld_stats, bld_cent = cv2.connectedComponentsWithStats(bmask.astype(np.uint8), connectivity=4)
    else:
        bld_lab = None

    n, lab, stats, cent = cv2.connectedComponentsWithStats(new.astype(np.uint8), connectivity=8)
    issues = []
    crops_dir = scene_dir / "crops"
    crops_dir.mkdir(exist_ok=True)
    scene_id = scene_dir.name

    def add(category, x, y, area_m2, bbox, note, comp_mask, extra=None):
        iid = f"A-{scene_id}-{len(issues) + 1:03d}"
        lat, lon = geo.latlon(x, y)
        crops = save_crops(iid, before, after_al, comp_mask, bbox, crops_dir)
        issues.append({
            "id": iid,
            "source": "aerial",
            "category": category,
            "lat": lat,
            "lon": lon,
            "area_m2": round(area_m2, 1),
            "blocks_road": category == "flooded_road",
            "note": note,
            "bbox_px": [int(v) for v in bbox],
            "crops": {k: f"{scene_id}/crops/{v}" for k, v in crops.items()},
            **(extra or {}),
        })

    for i in range(1, n):
        comp = lab == i
        x, y, w, h, area = stats[i]
        made = False
        if roads is not None:
            on_road = comp & roads
            for seg, sx, sy, seg_px in road_segments(on_road, int(ROAD_SEGMENT_M / gsd)):
                if seg_px * px_m2 < ROAD_MIN_M2:
                    continue
                ys, xs = np.nonzero(seg)
                box = (xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)
                add("flooded_road", sx, sy, seg_px * px_m2, box,
                    f"About {seg_px * px_m2:,.0f} m² of water on the road. Treat as impassable until checked.", comp)
                made = True
        if bld_lab is not None:
            touch = cv2.dilate(comp.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            ids = np.unique(bld_lab[touch & bmask])
            for b in ids[ids > 0]:
                bx, by, bw, bh, barea = bld_stats[b]
                pad = 6
                box = (max(bx - pad, 0), max(by - pad, 0), bw + 2 * pad, bh + 2 * pad)
                add("flooded_building", *bld_cent[b], barea * px_m2, box,
                    "Water surrounds this building. Possible interior flooding — verify.", comp,
                    {"footprint_m2": round(float(barea * px_m2), 1)})
                made = True
        if not made:
            add("standing_water", *cent[i], area * px_m2, (x, y, w, h),
                f"About {area * px_m2:,.0f} m² of new standing water.", comp)

    # transparent where the warp left no data, so the map shows through instead of black edges
    write_rgb(scene_dir / "after_aligned.png", np.dstack([after_al[..., :3], valid.astype(np.uint8) * 255]))
    write_rgb(scene_dir / "overlay.png", overlay(before_w, new, valid))

    out = {
        "scene": scene_id,
        "name": meta.get("name", scene_id),
        "bounds": meta["bounds"],
        "gsd_m": gsd,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alignment": align_info,
        "stats": {
            "new_water_m2": round(float(new.sum() * px_m2), 1),
            "pre_existing_water_m2": round(float(before_w.sum() * px_m2), 1),
            "issues": len(issues),
        },
        "images": {
            "before": f"{scene_id}/before.png",
            "after": f"{scene_id}/after_aligned.png",
            "overlay": f"{scene_id}/overlay.png",
        },
        "issues": issues,
    }
    (scene_dir / "detections.json").write_text(json.dumps(out, indent=2))
    return out


def road_segments(on_road: np.ndarray, cell_px: int):
    """Chop flooded road pixels into grid cells so each stretch of street is its own issue.

    Yields (mask, x, y, pixel_count); x, y is the flooded pixel nearest the cell's centre
    of mass, so the pin always sits on the water.
    """
    ys, xs = np.nonzero(on_road)
    if len(xs) == 0:
        return
    keys = (ys // cell_px) * 100_000 + (xs // cell_px)
    for k in np.unique(keys):
        sel = keys == k
        sx, sy = xs[sel], ys[sel]
        mx, my = sx.mean(), sy.mean()
        j = int(np.argmin((sx - mx) ** 2 + (sy - my) ** 2))
        seg = np.zeros_like(on_road)
        seg[sy, sx] = True
        yield seg, int(sx[j]), int(sy[j]), int(sel.sum())


def overlay(before_w, new, valid):
    h, w = new.shape
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[before_w & valid] = (40, 130, 255, 110)
    rgba[new] = (235, 50, 60, 170)
    edges = cv2.Canny(new.astype(np.uint8) * 255, 50, 150) > 0
    rgba[edges] = (255, 255, 255, 230)
    return rgba


def save_crops(iid, before, after_al, comp, bbox, out_dir: Path, pad: int = 30):
    x, y, w, h = bbox
    hh, ww = before.shape[:2]
    x0, y0 = max(int(x) - pad, 0), max(int(y) - pad, 0)
    x1, y1 = min(int(x + w) + pad, ww), min(int(y + h) + pad, hh)
    b = np.ascontiguousarray(before[y0:y1, x0:x1, :3])
    a = after_al[y0:y1, x0:x1, :3].copy()
    contours, _ = cv2.findContours(comp[y0:y1, x0:x1].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(a, contours, -1, (235, 50, 60), 2)
    scale = max(1, int(np.ceil(240 / max(b.shape[0], b.shape[1]))))
    if scale > 1:
        b = cv2.resize(b, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        a = cv2.resize(a, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    write_rgb(out_dir / f"{iid}_before.png", b)
    write_rgb(out_dir / f"{iid}_after.png", a)
    return {"before": f"{iid}_before.png", "after": f"{iid}_after.png"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene_dir", type=Path)
    ap.add_argument("--bands", choices=["rgb", "rgbn"], default="rgb",
                    help="rgbn = 4-band imagery with near-infrared; uses NDWI")
    args = ap.parse_args(argv)
    out = detect(args.scene_dir, args.bands)
    s = out["stats"]
    print(f"{out['scene']}: aligned with {out['alignment']['method']} "
          f"({out['alignment'].get('inliers', 0)} inliers)")
    print(f"  new water {s['new_water_m2']:,.0f} sq m, already-there water {s['pre_existing_water_m2']:,.0f} sq m")
    counts = {}
    for i in out["issues"]:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    print(f"  {s['issues']} issues: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
