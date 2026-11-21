"""One command for the whole demo: build the scene, detect, score, start the app.

    python run_demo.py              # then open http://localhost:5000
    python run_demo.py --lan        # also reachable from phones on the same Wi-Fi
"""
import argparse
from pathlib import Path

from app import server
from detection import detect, evaluate, make_demo_scene

SCENE = Path("data/scenes/demo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="listen on 0.0.0.0 so phones can open /report")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--keep", action="store_true", help="keep existing issues and statuses")
    args = ap.parse_args()

    make_demo_scene.main(["--out", str(SCENE)])
    detect.main([str(SCENE)])
    evaluate.main(["scene", str(SCENE), "--out", str(SCENE / "results.md")])

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\nCrew map:        http://localhost:{args.port}/")
    print(f"Resident form:   http://localhost:{args.port}/report")
    if args.lan:
        print("On a phone: use this computer's Wi-Fi IP address instead of localhost.")
    server.create(reset=not args.keep).run(host=host, port=args.port)


if __name__ == "__main__":
    main()
