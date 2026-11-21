"""ClearPath: document a blocked campus walkway, review it, report it, confirm the fix.

    streamlit run app.py

Person 1 owns this file and wires in Person 2 (clearpath.vision, clearpath.store)
and Person 3 (clearpath.reporting).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from clearpath import capture, config, demo, vision
from clearpath.contracts import (OBSTRUCTION_TYPES, PHASE_LABELS, SEVERITIES, STATUS_LABELS,
                                 ComparisonResult, ReviewedDetails)
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
        f = st.camera_input("Take a photo from where the reference was taken", key=f"{key}_cam")
        return f.getvalue() if f else None
    if src == "Upload":
        f = st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png", "webp"], key=f"{key}_up")
        return f.getvalue() if f else None
    st.image(str(demo_path), caption="Demo photo", width=320)
    return demo_path.read_bytes()


def process_capture(inspection_id: str, phase: str, image_bytes: bytes, reference_path: str):
    """Person 1 -> Person 2 -> Person 3 hand-offs for one photo."""
    with st.status("Checking the photo…", expanded=True) as s:
        st.write("Saving photo")
        cap = store.add_capture(capture.save_capture(image_bytes, inspection_id, phase))
        st.write("Comparing with the clear-path reference")
        overlay = config.OVERLAYS / inspection_id / f"{phase}_{cap.capture_id}.png"
        result: ComparisonResult = vision.compare(reference_path, cap.image_path, overlay)
        store.save_comparison(cap.capture_id, result)
        if phase == "initial":
            st.write("Asking Gemini what it sees")
            obs = gemini.observe(reference_path, cap.image_path, result.to_dict())
            store.save_observation(cap.capture_id, obs)
        s.update(label="Photo checked", state="complete")


def show_comparison(bundle: dict, phase: str):
    cap = bundle[phase]
    comp = cap["comparison"]
    c1, c2, c3 = st.columns(3)
    c1.image(bundle["reference_path"], caption="Clear-path reference", width="stretch")
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


def show_observation(obs: dict | None):
    if not obs:
        return
    if not obs.get("available"):
        st.info(f"No AI observations: {obs.get('reason')}")
        return
    st.markdown(f"**AI observations** · {obs['model']} · confidence {obs['confidence']} · *draft for the reviewer*")
    st.write(f"Obstruction: **{obs['obstruction_type']}**" + ("" if obs["path_blocked"] else " (Gemini thinks the path is clear)"))
    for o in obs["observations"]:
        st.write(f"- {o}")
    if obs.get("accessibility_impact"):
        st.write(f"Impact: {obs['accessibility_impact']}")
    if obs.get("suggested_action"):
        st.write(f"Suggested action: {obs['suggested_action']}")


# ---------------------------------------------------------------- pages
def page_locations():
    st.header("Locations")
    st.write("Each location needs one photo of the walkway when it's **clear**. Every inspection there is compared "
             "against it, so take it from a spot you can find again (e.g. standing at a door or a lamp post).")
    with st.form("new_loc", clear_on_submit=True):
        name = st.text_input("Location name", placeholder="e.g. Library north ramp")
        desc = st.text_input("Where exactly / how to stand", placeholder="Facing south from the ramp's top landing")
        src = st.radio("Reference photo", ["Camera", "Upload"], horizontal=True)
        f = st.camera_input("Clear-path photo") if src == "Camera" else st.file_uploader("Clear-path photo", type=["jpg", "jpeg", "png", "webp"])
        if st.form_submit_button("Add location", type="primary"):
            if not name.strip() or not f:
                st.error("Add a name and a reference photo.")
            else:
                ref = capture.save_reference(f.getvalue(), name)
                store.add_location(name, ref, desc)
                st.success(f"Added {name}.")
    if st.button("Add 3 demo locations (no camera needed)"):
        n = demo.seed(store)
        st.success(f"Added {n} demo locations." if n else "Demo locations already exist.")
    locs = store.locations()
    if locs:
        cols = st.columns(3)
        for i, l in enumerate(locs):
            with cols[i % 3]:
                st.image(l["reference_path"], width="stretch")
                st.markdown(f"**{l['name']}**  \n{l['description'] or ''}")


def page_inspect():
    locs = store.locations()
    if not locs:
        st.info("Add a location with a clear-path reference photo first (Locations page).")
        return

    qp = st.query_params.get("inspection")
    if qp and "iid" not in st.session_state and store.bundle(qp):
        st.session_state.iid = qp  # shareable link: ?inspection=INS-0001
    iid = st.session_state.get("iid")
    if iid:
        st.query_params["inspection"] = iid
    elif "inspection" in st.query_params:
        del st.query_params["inspection"]
    if not iid:
        st.header("Start an inspection")
        names = {l["name"]: l["id"] for l in locs}
        name = st.selectbox("Where are you?", list(names))
        loc = next(l for l in locs if l["id"] == names[name])
        st.image(loc["reference_path"], caption="Clear-path reference: stand roughly here", width=420)
        if st.button("Start inspection", type="primary"):
            st.session_state.iid = store.new_inspection(names[name])
            st.rerun()
        return

    b = store.bundle(iid)
    ins, loc = b["inspection"], b["location"]
    top = st.columns([4, 1])
    top[0].header(f"{iid} · {loc['name']}")
    top[0].caption(STATUS_LABELS[ins["status"]])
    if top[1].button("Close inspection"):
        st.session_state.pop("iid")
        st.rerun()

    # 1. initial capture
    st.subheader("1. Photo of the problem")
    if not b["initial"]:
        img = photo_input(f"{iid}_initial", b["reference_path"], "initial")
        if img and st.button("Check this photo", type="primary"):
            process_capture(iid, "initial", img, b["reference_path"])
            st.rerun()
        return
    show_comparison(b, "initial")
    show_observation(b["initial"].get("observation"))

    # 2. human review
    st.subheader("2. Review")
    if ins["status"] == "dismissed":
        st.write("Dismissed: not an obstruction.")
        return
    obs = b["initial"].get("observation") or {}
    prev = b["review"] or {}
    default_type = prev.get("obstruction_type") or (obs.get("obstruction_type") if obs.get("obstruction_type") in OBSTRUCTION_TYPES else OBSTRUCTION_TYPES[0])
    default_desc = prev.get("description") or " ".join(obs.get("observations", []))
    with st.form(f"review_{iid}"):
        t = st.selectbox("What is blocking the path?", OBSTRUCTION_TYPES, index=OBSTRUCTION_TYPES.index(default_type))
        sev = st.radio("How bad is it?", SEVERITIES, index=SEVERITIES.index(prev["severity"]) if prev.get("severity") in SEVERITIES else 0)
        desc = st.text_area("Description for facilities", value=default_desc, height=110,
                            help="Pre-filled from the AI observations when available. Edit so it's accurate.")
        note = st.text_input("Exact spot", value=prev.get("location_note", ""), placeholder="e.g. bottom of the ramp, east side")
        who = st.text_input("Your name", value=prev.get("reviewer", ""))
        ok = st.checkbox("I looked at the photos and these details are accurate.", value=bool(prev.get("confirmed")))
        c1, c2 = st.columns(2)
        confirm = c1.form_submit_button("Confirm details", type="primary")
        dismiss = c2.form_submit_button("Not an obstruction")
    if confirm:
        if not (ok and who.strip() and desc.strip()):
            st.error("Fill in the description and your name, and tick the confirmation box.")
        else:
            store.save_review(iid, ReviewedDetails(t, sev, desc.strip(), note.strip(), who.strip(), True, now()))
            if ins["status"] == "captured":
                store.set_status(iid, "reviewed", f"confirmed by {who.strip()}")
            st.session_state.pop(f"report_text_{iid}", None)
            st.rerun()
    if dismiss:
        store.set_status(iid, "dismissed", "reviewer: not an obstruction")
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
        if channel.get("submission_instructions"):
            st.caption(channel["submission_instructions"])
    else:
        st.warning("No verified campus reporting channel yet. Person 3: fill in config/channels.json from the "
                   "university's official website and mark it verified.")
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
    st.subheader("4. Follow-up")
    st.write("Come back later and take a photo from the same spot. It's compared with the **same** clear-path reference.")
    if not b["follow_up"] or st.session_state.get(f"retake_{iid}"):
        img = photo_input(f"{iid}_follow", b["reference_path"], "follow_up")
        if img and st.button("Check follow-up photo", type="primary"):
            process_capture(iid, "follow_up", img, b["reference_path"])
            st.session_state.pop(f"retake_{iid}", None)
            st.rerun()
        return
    show_comparison(b, "follow_up")
    if ins["status"] in ("resolved",):
        st.success("Resolved.")
        return
    c1, c2, c3 = st.columns(3)
    if c1.button("Confirm resolved", type="primary"):
        store.set_status(iid, "resolved", "follow-up confirmed clear")
        st.rerun()
    if c2.button("Still blocked"):
        store.set_status(iid, "still_blocked", "follow-up: obstruction still there")
        st.rerun()
    if c3.button("Retake follow-up"):
        st.session_state[f"retake_{iid}"] = True
        st.rerun()


def page_all():
    st.header("All inspections")
    items = store.inspections()
    if not items:
        st.info("No inspections yet.")
        return
    for i in items:
        c1, c2, c3, c4 = st.columns([1.2, 2.5, 2.5, 1])
        c1.write(f"**{i['id']}**")
        c2.write(i["location_name"])
        c3.write(STATUS_LABELS[i["status"]])
        c4.button("Open", key=f"open_{i['id']}", on_click=_open, args=(i["id"],))


def _open(iid: str):
    # runs before the next rerun, so it may set the sidebar radio's value
    st.session_state.iid = iid
    st.session_state.page = "Inspect"


# ---------------------------------------------------------------- layout
with st.sidebar:
    st.title("ClearPath")
    st.caption("Report blocked campus walkways and confirm they get fixed.")
    page = st.radio("Page", ["Inspect", "Locations", "All inspections"], key="page", label_visibility="collapsed")
    st.divider()
    method = vision_ready()
    st.caption(f"Photo comparison: **{'DINOv2' if method == 'dinov2' else 'OpenCV baseline'}**")
    st.caption(f"AI observations: **{'Gemini ' + config.GEMINI_MODEL if gemini.available() else 'off (no API key)'}**")
    n_ver = len(channels.verified())
    st.caption(f"Verified reporting channels: **{n_ver}**")

{"Inspect": page_inspect, "Locations": page_locations, "All inspections": page_all}[page]()
