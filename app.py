"""ClearPath: after a hurricane, residents report storm damage blocking a neighborhood route; a reviewer
confirms it, reports it and confirms it was cleared.

    streamlit run app.py

Person 1 owns this file and wires in Person 2 (clearpath.vision, clearpath.store)
and Person 3 (clearpath.reporting).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

import os

from clearpath import capture, config, demo, geo, pipeline, vision
from clearpath.vision import aerial
from clearpath.contracts import (HAZARD_TYPES, OBSTRUCTION_TYPES, PHASE_LABELS, SEVERITIES, STATUS_LABELS,
                                 ReviewedDetails)
from clearpath.pipeline import RESIDENT_NOTE
from clearpath.reporting import channels, gemini, report
from clearpath.store import Store, now

st.set_page_config(page_title="ClearPath", page_icon="♿", layout="wide")
config.ensure_dirs()

VERDICT_STYLE = {
    "obstructed": ":red-background[**Obstructed**]",
    "uncertain": ":orange-background[**Uncertain: needs a human look**]",
    "clear": ":green-background[**Clear**]",
}


@st.cache_resource
def get_store() -> Store:
    return Store()


@st.cache_resource(show_spinner="Loading DINOv2 (first run downloads ~90 MB)…")
def vision_ready() -> str:
    if config.VISION_METHOD == "opencv":
        return "opencv"
    return "dinov2" if vision.dino.available() else "opencv"


store = get_store()
RESIDENT_SITE = os.environ.get("CLEARPATH_RESIDENT_URL", "http://localhost:8000")  # api/main.py
POWER_LINE_WARNING = ("**Downed power line? Stay at least 35 feet (10 m) away and call 911.** "
                      "Don't go closer to take a photo.")


# ---------------------------------------------------------------- helpers
def photo_input(key: str, reference_path: str | None = None, phase: str = "initial") -> bytes | None:
    """Camera, upload, or (for demo locations) a prepared photo. Returns image bytes once chosen."""
    options = ["Camera", "Upload"]
    demo_path = demo.demo_photo(reference_path, phase) if reference_path else None
    if demo_path:
        options.append("Demo photo")
    src = st.radio("Photo source", options, horizontal=True, key=f"{key}_src",
                   index=len(options) - 1 if demo_path else 0)
    if src == "Camera":
        f = st.camera_input("Take a photo from where the before-storm photo was taken", key=f"{key}_cam")
        return f.getvalue() if f else None
    if src == "Upload":
        f = st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png", "webp"], key=f"{key}_up")
        return f.getvalue() if f else None
    st.image(str(demo_path), caption="Demo photo", width=320)
    return demo_path.read_bytes()


def process_capture(inspection_id: str, phase: str, image_bytes: bytes, reference_path: str):
    """Save -> compare -> damage analysis -> Gemini -> response plan (clearpath/pipeline.py)."""
    with st.status("Checking the photo…", expanded=True) as s:
        st.write("Saving photo")
        cap = pipeline.save_photo(store, inspection_id, phase, image_bytes)
        pipeline.analyse(store, cap, reference_path, progress=st.write)
        s.update(label="Photo checked", state="complete")


def show_comparison(bundle: dict, phase: str):
    cap = bundle[phase]
    comp = cap["comparison"]
    c1, c2, c3 = st.columns(3)
    c1.image(bundle["reference_path"], caption="Before the storm", width="stretch")
    c2.image(cap["image_path"], caption=f"{PHASE_LABELS[phase]} photo", width="stretch")
    c3.image(comp["overlay_path"], caption="Changes highlighted", width="stretch")
    st.markdown(f"{VERDICT_STYLE[comp['verdict']]} &nbsp; about **{comp['changed_fraction']:.0%}** of the scene "
                f"changed · method **{comp['method']}**")
    with st.expander("Comparison details"):
        d = comp["details"]
        al = d["alignment"]
        st.write(f"Alignment: {'lined up with the reference' if al['aligned'] else 'not aligned'} "
                 f"({al.get('inliers', 0)} matching points{', ' + al['reason'] if al.get('reason') else ''})")
        rows = [{"Method": k, "Changed": f"{v['changed_fraction']:.1%}", "Verdict": v["verdict"]}
                for k, v in d.items() if k in ("dinov2", "opencv")]
        st.table(rows)
        if d.get("fallback"):
            st.caption(d["fallback"])


def show_damage(comp: dict):
    """CLIP damage type + SegFormer walkway equations (clearpath/vision/ml.py)."""
    dmg = comp.get("details", {}).get("damage")
    if not dmg:
        return
    if dmg.get("available") is False:
        st.caption(f"Damage analysis off: {dmg.get('reason', '')[:160]}")
        return
    st.markdown("**Damage analysis** · *machine suggestions for the reviewer*")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Walkway blocked", f"{dmg['blocked_share']:.0%}", help="B = |walkway before ∩ changed| / |walkway before|")
    c2.metric("Narrowest clear width", f"{dmg['narrowest_clear_width']:.0%}",
              help="10th percentile, over rows near the camera, of the share of each row's walkway still clear")
    c3.metric("Damage index", f"{dmg['damage_index']:.0f} / 100", help="DI = 100 · B · weight of the damage type")
    c4.metric("Suggested severity", dmg["suggested_severity"].split(":")[0])
    if dmg.get("suggestions"):
        st.caption("Looks like: " + " · ".join(f"{x['type']} ({x['score']:.0%})" for x in dmg["suggestions"]
                                               if x["type"] != "None") + f" · {dmg['models']['classifier']}")
    if dmg.get("note"):
        st.caption(dmg["note"])


def show_plan(bundle: dict):
    pl = bundle.get("plan")
    if not pl:
        return
    plan = pl["plan"]
    src = f"Gemini {pl['model']} with map tools" if pl["source"] == "gemini" else "rules (no Gemini key)"
    st.markdown(f"**Response plan** · priority **{plan['priority']}** · *draft from {src}*")
    st.write(plan["summary"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Crew:** {plan['crew']}")
        if plan["equipment"]:
            st.markdown("**Bring:** " + ", ".join(plan["equipment"]))
        for i, step in enumerate(plan["steps"], 1):
            st.write(f"{i}. {step}")
    with c2:
        for line in plan["safety"]:
            st.warning(line)
    near = pl.get("nearby", {})
    st.markdown("**Nearby help** · from OpenStreetMap")
    if not near.get("available"):
        st.caption(near.get("reason", "No map data."))
        return
    rows = []
    for cat, places in near["by_category"].items():
        for x in places:
            rows.append({"Need": near["labels"][cat], "Name": x["name"], "Distance": f"{x['distance_m'] / 1609.34:.1f} mi",
                         "Phone": x["phone"] or "", "Map": x["osm_url"]})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch",
                     column_config={"Map": st.column_config.LinkColumn("Map", display_text="open")})
    else:
        st.caption("Nothing mapped nearby for these needs.")
    st.caption(f"Map data © {near['source']}. A place missing here may still exist; OpenStreetMap coverage varies.")


def show_observation(obs: dict | None):
    if not obs:
        return
    if not obs.get("available"):
        st.info(f"No AI observations: {obs.get('reason')}")
        return
    st.markdown(f"**AI observations** · {obs['model']} · confidence {obs['confidence']} · *draft for the reviewer*")
    st.write(f"Damage: **{obs['obstruction_type']}**" + ("" if obs["path_blocked"] else " (Gemini thinks the route is clear)"))
    for o in obs["observations"]:
        st.write(f"- {o}")
    if obs.get("accessibility_impact"):
        st.write(f"Impact: {obs['accessibility_impact']}")
    if obs.get("suggested_action"):
        st.write(f"Suggested action: {obs['suggested_action']}")


# ---------------------------------------------------------------- pages
def page_locations():
    st.header("Locations")
    st.write("Each location is a neighborhood route people need after a storm: the sidewalk to the bus stop, a curb ramp, "
             "the walkway to the shelter. It needs one photo taken **before the storm**, while it's clear. Every "
             "after-storm photo there is compared against it, so take it from a spot you can find again (a hydrant, "
             "a street sign, a mailbox).")
    with st.form("new_loc", clear_on_submit=True):
        name = st.text_input("Location name", placeholder="e.g. Palm St sidewalk to the bus stop")
        desc = st.text_input("Where exactly / how to stand", placeholder="Next to the hydrant, facing the bus shelter")
        addr = st.text_input("Address or lat, lon (optional)", placeholder="e.g. 4210 N Palm St, Tampa FL  or  28.0006, -82.4594",
                             help="Used for the satellite view, matching residents' GPS, and finding help nearby. "
                                  "Left empty, the photo's own GPS is used if it has one.")
        src = st.radio("Before-storm photo", ["Camera", "Upload"], horizontal=True)
        f = st.camera_input("Before-storm photo") if src == "Camera" else st.file_uploader("Before-storm photo", type=["jpg", "jpeg", "png", "webp"])
        if st.form_submit_button("Add location", type="primary"):
            if not name.strip() or not f:
                st.error("Add a name and a before-storm photo.")
            else:
                data = f.getvalue()
                point = _parse_point(addr) or geo.exif_gps(data)
                ref = capture.save_reference(data, name)
                loc_id = store.add_location(name, ref, desc)
                if point:
                    with st.spinner("Fetching the satellite view…"):
                        pipeline.add_geo(store, loc_id, *point)
                st.success(f"Added {name}." + ("" if point else " No coordinates: add an address to put it on the map."))
    if st.button("Add demo locations (no camera needed)"):
        n = demo.seed(store)
        st.success(f"Added {n} demo locations." if n else "Demo locations already exist.")
    locs = store.locations()
    placed = [l for l in locs if l.get("lat") is not None]
    if placed:
        st.subheader("Map")
        st.map([{"lat": l["lat"], "lon": l["lon"]} for l in placed], size=25, zoom=14)
    if locs:
        cols = st.columns(3)
        for i, l in enumerate(locs):
            with cols[i % 3]:
                st.image(l["reference_path"], width="stretch")
                if l.get("satellite_path") and Path(l["satellite_path"]).exists():
                    st.image(l["satellite_path"], caption="Satellite, before the storm (USGS)", width="stretch")
                risk = geo.tree_risk(l.get("canopy"))
                st.markdown(f"**{l['name']}**  \n{l['description'] or ''}")
                if l.get("canopy") is not None:
                    st.caption(f"Tree canopy nearby: {l['canopy']:.0%} · storm risk **{risk}**")
                if l.get("satellite_path"):
                    aerial_controls(l)


def aerial_controls(l: dict):
    """After-storm aerial for one spot: upload (NOAA flight or drone, straight down) or a labelled synthetic demo."""
    with st.expander("After-storm aerial"):
        up = st.file_uploader("NOAA post-storm aerial or a drone photo taken straight down",
                              type=["jpg", "jpeg", "png"], key=f"aerial_up_{l['id']}")
        c1, c2 = st.columns(2)
        run = c1.button("Compare", key=f"aerial_go_{l['id']}", disabled=up is None)
        fake = c2.button("Demo: synthetic damage", key=f"aerial_fake_{l['id']}",
                         help="Draws storm damage onto the real before-storm tile. Synthetic, for demos only.")
        if run or fake:
            data = up.getvalue() if run else demo.synthetic_after_aerial(l["satellite_path"], seed=l["id"])
            with st.spinner("Comparing from above…"):
                l["aerial_result"] = pipeline.add_after_aerial(store, l["id"], data, synthetic=bool(fake))
                l["after_aerial_path"] = str(config.SATELLITE / f"loc{l['id']}_after.jpg")
        show_aerial(l)


def show_aerial(l: dict):
    res = l.get("aerial_result")
    if not res:
        st.caption("No after-storm aerial yet.")
        return
    c1, c2, c3 = st.columns(3)
    c1.image(l["satellite_path"], caption="Before (USGS NAIP)", width="stretch")
    c2.image(l["after_aerial_path"], caption="After · SYNTHETIC demo damage" if res.get("synthetic")
             else "After the storm", width="stretch")
    c3.image(res["overlay_path"], caption="Changed from above", width="stretch")
    st.markdown(f"{VERDICT_STYLE[res['verdict']]} &nbsp; {res['largest_region']:.0%} of the view in one changed area")
    if res.get("shift"):
        up = [(k, v) for k, v in res["shift"].items() if v > 0.05]
        if up:
            st.caption("RemoteCLIP, more like after the storm: " + ", ".join(
                f"{aerial.AERIAL_LABELS[k]} (+{v:.0%})" for k, v in up[:3]))
    elif res.get("shift_note"):
        st.caption(res["shift_note"][:160])


def _parse_point(text: str):
    """'lat, lon' or an address -> (lat, lon), or None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        a, b = (float(x) for x in text.split(","))
        return (a, b) if -90 <= a <= 90 and -180 <= b <= 180 else None
    except ValueError:
        hit = geo.geocode(text)
        return (hit[0], hit[1]) if hit else None


def page_report():
    """For residents: one photo of storm damage at a known spot. A reviewer handles the rest."""
    st.header("Report storm damage")
    st.write("Seen a fallen tree, debris or flooding blocking a street, sidewalk or walkway? Send one photo. "
             "A neighborhood reviewer checks every report before it goes to the city.")
    st.warning(POWER_LINE_WARNING)
    done = st.session_state.get("submitted")
    if done:
        st.success(f"Thanks! Report **{done}** is with the reviewer. You don't need to do anything else.")
        if st.button("Report something else"):
            st.session_state.pop("submitted")
            st.rerun()
        return
    locs = store.locations()
    if not locs:
        st.info("No neighborhood spots are set up yet. A reviewer adds them on the Locations page.")
        return
    by_name = {l["name"]: l for l in locs}
    loc = by_name[st.selectbox("Which spot is it?", list(by_name))]
    st.image(loc["reference_path"], caption="Before the storm. Take your photo from about where this was taken.", width=420)
    img = photo_input("resident", loc["reference_path"], "initial")
    note = st.text_area("What did you see? (optional)", height=80,
                        placeholder="e.g. a big branch across the sidewalk, no way past with a wheelchair")
    if img and st.button("Send report", type="primary"):
        iid, cap = pipeline.new_report(store, loc["id"], img, note)
        with st.status("Checking the photo…", expanded=True) as s:
            pipeline.analyse(store, cap, loc["reference_path"], progress=st.write)
            s.update(label="Photo checked", state="complete")
        st.session_state.submitted = iid
        st.rerun()


QUEUE = (
    ("Needs review", ("captured",)),
    ("Ready to report", ("reviewed",)),
    ("Awaiting cleanup", ("reported", "still_blocked")),
    ("Closed", ("resolved", "dismissed")),
)


def page_review():
    """For the reviewer: the queue of resident reports, then confirm -> report -> after cleanup."""
    qp = st.query_params.get("inspection")
    if qp and "iid" not in st.session_state and store.bundle(qp):
        st.session_state.iid = qp  # shareable link: ?inspection=INS-0001
    iid = st.session_state.get("iid")
    if iid and not store.bundle(iid):  # e.g. the data folder was reset
        st.session_state.pop("iid")
        iid = None
    if iid:
        st.query_params["inspection"] = iid
    elif "inspection" in st.query_params:
        del st.query_params["inspection"]
    if not iid:
        st.header("Review queue")
        items = store.inspections()
        if not items:
            st.info("No reports yet. Residents send them from the **Report damage** page "
                    "(share the link ending in `?page=report`).")
            return
        for title, statuses in QUEUE:
            group = [i for i in items if i["status"] in statuses]
            st.subheader(f"{title} ({len(group)})")
            for i in group:
                c1, c2, c3, c4 = st.columns([1.2, 2.5, 2.5, 1])
                c1.write(f"**{i['id']}**")
                c2.write(i["location_name"])
                c3.write(STATUS_LABELS[i["status"]])
                c4.button("Open", key=f"open_{i['id']}", on_click=_open, args=(i["id"],))
        return

    b = store.bundle(iid)
    ins, loc = b["inspection"], b["location"]
    top = st.columns([4, 1])
    top[0].header(f"{iid} · {loc['name']}")
    top[0].caption(STATUS_LABELS[ins["status"]])
    if top[1].button("Back to queue"):
        st.session_state.pop("iid")
        st.query_params.pop("inspection", None)  # otherwise the ?inspection= link reopens it on rerun
        st.rerun()
    resident = [e["note"][len(RESIDENT_NOTE):] for e in b["events"] if (e["note"] or "").startswith(RESIDENT_NOTE)]
    if resident:
        st.info(f"**Resident wrote:** {resident[-1]}")

    # 1. initial capture
    st.subheader("1. After-storm photo")
    if not b["initial"]:
        img = photo_input(f"{iid}_initial", b["reference_path"], "initial")
        if img and st.button("Check this photo", type="primary"):
            process_capture(iid, "initial", img, b["reference_path"])
            st.rerun()
        return
    show_comparison(b, "initial")
    show_damage(b["initial"]["comparison"])
    show_observation(b["initial"].get("observation"))
    with st.expander("From above: satellite check"):
        dmg_type = (b.get("review") or {}).get("obstruction_type") or (
            (b["initial"].get("comparison") or {}).get("details", {}).get("damage", {}).get("likely_type"))
        for n in aerial.consistency(loc, dmg_type):
            st.write(n)
        if loc.get("aerial_result"):
            show_aerial(loc)
        elif loc.get("satellite_path") and Path(loc["satellite_path"]).exists():
            st.image(loc["satellite_path"], width=360, caption=f"Before the storm · USGS NAIP · {loc['lat']:.5f}, {loc['lon']:.5f}")

    with st.container(border=True):
        show_plan(b)
        if not (b["review"] or {}).get("confirmed"):
            st.caption("Draft from the photo alone. It updates when you confirm the details below.")

    # 2. human review
    st.subheader("2. Review")
    if ins["status"] == "dismissed":
        st.write("Dismissed: no storm damage blocking the route.")
        return
    obs = b["initial"].get("observation") or {}
    prev = b["review"] or {}
    if obs.get("obstruction_type") in HAZARD_TYPES or prev.get("obstruction_type") in HAZARD_TYPES:
        st.error("**Downed power line: treat it as live.** Stay at least 35 feet (10 m) away, keep others back, and call "
                 "**911** and the power company now. Don't wait for this report.")
    dmg = (b["initial"].get("comparison") or {}).get("details", {}).get("damage", {})
    default_type = (prev.get("obstruction_type")
                    or (obs.get("obstruction_type") if obs.get("obstruction_type") in OBSTRUCTION_TYPES else None)
                    or (dmg.get("likely_type") if dmg.get("likely_type") in OBSTRUCTION_TYPES else OBSTRUCTION_TYPES[0]))
    default_sev = prev.get("severity") or dmg.get("suggested_severity")
    default_desc = prev.get("description") or " ".join(obs.get("observations", [])) or (resident[-1] if resident else "")
    with st.form(f"review_{iid}"):
        t = st.selectbox("What is blocking the route?", OBSTRUCTION_TYPES, index=OBSTRUCTION_TYPES.index(default_type))
        sev = st.radio("How bad is it?", SEVERITIES, index=SEVERITIES.index(default_sev) if default_sev in SEVERITIES else 0)
        desc = st.text_area("Description for the cleanup crew", value=default_desc, height=110,
                            help="Pre-filled from the AI observations, or the resident's note. Edit so it's accurate.")
        note = st.text_input("Exact spot", value=prev.get("location_note", ""), placeholder="e.g. across the sidewalk outside the bus shelter")
        who = st.text_input("Your name", value=prev.get("reviewer", ""))
        ok = st.checkbox("I looked at the photos and these details are accurate.", value=bool(prev.get("confirmed")))
        c1, c2 = st.columns(2)
        confirm = c1.form_submit_button("Confirm details", type="primary")
        dismiss = c2.form_submit_button("No storm damage here")
    if confirm:
        if not (ok and who.strip() and desc.strip()):
            st.error("Fill in the description and your name, and tick the confirmation box.")
        else:
            store.save_review(iid, ReviewedDetails(t, sev, desc.strip(), note.strip(), who.strip(), True, now()))
            with st.spinner("Updating the response plan…"):
                pipeline.refresh_plan(store, iid)
            if ins["status"] == "captured":
                store.set_status(iid, "reviewed", f"confirmed by {who.strip()}")
            st.session_state.pop(f"report_text_{iid}", None)
            st.rerun()
    if dismiss:
        store.set_status(iid, "dismissed", "reviewer: no storm damage blocking the route")
        st.rerun()
    if not (b["review"] and b["review"].get("confirmed")):
        return

    # 3. report
    st.subheader("3. Report")
    vch = channels.verified()
    channel = None
    if vch:
        names = [c["name"] for c in vch]
        channel = vch[names.index(st.selectbox("Send to", names))]
        st.caption(f"Verified by {channel['verified_by']} on {channel['verified_on']} · {channels.contact_line(channel)}")
    else:
        st.warning("No verified reporting channel yet. Person 3: fill in config/channels.json from the official "
                   "city/county storm-debris and power company websites and mark them verified.")
    key = f"report_text_{iid}"
    if key not in st.session_state:
        st.session_state[key] = (b["report"] or {}).get("text") or report.draft_text(b, channel)
    text = st.text_area("Report (edit freely)", key=key, height=320)
    out = report.build(b, text, channel)
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Save report"):
        path = report.export(iid, out)
        store.save_report(iid, text, path, out.channel_name)
        st.success(f"Saved {path.name}")
    c2.download_button("Download printable report", out.html, file_name=f"{iid}-report.html", mime="text/html")
    c3.button("Redraft from details", on_click=lambda: st.session_state.pop(key, None))
    if ins["status"] == "reviewed" and c4.button(
            "Mark as sent" if channel else "Mark as sent (channel not verified)", type="primary"):
        path = report.export(iid, out)
        store.save_report(iid, text, path, out.channel_name)
        store.set_status(iid, "reported", f"sent to {out.channel_name}" if channel else "sent; channel NOT verified")
        st.rerun()
    if ins["status"] in ("captured", "reviewed"):
        return

    # 4. follow-up
    st.subheader("4. After cleanup")
    st.write("Come back after the crew has been and take a photo from the same spot. It's compared with the **same** before-storm photo.")
    if not b["follow_up"] or st.session_state.get(f"retake_{iid}"):
        img = photo_input(f"{iid}_follow", b["reference_path"], "follow_up")
        if img and st.button("Check after-cleanup photo", type="primary"):
            process_capture(iid, "follow_up", img, b["reference_path"])
            st.session_state.pop(f"retake_{iid}", None)
            st.rerun()
        return
    show_comparison(b, "follow_up")
    if ins["status"] in ("resolved",):
        st.success("Cleared.")
        return
    c1, c2, c3 = st.columns(3)
    if c1.button("Confirm cleared", type="primary"):
        store.set_status(iid, "resolved", "follow-up confirmed the route is clear")
        st.rerun()
    if c2.button("Still blocked"):
        store.set_status(iid, "still_blocked", "follow-up: obstruction still there")
        st.rerun()
    if c3.button("Retake photo"):
        st.session_state[f"retake_{iid}"] = True
        st.rerun()


def _open(iid: str):
    st.session_state.iid = iid


# ---------------------------------------------------------------- layout
PAGES = {
    "Report damage": ("Report damage (residents)", page_report),
    "Review": ("Review queue (reviewer)", page_review),
    "Locations": ("Before-storm photos (reviewer)", page_locations),
}
resident_only = st.query_params.get("page") == "report"  # the link residents get; not a login, just a simpler view

with st.sidebar:
    st.title("ClearPath")
    st.caption("After a hurricane: report storm damage blocking neighborhood streets, sidewalks and walkways, and confirm it gets cleared.")
    if resident_only:
        page = "Report damage"
    else:
        page = st.radio("Page", list(PAGES), key="page", format_func=lambda k: PAGES[k][0],
                        label_visibility="collapsed")
        st.divider()
        method = vision_ready()
        st.caption(f"Photo comparison: **{'DINOv2' if method == 'dinov2' else 'OpenCV baseline'}**")
        st.caption(f"AI observations: **{'Gemini ' + config.GEMINI_MODEL if gemini.available() else 'off (no API key)'}**")
        st.caption(f"Verified reporting channels: **{len(channels.verified())}**")
        st.caption(f"Damage analysis: **{'CLIP + SegFormer' if vision.ml.enabled() else 'off'}**")
        st.caption(f"Residents' website: [{RESIDENT_SITE}]({RESIDENT_SITE})")
        n_new = sum(i["status"] == "captured" for i in store.inspections())
        if n_new:
            st.caption(f"Reports waiting for review: **{n_new}**")

PAGES[page][1]()
