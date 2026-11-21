"""Leaflet map of the neighborhood for the reviewer app (Person 1).

Every spot is a pin coloured by its most urgent open report; nearby help from OpenStreetMap is a
second layer; the base map switches between OpenStreetMap streets and USGS aerial imagery.
Rendered as a self-contained HTML page inside Streamlit (no extra Python dependency).
"""
from __future__ import annotations

import json

from .contracts import STATUS_LABELS
from .geo import tree_risk
from .reporting import resources

# most urgent first; the pin shows the most urgent open report at that spot
URGENCY = ["still_blocked", "captured", "reviewed", "reported", "resolved", "dismissed"]
COLOR = {
    "still_blocked": "#b3261e", "captured": "#b3261e",   # needs a reviewer now
    "reviewed": "#c25e00",                               # ready to report
    "reported": "#b88a00",                               # awaiting cleanup
    "resolved": "#2e7d32",                               # cleared
    "dismissed": "#6b7177", None: "#6b7177",             # nothing open
}
LEGEND = [("#b3261e", "Needs review / still blocked"), ("#c25e00", "Ready to report"),
          ("#b88a00", "Awaiting cleanup"), ("#2e7d32", "Cleared"), ("#6b7177", "No reports")]
HELP_CATS = ("hospital", "shelter", "fire", "hardware", "tree_service", "builder", "plumber", "electrician", "waste")


def _spot_status(reports: list[dict]) -> str | None:
    if not reports:
        return None
    return min((r["status"] for r in reports), key=URGENCY.index)


def map_data(locations: list[dict], inspections: list[dict]) -> dict:
    by_loc: dict[int, list[dict]] = {}
    for i in inspections:
        by_loc.setdefault(i["location_id"], []).append(i)
    spots, help_, seen = [], [], set()
    for l in locations:
        if l.get("lat") is None:
            continue
        reps = by_loc.get(l["id"], [])
        status = _spot_status(reps)
        spots.append({
            "name": l["name"], "lat": l["lat"], "lon": l["lon"], "color": COLOR[status],
            "status": STATUS_LABELS[status] if status else "No reports",
            "reports": [f"{r['id']}: {STATUS_LABELS[r['status']]}" for r in reps[:5]],
            "canopy": None if l.get("canopy") is None else f"{l['canopy']:.0%} tree canopy, storm risk {tree_risk(l['canopy'])}",
        })
        els = resources.cached(l["lat"], l["lon"])
        if els:
            near = resources.nearby(l["lat"], l["lon"], list(HELP_CATS), per_category=2, elements=els)
            for cat, places in near["by_category"].items():
                for p in places:
                    if p["osm_url"] not in seen:
                        seen.add(p["osm_url"])
                        help_.append({"name": p["name"], "what": p["category_label"], "lat": p["lat"],
                                      "lon": p["lon"], "phone": p["phone"]})
    return {"spots": spots, "help": help_, "legend": LEGEND}


def leaflet_html(data: dict, height: int = 460) -> str:
    payload = json.dumps(data).replace("</", "<\\/")  # safe inside <script>
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  html, body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #16181a; }}
  #map {{ height: {height - 4}px; border: 1px solid #c9cdc6; border-radius: 10px; }}
  .pin {{ width: 20px; height: 20px; border-radius: 50%; border: 3px solid #fff; box-shadow: 0 1px 5px rgb(0 0 0 / .45); }}
  .help {{ width: 12px; height: 12px; border-radius: 3px; background: #fff; border: 2px solid #16181a; }}
  .legend {{ background: #fff; padding: 8px 10px; border-radius: 8px; box-shadow: 0 1px 5px rgb(0 0 0 / .3); font-size: 12px; line-height: 1.6; }}
  .legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }}
  .legend b {{ display: inline-block; width: 8px; height: 8px; border: 2px solid #16181a; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }}
  .off {{ padding: 16px; color: #464c52; }}
</style></head><body><div id="map"></div>
<script>
const D = {payload};
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[c]));
if (!window.L || !D.spots.length) {{
  document.getElementById("map").outerHTML = '<p class="off">' + (window.L ? "No spots have map coordinates yet." : "Map unavailable offline.") + "</p>";
}} else {{
  const base = {{
    "Streets": L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{maxZoom: 19, attribution: "© OpenStreetMap contributors"}}),
    "Satellite": L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{{z}}/{{y}}/{{x}}",
                             {{maxNativeZoom: 16, maxZoom: 19, attribution: "Imagery: USGS The National Map"}}),
  }};
  const map = L.map("map", {{ layers: [base.Streets], scrollWheelZoom: false }});
  const spots = L.layerGroup().addTo(map), help = L.layerGroup().addTo(map);
  const icon = (html, size) => L.divIcon({{ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] }});
  for (const s of D.spots) {{
    const pop = `<strong>${{esc(s.name)}}</strong><br>${{esc(s.status)}}` +
      (s.reports.length ? "<br>" + s.reports.map(esc).join("<br>") : "") + (s.canopy ? `<br><em>${{esc(s.canopy)}}</em>` : "");
    L.marker([s.lat, s.lon], {{ icon: icon(`<div class="pin" style="background:${{s.color}}"></div>`, 20), title: s.name, zIndexOffset: 1000 }})
      .addTo(spots).bindPopup(pop).bindTooltip(esc(s.name));
  }}
  for (const h of D.help) {{
    L.marker([h.lat, h.lon], {{ icon: icon('<div class="help"></div>', 12), title: h.name }})
      .addTo(help).bindPopup(`<strong>${{esc(h.name)}}</strong><br>${{esc(h.what)}}` + (h.phone ? `<br>${{esc(h.phone)}}` : ""));
  }}
  L.control.layers(base, {{ "Reported spots": spots, "Nearby help (OpenStreetMap)": help }}).addTo(map);
  const legend = L.control({{ position: "bottomleft" }});
  legend.onAdd = () => {{
    const d = L.DomUtil.create("div", "legend");
    d.innerHTML = D.legend.map(([c, t]) => `<i style="background:${{c}}"></i>${{esc(t)}}`).join("<br>") + "<br><b></b>Nearby help";
    return d;
  }};
  legend.addTo(map);
  map.fitBounds(L.latLngBounds(D.spots.map((s) => [s.lat, s.lon])).pad(0.35), {{ maxZoom: 17 }});
}}
</script></body></html>"""
