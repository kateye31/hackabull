"""One place that turns a photo into a checked report. Used by the reviewer app (app.py)
and the residents' backend (api/main.py), so both behave the same.

    photo -> (GPS -> nearest spot) -> save (EXIF stripped) -> compare with the before-storm photo
          -> damage analysis (CLIP + SegFormer equations) -> Gemini observations -> response plan
"""
from __future__ import annotations

from typing import Callable

from . import capture, config, geo, vision
from .contracts import ComparisonResult, SavedCapture
from .reporting import gemini, plan, resources
from .store import Store

RESIDENT_NOTE = "Resident: "  # prefix for a resident's note in the event history


def _noop(_msg: str):
    pass


def add_geo(store: Store, location_id: int, lat: float, lon: float) -> dict:
    """Give a spot coordinates, a before-storm satellite image and a tree-canopy estimate."""
    sat = geo.satellite_image(lat, lon, config.SATELLITE / f"loc{location_id}_{lat:.5f}_{lon:.5f}.jpg")
    canopy = geo.canopy_fraction(sat) if sat else None
    store.set_location_geo(location_id, lat, lon, str(sat) if sat else None, canopy)
    resources.fetch(lat, lon)  # warm the nearby-help cache now so reports never wait on OpenStreetMap
    return {"satellite_path": str(sat) if sat else None, "canopy": canopy}


def locate(store: Store, image_bytes: bytes, lat: float | None = None, lon: float | None = None,
           location_id: int | None = None) -> dict:
    """Which spot a report belongs to: the photo's GPS, then the phone's location, then the resident's pick."""
    locs = store.locations()
    for source, point in (("photo GPS", geo.exif_gps(image_bytes)),
                          ("phone location", (lat, lon) if lat is not None and lon is not None else None)):
        if point:
            loc, d = geo.nearest(locs, *point)
            if loc and (location_id is None or loc["id"] == location_id):
                return {"location": loc, "matched_by": source, "distance_m": round(d), "point": point}
    if location_id is not None:
        loc = store.location(location_id)
        if loc:
            return {"location": loc, "matched_by": "resident's choice", "distance_m": None, "point": None}
    raise LookupError("Couldn't tell which spot this is. Pick it from the list.")


def save_photo(store: Store, inspection_id: str, phase: str, image_bytes: bytes) -> SavedCapture:
    return store.add_capture(capture.save_capture(image_bytes, inspection_id, phase))


def analyse(store: Store, cap: SavedCapture, reference_path: str, progress: Callable[[str], None] = _noop):
    progress("Comparing with the before-storm photo")
    overlay = config.OVERLAYS / cap.inspection_id / f"{cap.phase}_{cap.capture_id}.png"
    from .satellite import site_meta  # Person 3's aerial sites (Esri before / NOAA after)
    result: ComparisonResult = vision.compare(reference_path, cap.image_path, overlay,
                                              aerial=site_meta(reference_path) is not None)
    store.save_comparison(cap.capture_id, result)
    if cap.phase == "initial":
        progress("Asking Gemini what it sees")
        store.save_observation(cap.capture_id, gemini.observe(reference_path, cap.image_path, result.to_dict()))
        progress("Finding crews and resources nearby")
        refresh_plan(store, cap.inspection_id)
    return result


def refresh_plan(store: Store, inspection_id: str) -> dict:
    p = plan.make_plan(store.bundle(inspection_id))
    store.save_plan(inspection_id, p)
    return p


def new_report(store: Store, location_id: int, image_bytes: bytes, note: str = "",
               located: dict | None = None) -> tuple[str, SavedCapture]:
    """Open an inspection for a resident's photo and save it (analysis runs separately)."""
    iid = store.new_inspection(location_id)
    if note.strip():
        store.set_status(iid, "captured", RESIDENT_NOTE + note.strip()[:1000])
    if located and located.get("matched_by") != "resident's choice":
        store.set_status(iid, "captured", f"Placed by {located['matched_by']}, {located['distance_m']} m from the spot")
    return iid, save_photo(store, iid, "initial", image_bytes)


def add_after_aerial(store: Store, location_id: int, image_bytes: bytes, synthetic: bool = False) -> dict:
    """An after-storm aerial (NOAA post-storm flight or a drone photo taken straight down) for a spot,
    compared with its before-storm satellite image."""
    from .vision import aerial
    loc = store.location(location_id)
    if not loc or not loc.get("satellite_path"):
        raise LookupError("This spot has no before-storm satellite image to compare with.")
    dest = config.SATELLITE / f"loc{location_id}_after.jpg"
    capture._to_jpeg(image_bytes, dest)  # strips EXIF like every other photo
    result = aerial.compare_aerial(loc["satellite_path"], dest, config.OVERLAYS / f"aerial_loc{location_id}.png")
    result["synthetic"] = synthetic  # drawn demo damage, never real imagery: always labelled in the UI
    store.set_aerial(location_id, str(dest), result)
    return result
