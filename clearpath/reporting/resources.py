"""Contractors and resources near a damaged spot, from OpenStreetMap (Person 3).

One Overpass query per ~1 km grid cell (searching 6 km around the cell), cached in data/resources/
and fetched when a spot is added, so a report never waits on it (a query can take 40+ s) and a demo
works on bad Wi-Fi once the neighborhood has been looked up. Each damage type maps to what it needs:

    fallen tree  -> tree service / landscaper, hardware (chainsaw, tarps), builder
    debris       -> debris drop-off / recycling, hardware, builder
    flooding     -> plumber (pumps), hardware, shelter
    downed line  -> fire station, electrician        (and 911 + the utility, always first)
    ...

Always included: the nearest hospital/clinic and shelter/community centre.
OpenStreetMap coverage varies: a missing category means "none mapped nearby", not "none exist".
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import config
from ..geo import haversine_m

OVERPASS = "https://overpass-api.de/api/interpreter"
RADIUS_M = 5000      # what we show, measured from the actual spot
QUERY_RADIUS_M = 6000  # what we fetch, around the grid cell's centre (covers any spot in the cell)
GRID_DEG = 0.01        # ~1.1 km cells: neighbouring spots share one cached query
CACHE_DAYS = 7

# key: (label people see, list of (osm_key, allowed values))
CATEGORIES = {
    "tree_service": ("Tree service / landscaper", [("craft", {"gardener", "arborist", "tree_surgeon"}),
                                                   ("shop", {"garden_centre"})]),
    "hardware": ("Hardware store (chainsaws, tarps, pumps)", [("shop", {"hardware", "doityourself", "trade"})]),
    "builder": ("Builder / roofer / contractor", [("craft", {"builder", "carpenter", "roofer", "fence_maker"}),
                                                  ("office", {"construction_company", "contractor"})]),
    "electrician": ("Electrician", [("craft", {"electrician"})]),
    "plumber": ("Plumber / pumps", [("craft", {"plumber", "hvac"})]),
    "waste": ("Debris drop-off / recycling", [("amenity", {"recycling", "waste_transfer_station"})]),
    "towing": ("Towing / car repair", [("shop", {"car_repair"})]),
    "fire": ("Fire station", [("amenity", {"fire_station"})]),
    "hospital": ("Hospital / clinic", [("amenity", {"hospital", "clinic"})]),
    "shelter": ("Shelter / community centre", [("amenity", {"community_centre"}), ("social_facility", {"shelter"}),
                                               ("emergency", {"assembly_point"})]),
    "pharmacy": ("Pharmacy", [("amenity", {"pharmacy"})]),
    "fuel": ("Fuel (generators)", [("amenity", {"fuel"})]),
}
NEEDS = {
    "Fallen tree or large branches": ["tree_service", "hardware", "builder"],
    "Storm debris pile": ["waste", "hardware", "builder"],
    "Flooding or standing water": ["plumber", "hardware", "shelter"],
    "Downed power line": ["fire", "electrician"],
    "Fallen sign, pole or fence": ["builder", "hardware"],
    "Displaced bin, vehicle or boat": ["towing", "builder"],
    "Damaged or washed-out pavement": ["builder"],
    "Other": ["hardware", "builder"],
}
ALWAYS = ["hospital", "shelter"]


def _query(lat: float, lon: float) -> str:
    keys: dict[str, set] = {}
    for _, rules in CATEGORIES.values():
        for k, vals in rules:
            keys.setdefault(k, set()).update(vals)
    parts = "".join(f'nwr(around:{QUERY_RADIUS_M},{lat:.5f},{lon:.5f})["{k}"~"^({"|".join(sorted(v))})$"];'
                    for k, v in keys.items())
    return f"[out:json][timeout:90];({parts});out center tags 800;"


def _cell(lat: float, lon: float) -> tuple[float, float]:
    return round(round(lat / GRID_DEG) * GRID_DEG, 4), round(round(lon / GRID_DEG) * GRID_DEG, 4)


def _cache_path(lat: float, lon: float) -> Path:
    clat, clon = _cell(lat, lon)
    return config.RESOURCES / f"osm_{clat:.2f}_{clon:.2f}.json"


def fetch(lat: float, lon: float) -> list[dict] | None:
    """Raw OSM elements for the grid cell around a point (cached). None if offline and not cached."""
    p = _cache_path(lat, lon)
    if p.exists() and time.time() - p.stat().st_mtime < CACHE_DAYS * 86400:
        return json.loads(p.read_text(encoding="utf-8"))
    if config.OFFLINE:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    import requests
    try:
        r = requests.post(OVERPASS, data={"data": _query(*_cell(lat, lon))}, headers={"User-Agent": config.USER_AGENT},
                          timeout=120)
        r.raise_for_status()
        elements = r.json().get("elements", [])
    except Exception:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(elements), encoding="utf-8")
    return elements


def cached(lat: float, lon: float) -> list[dict] | None:
    """Cached elements only: never calls the network (for maps that must render instantly)."""
    p = _cache_path(lat, lon)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _category(tags: dict) -> str | None:
    if tags.get("amenity") == "shelter" and tags.get("shelter_type") == "public_transport":
        return None
    for key, (_, rules) in CATEGORIES.items():
        if any(tags.get(k) in vals for k, vals in rules):
            return key
    return None


def _place(e: dict, lat: float, lon: float) -> dict | None:
    tags = e.get("tags", {})
    cat = _category(tags)
    if not cat:
        return None
    plat = e.get("lat", e.get("center", {}).get("lat"))
    plon = e.get("lon", e.get("center", {}).get("lon"))
    if plat is None or plon is None:
        return None
    addr = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
    return {
        "category": cat, "category_label": CATEGORIES[cat][0],
        "name": tags.get("name") or CATEGORIES[cat][0],
        "distance_m": round(haversine_m(lat, lon, plat, plon)),
        "phone": tags.get("phone") or tags.get("contact:phone") or "",
        "website": tags.get("website") or tags.get("contact:website") or "",
        "address": addr, "lat": plat, "lon": plon, "emergency_room": tags.get("emergency") == "yes",
        "osm_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
    }


def needed_categories(damage_type: str | None) -> list[str]:
    return NEEDS.get(damage_type or "Other", NEEDS["Other"]) + ALWAYS


def nearby(lat: float, lon: float, categories: list[str], per_category: int = 3,
           elements: list[dict] | None = None) -> dict:
    """{category: [closest places]} for the categories asked for, plus a status line."""
    if elements is None:
        elements = fetch(lat, lon)
    if elements is None:
        return {"available": False, "reason": "No internet and no cached map data for this spot.", "by_category": {}}
    places = [p for p in (_place(e, lat, lon) for e in elements) if p and p["distance_m"] <= RADIUS_M]
    by_cat = {}
    for c in categories:
        # hospitals with an emergency room first, then places you can call, then distance
        hits = sorted((p for p in places if p["category"] == c),
                      key=lambda p: (c == "hospital" and not p["emergency_room"], not p["phone"], p["distance_m"]))
        hits = sorted(hits[:max(per_category * 3, 6)],
                      key=lambda p: (c == "hospital" and not p["emergency_room"], p["distance_m"]))[:per_category]
        by_cat[c] = hits
    return {"available": True, "radius_m": RADIUS_M, "source": "OpenStreetMap contributors (ODbL)",
            "by_category": by_cat, "labels": {c: CATEGORIES[c][0] for c in categories}}


def for_damage(lat: float | None, lon: float | None, damage_type: str | None) -> dict:
    if lat is None or lon is None:
        return {"available": False, "reason": "This spot has no map coordinates yet (add them on Before-storm photos).",
                "by_category": {}}
    return nearby(lat, lon, needed_categories(damage_type))
