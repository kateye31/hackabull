"""Check the demo laptop before presenting (Person 1).

    python -m clearpath.preflight            # everything except a live Gemini call
    python -m clearpath.preflight --gemini   # also send one demo pair to Gemini
    python -m clearpath.preflight --no-camera

Run it on the laptop you'll present on, in the room, on the room's Wi-Fi, with
the browser closed (Windows lets only one app use the camera at a time).
Exit code 1 if anything would break the demo.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
import time
from pathlib import Path

OK, WARN, FAIL = "ok  ", "warn", "FAIL"
results: list[str] = []


def line(status: str, what: str, detail: str = ""):
    results.append(status)
    print(f"[{status}] {what}" + (f": {detail}" if detail else ""), flush=True)


def check_packages():
    for mod, need in (("streamlit", True), ("cv2", True), ("numpy", True), ("PIL", True),
                      ("torch", False), ("transformers", False), ("google.genai", False)):
        try:
            m = importlib.import_module(mod)
            line(OK, f"import {mod}", getattr(m, "__version__", ""))
        except ImportError as e:
            line(FAIL if need else WARN, f"import {mod}", f"{e}. pip install -r requirements.txt")


def check_data():
    from . import config
    try:
        config.ensure_dirs()
        probe = config.DATA / ".preflight"
        probe.write_text("ok")
        probe.unlink()
        line(OK, "data folder writable", str(config.DATA))
    except OSError as e:
        line(FAIL, "data folder writable", f"{config.DATA}: {e}")


def check_vision():
    from . import config, vision
    from evaluation.make_synthetic import obstacle, recapture, scene
    import cv2
    import numpy as np

    t = time.perf_counter()
    if vision.dino.available():
        line(OK, "DINOv2 loads", f"{config.DINO_MODEL} in {time.perf_counter() - t:.1f}s (cached now, no Wi-Fi needed)")
        method = "dinov2"
    else:
        reason = ""
        try:
            vision.dino._model()
        except vision.dino.DinoUnavailable as e:
            reason = str(e).splitlines()[0][:160]
        line(WARN, "DINOv2 loads", f"falling back to the OpenCV baseline. {reason}")
        method = "opencv"

    from .demo import SPOTS
    _, kind, seed_ = SPOTS[0]  # same pair as the first demo location
    rng = np.random.default_rng(seed_)
    base, path = scene(rng)
    blocked = base.copy()
    obstacle(blocked, rng, path, kind)
    d = Path(tempfile.mkdtemp(prefix="clearpath-preflight-"))
    imgs = {"ref": np.clip(base, 0, 255).astype(np.uint8), "blocked": recapture(blocked, rng, hard=False),
            "clear": recapture(base, rng, hard=False)}
    for k, im in imgs.items():
        cv2.imwrite(str(d / f"{k}.jpg"), cv2.cvtColor(im, cv2.COLOR_RGB2BGR))
    for k, want in (("blocked", "obstructed"), ("clear", "clear")):
        t = time.perf_counter()
        r = vision.compare(d / "ref.jpg", d / f"{k}.jpg", d / f"{k}_overlay.png", method=method)
        secs = time.perf_counter() - t
        status = OK if r.verdict == want else WARN
        line(status, f"compare ({method}) on a {k} test pair", f"{r.verdict} in {secs:.1f}s"
             + ("" if status == OK else f", expected {want}"))
        if secs > 5:
            line(WARN, "comparison speed", f"{secs:.1f}s per photo; fill the pause with narration")


def check_models():
    """CLIP, SegFormer and RemoteCLIP: loading them here downloads and caches them before the demo."""
    from .vision import aerial, ml
    if not ml.enabled():
        line(WARN, "damage analysis models", "CLEARPATH_ML=off")
        return
    for name, load in (("CLIP damage type", ml._clip), ("SegFormer walkway", ml._seg), ("RemoteCLIP aerial", aerial._remoteclip)):
        t = time.perf_counter()
        try:
            load()
            line(OK, name, f"loaded in {time.perf_counter() - t:.1f}s (cached now)")
        except Exception as e:
            line(WARN, name, str(e).splitlines()[0][:150])


def check_services():
    from . import config
    if config.OFFLINE:
        line(WARN, "map services", "CLEARPATH_OFFLINE=1: no satellite images or nearby-help lookups")
        return
    import requests
    from .geo import IMAGERY
    from .reporting.resources import OVERPASS
    for name, url in ((IMAGERY[0][0], IMAGERY[0][1] + "?f=json"), ("OpenStreetMap Overpass", OVERPASS.replace("interpreter", "status"))):
        try:
            r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=15)
            line(OK if r.ok else WARN, name, f"HTTP {r.status_code}")
        except Exception as e:
            line(WARN, name, f"unreachable ({type(e).__name__}); cached data still works")


def check_camera():
    import cv2
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cam = cv2.VideoCapture(0, backend)
    try:
        if not cam.isOpened():
            line(WARN, "camera", "no camera opened. Close the browser/Teams/Zoom and retry, or demo with Upload/Demo photo")
            return
        frame = None
        for _ in range(10):  # first frames are often black while exposure settles
            ok, frame = cam.read()
        if frame is None:
            line(WARN, "camera", "opened but returned no frame")
        elif frame.mean() < 15:
            line(WARN, "camera", "frames are almost black: lens cover, privacy shutter, or a very dark room")
        else:
            line(OK, "camera", f"{frame.shape[1]}x{frame.shape[0]}, brightness {frame.mean():.0f}/255")
    finally:
        cam.release()


def check_gemini(live: bool):
    from . import config
    from .reporting import gemini
    if not gemini.available():
        line(WARN, "Gemini", "no GEMINI_API_KEY set; the reviewer fills details by hand")
        return
    if not live:
        line(OK, "Gemini", f"key set, model {config.GEMINI_MODEL} (add --gemini to test a real call)")
        return
    from . import demo
    from .store import Store
    spots = [l for l in Store().locations() if demo.demo_photo(l["reference_path"], "initial")]
    if not spots:
        line(WARN, "Gemini live call", "no demo location to test with; run python -m clearpath.demo first")
        return
    t = time.perf_counter()
    obs = gemini.observe(spots[0]["reference_path"], demo.demo_photo(spots[0]["reference_path"], "initial"))
    if obs.get("available"):
        line(OK, "Gemini live call", f"{time.perf_counter() - t:.1f}s, saw: {obs['obstruction_type']}")
    else:
        line(WARN, "Gemini live call", obs.get("reason", "failed"))


def check_channels():
    from .reporting import channels
    n = len(channels.verified())
    line(OK if n else WARN, "verified reporting channels", str(n) if n else
         "none; the report will say 'channel not verified' (Person 3: config/channels.json)")


def check_locations():
    from . import demo
    from .store import Store
    locs = Store().locations()
    if not locs:
        line(WARN, "locations", "none yet. Locations page > Add 3 demo locations, or python -m clearpath.demo")
        return
    real = 0
    for l in locs:
        ref = Path(l["reference_path"])
        if not ref.exists():
            line(FAIL, f"location '{l['name']}'", f"reference photo missing: {ref}")
            continue
        has = [ph for ph in ("initial", "follow_up") if demo.demo_photo(ref, ph)]
        synthetic = "synthetic" in (l["description"] or "")
        real += bool(has) and not synthetic
        line(OK, f"location '{l['name']}'", "backup demo photos: " + (", ".join(has) if has else "none (camera/upload only)"))
    if not real:
        line(WARN, "real-photo backup run", 'no real before/after-storm location with demo photos yet; '
             'python -m clearpath.demo real "<name>" <folder>')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m clearpath.preflight", description="Check the demo laptop.")
    ap.add_argument("--gemini", action="store_true", help="make one real Gemini call")
    ap.add_argument("--no-camera", action="store_true", help="skip the camera check")
    args = ap.parse_args(argv)

    check_packages()
    if FAIL in results:
        return 1
    check_data()
    check_vision()
    check_models()
    check_services()
    if not args.no_camera:
        check_camera()
    check_gemini(args.gemini)
    check_channels()
    check_locations()

    fails, warns = results.count(FAIL), results.count(WARN)
    print()
    if fails:
        print(f"{fails} problem(s) will break the demo. Fix those first.")
    elif warns:
        print(f"Demo will run. {warns} warning(s) above; decide whether each one matters for your pitch.")
    else:
        print("All clear.")
    print("Reminder: in the browser, open http://localhost:8501 (not the Network URL). "
          "Browsers only allow the camera on localhost or https.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
