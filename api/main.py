"""ClearPath residents' backend (Person 1): a separate website connected to the reviewer app.

    uvicorn api.main:app --port 8000          # residents open http://localhost:8000
    streamlit run app.py                      # the reviewer app, same database

Residents send one photo, an optional note and their location. The report lands in the same
SQLite database the reviewer app reads, and is analysed in the background (comparison with the
before-storm photo, damage equations, Gemini, nearby resources). Residents never see other
people's photos or notes; a report's public status shows only its state and nearby help.
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from clearpath import config, pipeline
from clearpath.contracts import SavedCapture
from clearpath.store import Store

MAX_BYTES = 15 * 1024 * 1024
WEB = config.ROOT / "web"
PUBLIC_HELP = ("shelter", "hospital", "hardware", "fire")  # what a resident sees after sending
# what residents see for each status (the reviewer app uses contracts.STATUS_LABELS)
RESIDENT_STATUS = {
    "captured": "Photo checked. Waiting for a reviewer.",
    "reviewed": "A reviewer confirmed it.",
    "reported": "Sent to the city. Waiting for cleanup.",
    "resolved": "Cleared. Thank you!",
    "still_blocked": "Still blocked. The city has been told again.",
    "dismissed": "Closed by a reviewer.",
}

app = FastAPI(title="ClearPath API", version="0.2",
              description="Residents report storm damage; the reviewer app (Streamlit) works the same database.")
config.ensure_dirs()
_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def _public_location(l: dict) -> dict:
    return {"id": l["id"], "name": l["name"], "lat": l.get("lat"), "lon": l.get("lon"),
            "before_url": f"/api/locations/{l['id']}/before.jpg",
            "satellite_url": f"/api/locations/{l['id']}/satellite.jpg" if l.get("satellite_path") else None}


@app.get("/api/health")
def health():
    return {"ok": True, "locations": len(store().locations())}


@app.get("/api/locations")
def locations():
    return [_public_location(l) for l in store().locations()]


def _location_file(location_id: int, key: str) -> FileResponse:
    l = store().location(location_id)
    path = l and l.get(key)
    if not path or not Path(path).exists():
        raise HTTPException(404, "No image for this spot.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/locations/{location_id}/before.jpg")
def before_photo(location_id: int):
    return _location_file(location_id, "reference_path")


@app.get("/api/locations/{location_id}/satellite.jpg")
def satellite_photo(location_id: int):
    return _location_file(location_id, "satellite_path")


def _analyse(cap: SavedCapture, reference_path: str):
    try:
        pipeline.analyse(store(), cap, reference_path)
    except Exception as e:  # keep the report; the reviewer can re-check the photo
        store().set_status(cap.inspection_id, "captured", f"Automatic check failed: {e}"[:300])


@app.post("/api/reports", status_code=201)
async def create_report(background: BackgroundTasks, photo: UploadFile = File(...), note: str = Form(""),
                        lat: float | None = Form(None), lon: float | None = Form(None),
                        location_id: int | None = Form(None)):
    data = await photo.read()
    if not data:
        raise HTTPException(400, "The photo didn't arrive. Try again.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That photo is too large (15 MB max). Try a smaller one.")
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(415, "That file isn't a photo we can read. Send a JPG or PNG.")
    try:
        located = pipeline.locate(store(), data, lat, lon, location_id)
    except LookupError as e:
        raise HTTPException(422, str(e))
    loc = located["location"]
    iid, cap = pipeline.new_report(store(), loc["id"], data, note, located)
    background.add_task(_analyse, cap, store().bundle(iid)["reference_path"])
    return {"id": iid, "location": loc["name"], "matched_by": located["matched_by"],
            "distance_m": located["distance_m"], "status_url": f"/api/reports/{iid}"}


@app.get("/api/reports/{report_id}")
def report_status(report_id: str):
    b = store().bundle(report_id)
    if not b:
        raise HTTPException(404, "No report with that number.")
    ins = b["inspection"]
    processing = not (b["initial"] and b["initial"].get("comparison"))
    help_ = []
    near = (b.get("plan") or {}).get("nearby", {})
    for cat in PUBLIC_HELP:
        for p in near.get("by_category", {}).get(cat, [])[:1]:
            help_.append({k: p.get(k) for k in ("category_label", "name", "distance_m", "phone", "address", "lat", "lon")})
    spot = {"lat": b["location"].get("lat"), "lon": b["location"].get("lon")}
    return {"id": report_id, "location": b["location"]["name"], "spot": spot, "status": ins["status"],
            "status_label": RESIDENT_STATUS[ins["status"]], "processing": processing, "nearby_help": help_}


if WEB.exists():  # the residents' website; mounted last so /api wins
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
