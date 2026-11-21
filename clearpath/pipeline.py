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
    aerial_site = site_meta(reference_path) is not None
    street = aerial_site and _is_street_photo(cap.image_path)
    if street:  # a resident's street photo can't be compared pixel-for-pixel with an aerial before-image
        result = _street_photo_result(cap, overlay)
    else:
        result = vision.compare(reference_path, cap.image_path, overlay, aerial=aerial_site)
    store.save_comparison(cap.capture_id, result)
    if cap.phase == "initial":
        progress("Asking Gemini what it sees")
        store.save_observation(cap.capture_id, gemini.observe(
            reference_path, cap.image_path, None if street else result.to_dict(),
            imagery={} if street else None))  # {} = ground prompt even at an aerial site
        progress("Finding crews and resources nearby")
        refresh_plan(store, cap.inspection_id)
    return result


def _is_street_photo(path) -> bool:
    from .vision import ml
    from .vision.align import load_rgb
    if not ml.enabled():
        return False
    try:
        return ml.is_street_photo(load_rgb(path))
    except ml.MLUnavailable:
        return False


def _street_photo_result(cap: SavedCapture, overlay) -> ComparisonResult:
    """No pixel comparison possible: keep the photo, suggest the damage type, let the reviewer judge."""
    import shutil
    from .vision import ml
    from .vision.align import load_rgb
    overlay.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cap.image_path, overlay)
    dmg = {"available": False, "street": True,
           "reason": "Street photo at a spot that only has an aerial before-image, so there's nothing to measure "
                     "it against. The damage type is a suggestion from the photo alone."}
    try:
        sugg = ml.classify_damage(load_rgb(cap.image_path))
        dmg["suggestions"] = sugg
        dmg["likely_type"] = next((x["type"] for x in sugg if x["type"] != "None"), None)
    except ml.MLUnavailable:
        pass
    return ComparisonResult(method="none", score=0.0, changed_fraction=0.0, largest_region=0.0, verdict="uncertain",
                            overlay_path=overlay, aligned=False,
                            details={"alignment": {"aligned": False, "inliers": 0,
                                                   "reason": "street photo vs aerial before-image"},
                                     "damage": dmg})


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
