"""Measure how well detection works (the "How we'll measure success" section).

1) Scene with labels (the synthetic demo, or any scene you hand-label):
       python -m detection.evaluate scene data/scenes/demo
   Needs labels/after_water.png, labels/new_water.png, labels/before_water.png
   (white = yes) in the BEFORE image frame. Reports:
     * water detection  - IoU / precision / recall of the after-storm water mask
     * new-water detection - the same for flooding only
     * normal water     - how many pools/ponds get wrongly flagged as flooding, with and
                          without the before/after comparison

2) FloodNet (post-Hurricane Harvey drone images; https://arxiv.org/abs/2012.02951):
       python -m detection.evaluate floodnet path/to/images path/to/labels --limit 10
   FloodNet has no "before" image, so this scores only the single-image water mask.
   Label pixel values are class ids; --water-classes picks which ones count as water.
   Default 3,5,8 = flooded road, water, and pool (zero-based FloodNet labels).

Add --out results.md to save a markdown table for the pitch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from . import align as align_mod
from .detect import find_new_water, read_mask, read_rgb, MIN_BLOB_M2
from .water import water_mask


def scores(pred: np.ndarray, truth: np.ndarray) -> dict:
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    return {
        "iou": tp / max(tp + fp + fn, 1),
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
    }


def flagged_bodies(flag: np.ndarray, bodies: np.ndarray, min_frac: float = 0.2):
    n, lab = cv2.connectedComponents(bodies.astype(np.uint8))
    hit = 0
    for i in range(1, n):
        body = lab == i
        if (flag & body).sum() / body.sum() >= min_frac:
            hit += 1
    return hit, n - 1


def eval_scene(scene_dir: Path) -> list[tuple[str, str]]:
    import json
    meta = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    gsd = float(meta.get("gsd_m", 0.5))
    before = read_rgb(scene_dir / "before.png")[..., :3]
    after = read_rgb(scene_dir / "after.png")[..., :3]
    shape = before.shape[:2]
    lab = {k: read_mask(scene_dir / "labels" / f"{k}.png", shape) for k in ("before_water", "after_water", "new_water")}
    if any(v is None for v in lab.values()):
        sys.exit(f"{scene_dir}/labels/ needs before_water.png, after_water.png and new_water.png")

    after_al, valid, info = align_mod.align(before, after)
    _, after_w, new = find_new_water(before, after_al, valid, min_px=int(MIN_BLOB_M2 / (gsd * gsd)))

    # Without the comparison, every water pixel in the after image would be flagged.
    naive = after_w
    w = scores(after_w & valid, lab["after_water"] & valid)
    n = scores(new, lab["new_water"] & valid)
    bodies = lab["before_water"] & valid
    hit_naive, total = flagged_bodies(naive, bodies)
    hit_cmp, _ = flagged_bodies(new, bodies)
    px_naive = int((naive & bodies).sum())
    px_cmp = int((new & bodies).sum())

    pct = lambda v: f"{v * 100:.1f}%"
    return [
        ("Alignment", f"{info['method']}, {info.get('inliers', 0)} inlier matches"),
        ("Water detection IoU (after image)", pct(w["iou"])),
        ("Water detection precision / recall", f"{pct(w['precision'])} / {pct(w['recall'])}"),
        ("New-water (flood) IoU", pct(n["iou"])),
        ("New-water precision / recall", f"{pct(n['precision'])} / {pct(n['recall'])}"),
        ("Pools/ponds wrongly flagged, after image only", f"{hit_naive} of {total}  ({px_naive * gsd * gsd:,.0f} sq m)"),
        ("Pools/ponds wrongly flagged, with before/after", f"{hit_cmp} of {total}  ({px_cmp * gsd * gsd:,.0f} sq m)"),
    ]


def eval_floodnet(img_dir: Path, label_dir: Path, water_classes, limit: int, max_side: int):
    if limit < 1 or max_side < 1:
        sys.exit("limit and max-side must be positive")
    imgs = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not imgs:
        sys.exit(f"no images in {img_dir}")
    tot = {"tp": 0, "fp": 0, "fn": 0}
    used = 0
    image_ious = []
    for p in imgs:
        label_path = next((candidate for candidate in (
            label_dir / f"{p.stem}_lab.png", label_dir / f"{p.stem}.png"
        ) if candidate.is_file()), None)
        if label_path is None:
            print(f"  skip {p.name}: no label")
            continue
        rgb = read_rgb(p)[..., :3]
        lab = cv2.imread(str(label_path), cv2.IMREAD_UNCHANGED)
        if lab is None or lab.ndim != 2 or lab.shape != rgb.shape[:2]:
            sys.exit(f"{label_path}: expected a class-ID mask matching {p.name}")
        if not np.isin(lab, np.arange(10)).all():
            sys.exit(f"{label_path}: expected FloodNet class IDs from 0 through 9")
        scale = max_side / max(rgb.shape[:2])
        if scale < 1:
            rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        lab = cv2.resize(lab, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
        truth = np.isin(lab, water_classes)
        pred = water_mask(rgb)
        tot["tp"] += int((pred & truth).sum())
        tot["fp"] += int((pred & ~truth).sum())
        tot["fn"] += int((~pred & truth).sum())
        used += 1
        s = scores(pred, truth)
        if (pred | truth).any():
            image_ious.append(s["iou"])
        print(f"  {p.name}: IoU {s['iou']:.2f}")
        if used == limit:
            break
    if not used:
        sys.exit("no matching FloodNet image and label pairs")
    tp, fp, fn = tot["tp"], tot["fp"], tot["fn"]
    pct = lambda v: f"{v * 100:.1f}%"
    return [
        ("FloodNet images scored", str(used)),
        ("Pixel counts (TP / FP / FN)", f"{tp:,} / {fp:,} / {fn:,}"),
        ("Water IoU", pct(tp / max(tp + fp + fn, 1))),
        ("Water precision / recall", f"{pct(tp / max(tp + fp, 1))} / {pct(tp / max(tp + fn, 1))}"),
        ("Mean image IoU (nonempty union)", pct(sum(image_ious) / len(image_ious)) if image_ious else "N/A"),
    ]


def as_markdown(title, rows):
    lines = [f"### {title}", "", "| Metric | Result |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("scene")
    a.add_argument("scene_dir", type=Path)
    b = sub.add_parser("floodnet")
    b.add_argument("img_dir", type=Path)
    b.add_argument("label_dir", type=Path)
    b.add_argument("--water-classes", default="3,5,8")
    b.add_argument("--limit", type=int, default=10)
    b.add_argument("--max-side", type=int, default=1500)
    for p in (a, b):
        p.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    if args.mode == "scene":
        title = f"Scene: {args.scene_dir.name}"
        rows = eval_scene(args.scene_dir)
    else:
        title = "FloodNet (single-image water mask)"
        classes = [int(c) for c in args.water_classes.split(",")]
        rows = eval_floodnet(args.img_dir, args.label_dir, classes, args.limit, args.max_side)

    md = as_markdown(title, rows)
    print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
