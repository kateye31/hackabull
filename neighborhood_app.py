"""Neighborhood storm damage viewer for Streamlit."""
from __future__ import annotations

import json
import math
from io import BytesIO
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st
from PIL import Image

from clearpath import config


def satellite_url(lat: float, lon: float) -> str:
    radius = 110  # meters from the selected point
    dy = radius / 111320
    dx = radius / (111320 * max(math.cos(math.radians(lat)), 0.1))
    params = {"bbox": f"{lon-dx},{lat-dy},{lon+dx},{lat+dy}", "bboxSR": 4326,
              "imageSR": 4326, "size": "640,640", "format": "jpg", "f": "image"}
    return "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + urlencode(params)


@st.cache_data(ttl=3600, show_spinner=False)
def satellite_image(lat: float, lon: float) -> bytes:
    req = Request(satellite_url(lat, lon), headers={"User-Agent": "ClearPath neighborhood app"})
    with urlopen(req, timeout=12) as response:
        data = response.read(5_000_000)
    Image.open(BytesIO(data)).verify()
    return data


@st.cache_data(ttl=600, show_spinner=False)
def nearby(lat: float, lon: float) -> list[dict]:
    query = ("[out:json][timeout:15];("
             f'node(around:8000,{lat},{lon})[amenity~"^(shelter|hospital|fire_station)$"];'
             f'way(around:8000,{lat},{lon})[amenity~"^(shelter|hospital|fire_station)$"];'
             f'node(around:8000,{lat},{lon})[shop="hardware"];'
             f'way(around:8000,{lat},{lon})[shop="hardware"];'
             ");out center 30;")
    req = Request("https://overpass-api.de/api/interpreter", data=query.encode(),
                  headers={"User-Agent": "ClearPath neighborhood app", "Content-Type": "text/plain"})
    with urlopen(req, timeout=20) as response:
        items = json.load(response).get("elements", [])
    places = []
    for item in items:
        tags, point = item.get("tags", {}), item.get("center", item)
        if not tags.get("name") or "lat" not in point or "lon" not in point:
            continue
        km = math.hypot((point["lat"] - lat) * 111, (point["lon"] - lon) * 111 * math.cos(math.radians(lat)))
        places.append({"name": tags["name"], "type": tags.get("amenity") or tags.get("shop"),
                       "km": round(km, 1), "lat": point["lat"], "lon": point["lon"]})
    return sorted(places, key=lambda p: p["km"])[:12]


def assess(satellite: bytes | None, current: bytes, before: bytes | None, location: str) -> dict:
    if not config.GEMINI_API_KEY:
        return {"error": "Set GEMINI_API_KEY to enable AI damage assessment."}
    try:
        from google import genai
        from google.genai import types

        prompt = ("Help a resident document neighborhood storm damage. The first image, if supplied, "
                  "is satellite context at the selected coordinates and may be old. The next image is "
                  "a current outside photo. The last image, if supplied, is an older ground-level photo "
                  "of the same place. Never infer a before/after change by comparing satellite and "
                  "ground views. Identify only visible flooded houses, flooded or damaged cars, fallen "
                  "trees, blocked driveways, debris, and other visible hazards. Do not guess water depth, "
                  "hidden damage, ownership, or road safety. If an older ground photo exists, list only "
                  "changes visible between the two ground photos. Give practical next steps. Do not "
                  "identify people or license plates. Return JSON with keys summary (string), "
                  "damage_types (array), visible_evidence (array), changes_since_before (array), "
                  "next_steps (array), confidence (low/medium/high), limitations (string). "
                  f"Resident location: {location[:300]}.")
        def image_part(raw: bytes):
            image = Image.open(BytesIO(raw)).convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=88)
            return types.Part.from_bytes(data=output.getvalue(), mime_type="image/jpeg")

        parts = [prompt]
        if satellite:
            parts.append(image_part(satellite))
        parts.append(image_part(current))
        if before:
            parts.append(image_part(before))
        response = genai.Client(api_key=config.GEMINI_API_KEY).models.generate_content(
            model=config.GEMINI_MODEL, contents=parts,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1))
        return json.loads(response.text)
    except Exception as exc:
        return {"error": f"Assessment could not run: {exc}"}


def render():
    st.set_page_config(page_title="ClearPath | Neighborhood recovery", page_icon="🏘️", layout="wide")
    st.title("ClearPath")
    st.subheader("See neighborhood damage. Find nearby help.")
    st.write("Check a home, car, street, or driveway after a flood or storm. Add its coordinates and a photo taken outside.")
    with st.form("incident"):
        address = st.text_input("Location or address", placeholder="Street, neighborhood, or nearby landmark")
        a, b = st.columns(2)
        lat = a.number_input("Latitude", min_value=-90.0, max_value=90.0, value=0.0, format="%.6f")
        lon = b.number_input("Longitude", min_value=-180.0, max_value=180.0, value=0.0, format="%.6f")
        st.caption("Copy coordinates from your phone's map. Satellite imagery centers on this point.")
        photo = st.file_uploader("Current outside photo", type=["jpg", "jpeg", "png", "webp"])
        before = st.file_uploader("Older photo of the same spot (optional, for actual change detection)",
                                  type=["jpg", "jpeg", "png", "webp"])
        submitted = st.form_submit_button("Check this location", type="primary")
    if submitted:
        if not photo:
            st.error("Add a current outside photo.")
        elif lat == 0 and lon == 0:
            st.error("Enter the location coordinates from your phone's map.")
        else:
            st.session_state.incident = {"address": address, "lat": lat, "lon": lon,
                                         "photo": photo.getvalue(), "before": before.getvalue() if before else None}
            st.session_state.pop("assessment", None)
    incident = st.session_state.get("incident")
    if not incident:
        return
    lat, lon = incident["lat"], incident["lon"]
    satellite = None
    try:
        satellite = satellite_image(lat, lon)
    except Exception as exc:
        st.warning(f"Satellite imagery unavailable: {exc}")
    columns = st.columns(3)
    if satellite:
        columns[0].image(satellite, caption="Satellite context · Esri World Imagery", use_container_width=True)
    columns[0].caption("Satellite imagery may predate the storm and cannot prove a change by itself.")
    columns[1].image(incident["photo"], caption="Current outside photo", use_container_width=True)
    if incident["before"]:
        columns[2].image(incident["before"], caption="Older photo of the same spot", use_container_width=True)
    if st.button("Assess visible damage", type="primary"):
        with st.spinner("Reviewing images..."):
            st.session_state.assessment = assess(satellite, incident["photo"], incident["before"], incident["address"])
    result = st.session_state.get("assessment")
    if result:
        st.header("Damage assessment")
        if result.get("error"):
            st.info(result["error"])
        else:
            st.write(result.get("summary", ""))
            st.write("**Visible issues:** " + ", ".join(result.get("damage_types", [])))
            for item in result.get("visible_evidence", []):
                st.write("• " + item)
            if incident["before"] and result.get("changes_since_before"):
                st.write("**Changes from the older photo:**")
                for item in result["changes_since_before"]:
                    st.write("• " + item)
            st.write("**Suggested next steps:**")
            for item in result.get("next_steps", []):
                st.write("• " + item)
            st.caption(f"AI assessment · confidence: {result.get('confidence', 'unknown')} · {result.get('limitations', '')}")
    st.header("Resources near this location")
    st.caption("OpenStreetMap listings within about 8 km. Availability is unverified; contact before traveling.")
    try:
        places = nearby(lat, lon)
        if not places:
            st.info("No mapped shelters, hospitals, fire stations, or hardware stores found nearby.")
        for p in places:
            url = f"https://www.openstreetmap.org/?mlat={p['lat']}&mlon={p['lon']}#map=17/{p['lat']}/{p['lon']}"
            st.write(f"[{p['name']}]({url}) · {p['type'].replace('_', ' ').title()} · {p['km']} km away")
    except Exception:
        st.info("Nearby listings are unavailable right now. Try the links below.")
    st.markdown("[Find local help through 211](https://www.211.org/) · [Disaster assistance](https://www.disasterassistance.gov/)")
