"""Editable report text and printable HTML (Person 3).

Takes saved evidence and reviewer-confirmed details; returns ReportOutput.
Only confirmed details go in. AI observations appear only as a labeled note.
"""
from __future__ import annotations

import base64
import html
from datetime import datetime
from pathlib import Path

from .. import config, satellite
from ..contracts import PHASE_LABELS, STATUS_LABELS, ReportOutput
from . import channels as channels_mod


def _when(iso: str | None) -> str:
    if not iso:
        return "unknown"
    return datetime.fromisoformat(iso).astimezone().strftime("%b %d, %Y at %I:%M %p")


def draft_text(bundle: dict, channel: dict | None = None) -> str:
    review = bundle.get("review")
    if not review or not review.get("confirmed"):
        raise ValueError("A reviewer must confirm the details before a report can be drafted.")
    loc = bundle["location"]
    ins = bundle["inspection"]
    initial = bundle.get("initial") or {}
    comp = initial.get("comparison") or {}
    lines = [
        f"Subject: Neighborhood hazard at {loc['name']} ({ins['id']})",
        "",
        f"Location: {loc['name']}" + (f" ({review['location_note']})" if review.get("location_note") else ""),
        f"What is blocking it: {review['obstruction_type']}",
        f"Severity: {review['severity']}",
        f"First observed: {_when(initial.get('captured_at'))}",
    ]
    site = satellite.site_meta(bundle["reference_path"])
    if site:
        lines += [f"Coordinates: {site['lat']:.5f}, {site['lon']:.5f} ({satellite.maps_link(site['lat'], site['lon'])})"]
        for fname, label in (("reference.jpg", "Before imagery"), ("initial.jpg", "After imagery")):
            info = site["images"].get(fname)
            if info:
                lines += [f"{label}: {info['label']}" + (f", captured {info['captured']}" if info.get("captured") else "")]
    lines += [
        "",
        review["description"].strip(),
        "",
        "Evidence: a before image, the image showing the hazard, and a highlighted comparison",
        "are in the attached printable report.",
    ]
    if comp:
        lines += ["", f"Photo comparison ({comp['method']}): about {comp['changed_fraction']:.0%} of the scene changed "
                      f"versus the before image (verdict: {comp['verdict']})."]
    obs = initial.get("observation") or {}
    if obs.get("available"):
        lines += [f"AI-generated observations ({obs['model']}) were checked by the reviewer before sending."]
    fu = bundle.get("follow_up")
    if fu:
        fc = fu.get("comparison") or {}
        lines += ["", f"Follow-up photo {_when(fu.get('captured_at'))}: "
                      f"{fc.get('verdict', 'not compared')} ({fc.get('changed_fraction', 0):.0%} changed)."]
    lines += ["", f"Reported by: {review['reviewer']}", f"Inspection ID: {ins['id']}"]
    if channel:
        lines += [f"Reporting channel: {channel['name']} ({channels_mod.contact_line(channel)})"]
    return "\n".join(lines)


def _img(path: str | Path | None) -> str:
    if not path or not Path(path).exists():
        return ""
    data = base64.b64encode(Path(path).read_bytes()).decode()
    mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
    return f"data:{mime};base64,{data}"


def render_html(bundle: dict, text: str, channel: dict | None = None) -> str:
    esc = html.escape
    ins, loc = bundle["inspection"], bundle["location"]
    site = satellite.site_meta(bundle["reference_path"])
    imgs = (site or {}).get("images", {})

    def src(fname):
        i = imgs.get(fname)
        return f"{i['label']}" + (f" · captured {i['captured']}" if i.get("captured") else "") if i else ""

    figs = [("Before (reference)", bundle["reference_path"], src("reference.jpg"))]
    for phase in ("initial", "follow_up"):
        cap = bundle.get(phase)
        if not cap:
            continue
        comp = cap.get("comparison") or {}
        cap_note = src("initial.jpg" if phase == "initial" else "followup.jpg") or _when(cap["captured_at"])
        figs.append((f"{PHASE_LABELS[phase]} photo", cap["image_path"], cap_note))
        if comp.get("overlay_path"):
            figs.append((f"{PHASE_LABELS[phase]}: changes highlighted", comp["overlay_path"],
                         f"{comp['verdict']} · {comp['changed_fraction']:.0%} changed · {comp['method']}"))
    fig_html = "\n".join(
        f'<figure><img src="{_img(p)}" alt="{esc(t)}"><figcaption><b>{esc(t)}</b><br>{esc(n)}</figcaption></figure>'
        for t, p, n in figs if _img(p))
    ch = ""
    if channel:
        ch = f'<p class="channel">Send to: <b>{esc(channel["name"])}</b> · {esc(channels_mod.contact_line(channel))}</p>'
        if channel.get("submission_instructions"):
            ch += f'<p>{esc(channel["submission_instructions"])}</p>'
    events = "".join(f"<li>{esc(STATUS_LABELS.get(e['status'], e['status']))} · {esc(_when(e['at']))}</li>"
                     for e in bundle.get("events", []))
    used = {i["source"] for i in imgs.values()}
    credits = "".join(f'<p class="fine">{esc(satellite.ATTRIBUTION[k])}</p>' for k in sorted(used))
    if site:
        ch += (f'<p class="meta">Location: {site["lat"]:.5f}, {site["lon"]:.5f} · '
               f'<a href="{esc(satellite.maps_link(site["lat"], site["lon"]))}">map</a></p>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(ins['id'])} · Neighborhood hazard report</title>
<style>
  body {{ font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1b1f23; max-width: 820px; margin: 24px auto; padding: 0 16px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .meta {{ color: #5d6670; margin: 0 0 16px; }}
  pre {{ white-space: pre-wrap; font: inherit; background: #f6f7f5; border: 1px solid #e1e4e0; border-radius: 8px; padding: 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 16px; }}
  figure {{ margin: 0; break-inside: avoid; }}
  img {{ width: 100%; border-radius: 6px; border: 1px solid #e1e4e0; }}
  figcaption {{ font-size: 13px; color: #5d6670; margin-top: 4px; }}
  .channel {{ background: #e9f4f1; padding: 8px 12px; border-radius: 8px; }}
  .fine {{ font-size: 12px; color: #5d6670; }}
  @page {{ margin: 0.5in; }}
  @media print {{
    body {{ margin: 0; max-width: none; padding: 0; font-size: 12px; line-height: 1.35; overflow-wrap: anywhere; }}
    pre {{ padding: 8px; }}
    .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 8px; }}
    figure img {{ height: 1.12in; object-fit: contain; box-sizing: border-box; }}
    figcaption {{ font-size: 12px; }}
    h3 {{ break-after: avoid; }}
    .noprint {{ display: none; }}
  }}
</style></head>
<body>
  <h1>Neighborhood hazard: {esc(loc['name'])}</h1>
  <p class="meta">{esc(ins['id'])} · status: {esc(STATUS_LABELS.get(ins['status'], ins['status']))}</p>
  {ch}
  <pre>{esc(text)}</pre>
  <div class="grid">{fig_html}</div>
  <h3>History</h3><ul>{events}</ul>
  <p class="fine">Images were compared automatically and every detail above was confirmed by a person before sending.</p>
  {credits}
  <p class="noprint fine">Use your browser's Print command to save as PDF.</p>
</body></html>"""


def build(bundle: dict, text: str | None = None, channel: dict | None = None) -> ReportOutput:
    """Draft (or reuse edited) text, render HTML. Person 1 shows/edits; export saves it."""
    text = text if text is not None else draft_text(bundle, channel)
    return ReportOutput(text=text, html=render_html(bundle, text, channel),
                        channel_name=channel["name"] if channel else None,
                        channel_verified=bool(channel and channels_mod.is_verified(channel)))


def export(inspection_id: str, out: ReportOutput) -> Path:
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    p = config.REPORTS / f"{inspection_id}.html"
    p.write_text(out.html, encoding="utf-8")
    return p
