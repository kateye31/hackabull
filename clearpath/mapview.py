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
# nearby help is grouped into four kinds so the layer reads at a glance
HELP_KIND = {"hospital": "medical", "fire": "medical", "shelter": "shelter", "hardware": "supplies",
             "waste": "supplies", "tree_service": "crews", "builder": "crews", "plumber": "crews", "electrician": "crews"}
KIND_COLOR = {"medical": "#2563eb", "shelter": "#7c3aed", "supplies": "#0f766e", "crews": "#57534e"}
KIND_LABEL = {"medical": "Hospital / fire station", "shelter": "Shelter / community centre",
              "supplies": "Hardware / debris drop-off", "crews": "Contractors"}
OPEN = {"captured", "still_blocked", "reviewed", "reported"}


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
            "open": sum(r["status"] in OPEN for r in reps),
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
                        kind = HELP_KIND.get(cat, "crews")
                        help_.append({"name": p["name"], "what": p["category_label"], "lat": p["lat"],
                                      "lon": p["lon"], "phone": p["phone"], "color": KIND_COLOR[kind]})
    return {"spots": spots, "help": help_, "legend": LEGEND,
            "kinds": [(KIND_COLOR[k], KIND_LABEL[k]) for k in KIND_COLOR]}


def leaflet_html(data: dict, height: int = 460) -> str:
    payload = json.dumps(data).replace("</", "<\\/")  # safe inside <script>
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
  html, body {{ margin: 0; font-family: "Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #16181a; }}
  #map {{ height: {height - 4}px; border-radius: 12px; box-shadow: 0 0 0 1px #d6d9d2, 0 2px 10px rgb(22 24 26 / .08); }}
  .leaflet-container {{ font: inherit; background: #eef0ea; }}
  .pin {{ width: 26px; height: 26px; border-radius: 50%; border: 3px solid #fff; box-sizing: border-box;
         box-shadow: 0 2px 6px rgb(22 24 26 / .45); display: grid; place-items: center;
         color: #fff; font-weight: 700; font-size: 12px; font-variant-numeric: tabular-nums; }}
  .pin.quiet {{ width: 18px; height: 18px; border-width: 3px; }}
  .leaflet-tooltip {{ border: 0; border-radius: 6px; padding: 4px 8px; box-shadow: 0 2px 8px rgb(22 24 26 / .2); font-size: 13px; }}
  .leaflet-popup-content-wrapper {{ border-radius: 10px; box-shadow: 0 4px 16px rgb(22 24 26 / .18); }}
  .leaflet-popup-content {{ margin: 12px 14px; font-size: 13px; line-height: 1.45; }}
  .leaflet-popup-content strong {{ font-size: 14px; }}
  .pop-status {{ display: inline-block; margin: 4px 0 2px; padding: 1px 8px; border-radius: 999px; color: #fff; font-size: 12px; font-weight: 700; }}
  .muted {{ color: #55595e; }}
  .legend, .fit {{ background: rgb(255 255 255 / .94); border-radius: 10px; box-shadow: 0 1px 6px rgb(22 24 26 / .18); }}
  .legend {{ padding: 8px 12px; font-size: 12px; line-height: 1.7; }}
  .legend h4 {{ margin: 6px 0 0; font-size: 11px; letter-spacing: .02em; color: #55595e; font-weight: 700; }}
  .legend h4:first-child {{ margin-top: 0; }}
  .legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 7px; vertical-align: -1px; box-shadow: 0 0 0 2px #fff, 0 0 0 3px #c9cdc6; }}
  .fit {{ border: 0; padding: 7px 12px; font: inherit; font-size: 13px; font-weight: 700; color: #16181a; cursor: pointer; }}
  .fit:hover {{ background: #d4f000; }}
  .fit:focus-visible {{ outline: 3px solid #16181a; outline-offset: 2px; }}
  .off {{ padding: 16px; color: #464c52; }}
</style></head><body><div id="map"></div>
<script>
const D = {payload};
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[c]));
if (!window.L || !D.spots.length) {{
  document.getElementById("map").outerHTML = '<p class="off">' + (window.L ? "No spots have map coordinates yet." : "Map unavailable offline.") + "</p>";
}} else {{
  const base = {{
    "Streets": L.tileLayer("https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png",
                           {{maxZoom: 20, subdomains: "abcd", attribution: "© OpenStreetMap contributors © CARTO"}}),
    "Satellite": L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{{z}}/{{y}}/{{x}}",
                             {{maxNativeZoom: 16, maxZoom: 19, attribution: "Imagery: USGS The National Map"}}),
  }};
  const map = L.map("map", {{ layers: [base.Streets], scrollWheelZoom: false, zoomSnap: 0.5 }});
  const spots = L.layerGroup().addTo(map), help = L.layerGroup();   // nearby help starts hidden
  const icon = (html, size) => L.divIcon({{ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] }});
  for (const s of D.spots) {{
    const pop = `<strong>${{esc(s.name)}}</strong><br><span class="pop-status" style="background:${{s.color}}">${{esc(s.status)}}</span>` +
      (s.reports.length ? "<br>" + s.reports.map(esc).join("<br>") : "") + (s.canopy ? `<br><span class="muted">${{esc(s.canopy)}}</span>` : "");
    const html = s.open ? `<div class="pin" style="background:${{s.color}}">${{s.open}}</div>` : `<div class="pin quiet" style="background:${{s.color}}"></div>`;
    L.marker([s.lat, s.lon], {{ icon: icon(html, s.open ? 26 : 18), title: s.name, zIndexOffset: s.open ? 2000 : 1000, riseOnHover: true }})
      .addTo(spots).bindPopup(pop).bindTooltip(esc(s.name), {{ direction: "top", offset: [0, -12] }});
  }}
  for (const h of D.help) {{
    L.circleMarker([h.lat, h.lon], {{ radius: 5, color: "#fff", weight: 2, fillColor: h.color, fillOpacity: 1 }})
      .addTo(help).bindPopup(`<strong>${{esc(h.name)}}</strong><br>${{esc(h.what)}}` +
        (h.phone ? `<br>${{esc(h.phone)}} <span class="muted">(from OpenStreetMap)</span>` : ""));
  }}
  L.control.layers(base, {{ "Reported spots": spots, "Nearby help (OpenStreetMap)": help }}, {{ collapsed: true }}).addTo(map);
  const legend = L.control({{ position: "bottomleft" }});
  legend.onAdd = () => {{
    const d = L.DomUtil.create("div", "legend");
    const row = ([c, t]) => `<i style="background:${{c}}"></i>${{esc(t)}}`;
    d.innerHTML = "<h4>Spots</h4>" + D.legend.map(row).join("<br>") +
      '<div id="help-legend" hidden><h4>Nearby help</h4>' + D.kinds.map(row).join("<br>") + "</div>";
    return d;
  }};
  legend.addTo(map);
  map.on("overlayadd overlayremove", (e) => {{
    if (e.layer === help) document.getElementById("help-legend").hidden = e.type === "overlayremove";
  }});
  const all = L.latLngBounds(D.spots.map((s) => [s.lat, s.lon]));
  const open = D.spots.filter((s) => s.open);
  const focus = open.length ? L.latLngBounds(open.map((s) => [s.lat, s.lon])) : all;
  map.fitBounds(focus.pad(0.5), {{ maxZoom: 15 }});
  if (open.length && open.length < D.spots.length) {{
    const fit = L.control({{ position: "topright" }});
    fit.onAdd = () => {{
      const b = L.DomUtil.create("button", "fit");
      b.type = "button"; b.textContent = "Show all spots";
      L.DomEvent.disableClickPropagation(b);
      b.onclick = () => {{
        const showingAll = b.textContent === "Show open reports";
        map.fitBounds((showingAll ? focus : all).pad(showingAll ? 0.5 : 0.15), {{ maxZoom: 15 }});
        b.textContent = showingAll ? "Show all spots" : "Show open reports";
      }};
      return b;
    }};
    fit.addTo(map);
  }}
}}
</script></body></html>"""
