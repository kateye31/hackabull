"""Make synthetic before/after pairs of a neighborhood street after a hurricane, for testing and evaluation.

Each pair is a clear-path reference plus a later capture that is either
  * clear      - same path, but different light, a shadow, a slightly different
                 camera position, sensor noise (the things that fool pixel diffs)
  * obstructed - all of the above plus storm damage: a fallen tree, scattered branches,
                 a debris pile, flood water, a blown-over trash bin or sign

    python -m evaluation.make_synthetic                  # data/eval/synthetic, 40 pairs
    python -m evaluation.make_synthetic --n 80 --seed 2

Writes <out>/<pair_id>/reference.jpg, capture.jpg and <out>/labels.csv
(pair_id, label, obstruction, hard_case). Real pairs can use the same layout.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

W, H = 640, 480
# what a hurricane leaves on a neighborhood street or sidewalk
OBJECTS = ("tree", "branches", "debris", "water", "bin", "sign")
# older everyday obstacles, still drawable by name
EXTRA_OBJECTS = ("scooter", "cone", "barrier", "box")


def _noise(rng, shape, s):
    return rng.normal(0, s, shape).astype(np.float32)


def scene(rng) -> tuple[np.ndarray, np.ndarray]:
    """A street or sidewalk in perspective. Returns (image, path mask)."""
    img = np.zeros((H, W, 3), np.float32)
    horizon = int(rng.integers(150, 200))
    sky = np.array(rng.choice([(150, 190, 230), (170, 200, 225), (200, 210, 220)]), np.float32)
    img[:horizon] = sky
    # building band with windows
    bcol = np.array(rng.choice([(170, 120, 95), (190, 180, 165), (140, 140, 150)]), np.float32)
    top = horizon - int(rng.integers(60, 120))
    img[top:horizon] = bcol
    for x in range(int(rng.integers(5, 30)), W, int(rng.integers(45, 70))):
        cv2.rectangle(img, (x, top + 15), (x + 22, top + 40), (60, 75, 95), -1)
    # grass
    grass = np.array(rng.choice([(80, 130, 60), (95, 140, 70), (70, 115, 55)]), np.float32)
    img[horizon:] = grass
    img[horizon:] += cv2.GaussianBlur(_noise(rng, (H - horizon, W, 3), 22), (0, 0), 1.2)
    # street/sidewalk trapezoid
    cx = W // 2 + int(rng.integers(-60, 60))
    near_w, far_w = int(rng.integers(300, 420)), int(rng.integers(40, 80))
    poly = np.array([[cx - far_w // 2, horizon], [cx + far_w // 2, horizon],
                     [cx + near_w // 2 + 40, H], [cx - near_w // 2 - 40, H]], np.int32)
    path = np.zeros((H, W), np.uint8)
    cv2.fillPoly(path, [poly], 1)
    pcol = np.array(rng.choice([(185, 182, 175), (165, 160, 150), (200, 190, 175)]), np.float32)
    img[path > 0] = pcol
    img[path > 0] += _noise(rng, (int(path.sum()), 3), 6)
    # paver joints
    for y in range(horizon + 8, H, 1):
        if (y - horizon) % max(4, (y - horizon) // 6) == 0:
            row = path[y] > 0
            img[y, row] *= 0.85
    cv2.polylines(img, [poly], True, (120, 120, 115), 2)
    # trees and lamp posts beside the path
    for _ in range(int(rng.integers(2, 5))):
        side = rng.choice([-1, 1])
        x = cx + side * int(rng.integers(near_w // 2 + 60, near_w // 2 + 220))
        y = int(rng.integers(horizon + 10, horizon + 80))
        cv2.rectangle(img, (x - 5, y - 20), (x + 5, y + 40), (80, 60, 40), -1)
        cv2.circle(img, (x, y - 40), int(rng.integers(25, 45)), (45, 95, 45), -1)
    return img, path


def obstacle(img, rng, path, kind: str):
    ys, xs = np.nonzero(path)
    sel = ys > (ys.min() + 0.35 * (ys.max() - ys.min()))
    i = int(rng.integers(0, sel.sum()))
    x, y = int(xs[sel][i]), int(ys[sel][i])
    s = 0.5 + 1.1 * (y - ys.min()) / (ys.max() - ys.min())  # bigger when closer
    S = lambda v: int(v * s)
    if kind == "scooter":
        cv2.line(img, (x - S(40), y), (x + S(40), y), (30, 30, 30), S(8))
        cv2.line(img, (x + S(35), y), (x + S(30), y - S(90)), (40, 40, 45), S(5))
        cv2.line(img, (x + S(15), y - S(90)), (x + S(45), y - S(90)), (40, 40, 45), S(5))
        for wx in (x - S(40), x + S(40)):
            cv2.circle(img, (wx, y + S(6)), S(10), (15, 15, 15), -1)
        cv2.rectangle(img, (x - S(5), y - S(6)), (x + S(25), y + S(2)), (20, 160, 90), -1)
    elif kind == "cone":
        pts = np.array([[x, y - S(70)], [x - S(25), y], [x + S(25), y]], np.int32)
        cv2.fillPoly(img, [pts], (240, 110, 20))
        cv2.line(img, (x - S(12), y - S(35)), (x + S(12), y - S(35)), (245, 245, 245), S(7))
        cv2.rectangle(img, (x - S(32), y - S(4)), (x + S(32), y + S(4)), (220, 95, 15), -1)
    elif kind == "barrier":
        w = S(150)
        for k in range(0, w, S(25)):
            col = (240, 120, 20) if (k // max(S(25), 1)) % 2 == 0 else (245, 245, 245)
            cv2.rectangle(img, (x - w // 2 + k, y - S(55)), (x - w // 2 + k + S(25), y - S(30)), col, -1)
        for lx in (x - w // 2 + S(8), x + w // 2 - S(8)):
            cv2.line(img, (lx, y - S(55)), (lx, y), (60, 60, 60), S(5))
    elif kind == "bin":
        cv2.rectangle(img, (x - S(22), y - S(75)), (x + S(22), y), (30, 80, 50), -1)
        cv2.rectangle(img, (x - S(26), y - S(82)), (x + S(26), y - S(72)), (20, 60, 35), -1)
    elif kind == "box":
        cv2.rectangle(img, (x - S(35), y - S(45)), (x + S(35), y), (175, 135, 85), -1)
        cv2.line(img, (x - S(35), y - S(30)), (x + S(35), y - S(30)), (140, 105, 60), S(3))
    elif kind == "tree":  # fallen trunk across the path with leafy limbs
        dx = S(150)
        tilt = int(rng.integers(-S(25), S(25) + 1))
        a, b = (x - dx, y - tilt), (x + dx, y + tilt)
        for t in np.linspace(0.15, 0.9, 5):
            bx, by = int(a[0] + t * (b[0] - a[0])), int(a[1] + t * (b[1] - a[1]))
            ex, ey = bx + int(rng.integers(-S(40), S(40) + 1)), by - int(rng.integers(S(30), S(70) + 1))
            cv2.line(img, (bx, by), (ex, ey), (85, 62, 40), max(S(6), 1))
            for _ in range(4):
                cv2.circle(img, (ex + int(rng.integers(-S(18), S(18) + 1)), ey + int(rng.integers(-S(14), S(14) + 1))),
                           max(S(15), 2), (int(rng.integers(40, 70)), int(rng.integers(85, 115)), 35), -1)
        cv2.line(img, a, b, (95, 70, 45), max(S(18), 2))
    elif kind == "branches":  # scattered limbs and leaves
        for _ in range(int(rng.integers(6, 10))):
            cx, cy = x + int(rng.integers(-S(70), S(70) + 1)), y - int(rng.integers(0, S(40) + 1))
            ang = rng.uniform(0, np.pi)
            L = int(rng.integers(S(35), S(80) + 1))
            p1 = (int(cx - L * np.cos(ang) / 2), int(cy - L * np.sin(ang) / 4))
            p2 = (int(cx + L * np.cos(ang) / 2), int(cy + L * np.sin(ang) / 4))
            cv2.line(img, p1, p2, (90, 66, 42), max(S(5), 1))
            cv2.circle(img, p2, max(S(10), 2), (55, 100, 40), -1)
    elif kind == "debris":  # boards, shingles and a torn tarp
        for col in ((40, 90, 170), (165, 135, 95), (70, 70, 78), (165, 135, 95), (190, 185, 175), (70, 70, 78)):
            c = (float(x + rng.integers(-S(55), S(55) + 1)), float(y - rng.integers(0, S(35) + 1)))
            size = (float(rng.integers(S(30), S(75) + 1)), float(rng.integers(S(8), S(30) + 1)))
            box = cv2.boxPoints((c, size, float(rng.uniform(0, 180)))).astype(np.int32)
            cv2.fillPoly(img, [box], col)
    elif kind == "water":  # murky standing flood water
        m = np.zeros(img.shape[:2], np.uint8)
        cv2.ellipse(m, (x, y - S(10)), (S(140), S(40)), float(rng.uniform(-6, 6)), 0, 360, 1, -1)
        m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(s * 3, 1))[..., None]
        water = np.empty_like(img)
        water[:] = (112, 104, 82)
        water += _noise(rng, img.shape, 5)
        img[:] = img * (1 - 0.9 * m) + water * (0.9 * m)
    elif kind == "sign":
        pts = np.array([[x, y - S(80)], [x - S(28), y], [x + S(28), y]], np.int32)
        cv2.fillPoly(img, [pts], (245, 215, 40))
        glyph = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.putText(glyph, "!", (x - S(6), y - S(20)), cv2.FONT_HERSHEY_SIMPLEX, max(s, .5), 255, max(S(3), 1))
        img[glyph != 0] = (20, 20, 20)


def recapture(img, rng, hard: bool):
    """Same place, later: new light, maybe a shadow, slightly different camera."""
    out = img.copy()
    if hard:  # a long shadow across the street
        pts = np.array([[int(rng.integers(0, W)), H], [int(rng.integers(0, W)), int(H * 0.5)],
                        [int(rng.integers(0, W)), int(H * 0.45)], [int(rng.integers(0, W)), H]], np.int32)
        m = np.zeros((H, W), np.uint8)
        cv2.fillPoly(m, [cv2.convexHull(pts)], 1)
        m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 6)[..., None]
        out = out * (1 - 0.45 * m)
    gain = rng.uniform(0.75, 1.2)
    tint = rng.uniform(0.92, 1.08, 3)
    out = out * gain * tint + _noise(rng, out.shape, 4)
    ang, sc = rng.uniform(-2.5, 2.5), rng.uniform(0.96, 1.05)
    M = cv2.getRotationMatrix2D((W / 2, H / 2), ang, sc)
    M[:, 2] += rng.uniform(-14, 14, 2)
    out = cv2.warpAffine(np.clip(out, 0, 255).astype(np.uint8), M, (W, H), borderMode=cv2.BORDER_REFLECT)
    return out


def make_pair(rng, obstructed: bool, hard: bool):
    base, path = scene(rng)
    ref = np.clip(base, 0, 255).astype(np.uint8)
    later = base.copy()
    kind = ""
    if obstructed:
        kind = str(rng.choice(OBJECTS))
        obstacle(later, rng, path, kind)
    return ref, recapture(later, rng, hard), kind


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/eval/synthetic"))
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    rng = np.random.default_rng(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(args.n):
        obstructed = i % 2 == 0
        hard = (i // 2) % 2 == 1
        ref, cap, kind = make_pair(rng, obstructed, hard)
        pid = f"pair_{i:03d}"
        d = args.out / pid
        d.mkdir(exist_ok=True)
        cv2.imwrite(str(d / "reference.jpg"), cv2.cvtColor(ref, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(str(d / "capture.jpg"), cv2.cvtColor(cap, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
        rows.append({"pair_id": pid, "label": "obstructed" if obstructed else "clear",
                     "obstruction": kind, "hard_case": "shadow" if hard else ""})
    with open(args.out / "labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pair_id", "label", "obstruction", "hard_case"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} pairs to {args.out}")


if __name__ == "__main__":
    main()
