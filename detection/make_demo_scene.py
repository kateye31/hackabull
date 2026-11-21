"""Generate a synthetic before/after neighborhood so the whole pipeline runs offline.

The scene has roads, houses, trees, a pond and backyard pools. The "after" image adds
muddy floodwater over part of the streets and around some houses, scatters debris,
darkens the light (overcast), and is shifted/rotated a little so alignment has work to do.

Ground-truth masks are written in the BEFORE image's pixel frame, so evaluate.py can
score the detector after alignment.

    python -m detection.make_demo_scene            # writes data/scenes/demo/
    python -m detection.make_demo_scene --out data/scenes/demo2 --seed 7
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

W, H = 800, 600
GSD_M = 0.5  # metres per pixel -> scene is 400 m x 300 m

# Rough residential block near Tampa, FL (Hackabull is at USF). North-up.
SOUTH, WEST = 27.9600, -82.4600
NORTH = SOUTH + (H * GSD_M) / 111_000
EAST = WEST + (W * GSD_M) / (111_000 * np.cos(np.radians(SOUTH)))

GRASS = (96, 140, 70)
ROAD = (122, 122, 120)
ROOFS = [(72, 72, 78), (98, 92, 104), (165, 82, 62), (140, 136, 128)]
TREE = (42, 92, 44)
POOL = (64, 184, 214)
POND = (40, 82, 92)
MUD = (128, 104, 70)


def _noise(rng, shape, sigma, blur=0):
    n = rng.normal(0, sigma, shape).astype(np.float32)
    if blur:
        n = cv2.GaussianBlur(n, (0, 0), blur)
    return n


def _fill(img, mask, color, rng, sigma):
    region = np.zeros_like(img, dtype=np.float32)
    region[:] = color
    region += _noise(rng, img.shape, sigma)
    img[mask] = region[mask]


def build(seed: int = 3):
    rng = np.random.default_rng(seed)
    img = np.zeros((H, W, 3), np.float32)
    img[:] = GRASS
    img += _noise(rng, img.shape, 14, blur=0.8)

    roads = np.zeros((H, W), np.uint8)
    cv2.rectangle(roads, (0, 280), (W, 310), 1, -1)    # Main St (east-west)
    cv2.rectangle(roads, (380, 0), (410, H), 1, -1)    # Bay Ave (north-south)
    cv2.rectangle(roads, (0, 500), (W, 525), 1, -1)    # Palm St (east-west)

    trees = np.zeros((H, W), np.uint8)
    for _ in range(70):
        cv2.circle(trees, (int(rng.integers(0, W)), int(rng.integers(0, H))), int(rng.integers(7, 14)), 1, -1)
    trees[roads > 0] = 0

    buildings = np.zeros((H, W), np.uint8)
    roof_color = {}
    xs = [20, 110, 200, 290, 430, 520]
    rows = [(212, 262), (328, 378), (440, 488)]
    bid = 0
    for (y0, y1) in rows:
        for x in xs:
            bid += 1
            cv2.rectangle(buildings, (x, y0), (x + 55, y1), bid, -1)
            roof_color[bid] = ROOFS[int(rng.integers(0, len(ROOFS)))]
    # Two more houses at the east end of the block
    for x in (620, 710):
        bid += 1
        cv2.rectangle(buildings, (x, 330), (x + 50, 376), bid, -1)
        roof_color[bid] = ROOFS[int(rng.integers(0, len(ROOFS)))]

    pond = np.zeros((H, W), np.uint8)
    cv2.ellipse(pond, (650, 110), (90, 50), 10, 0, 360, 1, -1)

    pools = np.zeros((H, W), np.uint8)
    for x in (30, 210, 300, 440):
        cv2.rectangle(pools, (x + 10, 180), (x + 30, 196), 1, -1)
    for x in (120, 530):
        cv2.rectangle(pools, (x + 12, 392), (x + 32, 406), 1, -1)

    trees[(buildings > 0) | (pond > 0) | (pools > 0)] = 0

    _fill(img, trees > 0, TREE, rng, 10)
    _fill(img, roads > 0, ROAD, rng, 4)
    # dashed centre lines
    for x in range(0, W, 40):
        cv2.line(img, (x, 295), (x + 18, 295), (205, 200, 170), 1)
        cv2.line(img, (x, 512), (x + 18, 512), (205, 200, 170), 1)
    for y in range(0, H, 40):
        cv2.line(img, (395, y), (395, y + 18), (205, 200, 170), 1)
    for b, c in roof_color.items():
        _fill(img, buildings == b, c, rng, 3)
    _fill(img, pond > 0, POND, rng, 2)
    _fill(img, pools > 0, POOL, rng, 2)

    before = np.clip(img, 0, 255).astype(np.uint8)

    # ---- the storm ----
    flood_field = np.zeros((H, W), np.float32)
    for (cx, cy, ax, ay) in [(395, 420, 70, 170), (190, 300, 150, 45), (250, 520, 130, 40), (600, 300, 60, 25)]:
        blob = np.zeros((H, W), np.uint8)
        cv2.ellipse(blob, (cx, cy), (ax, ay), 0, 0, 360, 1, -1)
        flood_field += blob
    flood_field = cv2.GaussianBlur(flood_field, (0, 0), 12) + _noise(rng, (H, W), 0.35, blur=9)
    flood = (flood_field > 0.45) & (buildings == 0)  # roofs stay above the water
    flood &= ~((pond > 0) | (pools > 0))
    flood = cv2.morphologyEx(flood.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0

    after = before.astype(np.float32)
    _fill(after, flood, MUD, rng, 2.5)

    # debris: textured grey/brown patches (not water)
    for _ in range(14):
        x, y = int(rng.integers(20, W - 40)), int(rng.integers(20, H - 40))
        patch = after[y:y + 14, x:x + 22]
        patch[:] = rng.integers(60, 170, patch.shape)

    after *= 0.93  # overcast
    after = np.clip(after, 0, 255).astype(np.uint8)

    # the after capture is not perfectly lined up with the before capture
    m = cv2.getRotationMatrix2D((W / 2, H / 2), 0.6, 1.0)
    m[:, 2] += (6, -4)
    after_shot = cv2.warpAffine(after, m, (W, H), borderMode=cv2.BORDER_REFLECT)

    labels = {
        "before_water": ((pond > 0) | (pools > 0)),
        "after_water": ((pond > 0) | (pools > 0) | flood),
        "new_water": flood,
    }
    return before, after_shot, roads > 0, buildings > 0, labels


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/scenes/demo")
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args(argv)

    out = Path(args.out)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    before, after, roads, buildings, labels = build(args.seed)

    def save(name, arr):
        if arr.dtype == bool:
            arr = arr.astype(np.uint8) * 255
        elif arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(out / name), arr)

    save("before.png", before)
    save("after.png", after)
    save("roads.png", roads)
    save("buildings.png", buildings)
    for k, v in labels.items():
        save(f"labels/{k}.png", v)

    meta = {
        "name": "Demo neighborhood (synthetic)",
        "bounds": [[SOUTH, WEST], [NORTH, EAST]],
        "gsd_m": GSD_M,
        "storm": "Synthetic hurricane",
        "synthetic": True,
    }
    (out / "scene.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote synthetic scene to {out}")


if __name__ == "__main__":
    main()
