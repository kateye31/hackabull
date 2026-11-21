"""Demo locations so the app works with no webcam (Person 1).

    python -m clearpath.demo

Creates three walkways under data/demo/<slug>/ with reference.jpg (clear),
initial.jpg (blocked), followup.jpg (clear again, different light/angle), and
registers them as locations. The app offers "Demo photo" for these locations.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config
from .store import Store

DEMO = config.DATA / "demo"
SPOTS = [
    ("Library north ramp", "cone", 11),
    ("Engineering walkway", "scooter", 23),
    ("Student union side path", "barrier", 37),
]


def demo_photo(reference_path: str | Path, phase: str) -> Path | None:
    p = Path(reference_path).parent / ("initial.jpg" if phase == "initial" else "followup.jpg")
    return p if p.exists() and p.parent.parent == DEMO else None


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
        store.add_location(name, d / "reference.jpg", f"Demo walkway (synthetic). Expected obstruction: {kind}.")
        made += 1
    return made


if __name__ == "__main__":
    print(f"added {seed()} demo locations")
