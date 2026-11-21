"""ReTrace web server: crew map, resident report form, JSON API.

    python -m app.server               # http://localhost:5000  (crew map)
                                       # http://localhost:5000/report  (resident form)
    python -m app.server --reset       # wipe issues and reload detections

On startup every data/scenes/*/detections.json is loaded, so run detection first.

API
    GET   /api/scenes            scene bounds + image URLs for the map layers
    GET   /api/issues            all issues with priority, next steps, cost (sorted)
    POST  /api/reports           resident report (multipart form, see report.html)
    PATCH /api/issues/<id>       {"status": "Verified"} / {"affected_sqft": 650} / {"note": "..."}
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from . import priority
from .db import DB, now

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCENES = DATA / "scenes"
UPLOADS = DATA / "uploads"
STATIC = Path(__file__).resolve().parent / "static"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
db: DB


def load_scenes(scenes_dir: Path) -> list[dict]:
    scenes = []
    for f in sorted(scenes_dir.glob("*/detections.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        added = sum(db.upsert_detection(i, d["scene"], d["generated_at"]) for i in d["issues"])
        scenes.append({k: d[k] for k in ("scene", "name", "bounds", "images", "stats", "generated_at")})
        print(f"scene {d['scene']}: {len(d['issues'])} detections ({added} new)")
    return scenes


def enrich(issue: dict) -> dict:
    out = {**issue, **priority.compute(issue)}
    if issue.get("crops"):
        out["crops"] = {k: f"/scenes/{v}" for k, v in issue["crops"].items()}
    if issue.get("photo"):
        out["photo"] = f"/uploads/{issue['photo']}"
    return out


# ---------- pages ----------

@app.get("/")
def crew_page():
    return send_from_directory(STATIC, "index.html")


@app.get("/report")
def report_page():
    return send_from_directory(STATIC, "report.html")


@app.get("/static/<path:p>")
def static_files(p):
    return send_from_directory(STATIC, p)


@app.get("/scenes/<path:p>")
def scene_files(p):
    return send_from_directory(SCENES, p)


@app.get("/uploads/<path:p>")
def upload_files(p):
    return send_from_directory(UPLOADS, p)


# ---------- api ----------

@app.get("/api/scenes")
def api_scenes():
    scenes = []
    for s in app.config["SCENES"]:
        scenes.append({**s, "images": {k: f"/scenes/{v}" for k, v in s["images"].items()}})
    return jsonify(scenes)


@app.get("/api/meta")
def api_meta():
    return jsonify({
        "categories": priority.CATEGORIES,
        "depths": priority.DEPTH_LABELS,
        "statuses": priority.STATUSES,
    })


@app.get("/api/issues")
def api_issues():
    items = [enrich(i) for i in db.all()]
    items.sort(key=priority.sort_key)
    return jsonify(items)


@app.post("/api/reports")
def api_report():
    f = request.form
    try:
        lat, lon = float(f["lat"]), float(f["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Drop a pin on the map first."}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "That location is off the map."}), 400
    category = f.get("category", "standing_water")
    if category not in priority.CATEGORIES:
        return jsonify({"error": "Unknown category."}), 400
    depth = f.get("depth") or None
    if depth and depth not in priority.DEPTH_LABELS:
        return jsonify({"error": "Unknown depth."}), 400
    moving = {"moving": 1, "still": 0}.get(f.get("flow", ""))

    photo_name = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        ext = Path(photo.filename).suffix.lower()
        if ext not in PHOTO_TYPES:
            return jsonify({"error": "Photo must be an image."}), 400
        UPLOADS.mkdir(parents=True, exist_ok=True)
        photo_name = f"{uuid.uuid4().hex}{ext}"
        photo.save(UPLOADS / photo_name)

    iid = db.next_resident_id()
    db.insert({
        "id": iid,
        "source": "resident",
        "category": category,
        "lat": lat,
        "lon": lon,
        "depth": depth,
        "moving": moving,
        "blocks_road": category == "flooded_road" or f.get("blocks_road") == "on",
        "note": (f.get("note") or "").strip()[:500] or None,
        "photo": photo_name,
        "created_at": now(),
    })
    return jsonify(enrich(db.get(iid))), 201


@app.patch("/api/issues/<iid>")
def api_update(iid):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "status" in body:
        if body["status"] not in priority.STATUSES:
            return jsonify({"error": f"status must be one of {priority.STATUSES}"}), 400
        fields["status"] = body["status"]
    if "affected_sqft" in body:
        try:
            v = float(body["affected_sqft"]) if body["affected_sqft"] not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"error": "affected_sqft must be a number"}), 400
        if v is not None and not (0 < v < 100_000):
            return jsonify({"error": "affected_sqft out of range"}), 400
        fields["affected_sqft"] = v
    if "note" in body:
        fields["note"] = (str(body["note"]).strip()[:500]) or None
    updated = db.update(iid, fields)
    if not updated:
        abort(404)
    return jsonify(enrich(updated))


def create(db_path: Path = DATA / "retrace.db", reset: bool = False, scenes_dir: Path = SCENES) -> Flask:
    global db
    db = DB(db_path)
    if reset:
        db.reset()
    app.config["SCENES"] = load_scenes(scenes_dir)
    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to let phones on your Wi-Fi open /report")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--reset", action="store_true", help="delete all issues, then reload detections")
    args = ap.parse_args(argv)
    create(reset=args.reset).run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
