# Build plan

Three people. Each owns a slice and one hand-off, defined in [clearpath/contracts.py](../clearpath/contracts.py). Checked items already work. Unchecked items are what's left.

## Person 1: Capture and demo (`capture-demo`)

Owns: webcam, Streamlit workflow, human review and resolution, and integrating everyone's modules into `app.py`.
Hands off: a saved image with its inspection ID and phase (`SavedCapture`) to Person 2.

- [x] Streamlit flow: locations → inspect → review → report → follow-up → resolve
- [x] Webcam (`st.camera_input`) and upload; photos saved per inspection and phase
- [x] Review form: type, severity, description (pre-filled from Gemini), reviewer, confirmation box
- [x] Resolution: confirm resolved / still blocked / retake; dismiss false alarms
- [x] Demo locations so the demo works without a camera
- [x] Real-photo import (`python -m clearpath.demo real`), preflight check (`python -m clearpath.preflight`), playbook in [DEMO.md](DEMO.md)
- [x] Satellite (USGS NAIP) + tree-canopy risk per spot; reports placed by photo/phone GPS; before/after aerial comparison (NOAA or drone) + consistency check
- [x] Hugging Face models: CLIP damage type, SegFormer walkway + damage equations, RemoteCLIP aerial (OWL-ViT tested and dropped)
- [x] Nearby contractors/resources (OpenStreetMap) + response plan (Gemini agent with `find_nearby` tool, or rules)
- [x] FastAPI backend + separate residents' website (`api/`, `web/`), Playwright-tested; reviewer app themed to match
- [x] Two pages: residents' **Report damage** (one photo + note; `?page=report` link hides reviewer pages) and the reviewer's **Review queue**
- [x] Refocused on neighborhoods after a hurricane: storm-damage types, power-line safety warning, before-storm / after-cleanup flow, 4 storm demo routes
- [ ] Photo shoot at 2–3 neighborhood routes: before, staged storm debris, after cleanup (note where you stood); import with `--eval` so Person 2 gets the pairs ([DEMO.md §1](DEMO.md#1-photo-shoot-in-the-neighborhood-about-45-minutes))
- [ ] Test the webcam flow on the demo laptop, in the room you'll present in ([DEMO.md §2](DEMO.md#2-laptop-check-in-the-presenting-room))
- [ ] Rehearse the demo end to end; keep a backup run on demo photos ([DEMO.md §3–4](DEMO.md#3-demo-script-about-3-minutes))

## Person 2: Vision and data (`vision-data`)

Owns: DINOv2, OpenCV baseline, SQLite, evaluation.
Hands off: `ComparisonResult` + overlay. Keeps initial and follow-up captures linked to the same clear-path reference.

- [x] Alignment: ORB homography with an ECC fallback
- [x] DINOv2 patch comparison; OpenCV baseline runs alongside
- [x] Overlay image with changed regions outlined
- [x] SQLite store; each inspection copies its reference path so follow-ups use the same one
- [x] Synthetic pairs + evaluation script (DINOv2 vs OpenCV)
- [x] Storm-damage synthetic pairs (tree, branches, debris, flood water, bin, sign) and re-run evaluation
- [x] Real-photo pilot (campus/indoor, backpack): method check only, kept in the README
- [ ] Collect 15–30 real **neighborhood** pairs with staged storm debris (clear, blocked, cleared, shadow, wet) into `data/eval/real/`
- [ ] Re-tune `PATCH_THRESHOLD` (dino.py) and `OBSTRUCTED_AT` / `CLEAR_BELOW` (vision/__init__.py) on real pairs
- [ ] Put the real evaluation table in the README and the pitch

## Person 3: Gemini, imagery and reporting (`gemini-reporting`)

Owns: AI observations, before/after aerial imagery (`clearpath/satellite.py`), verified neighborhood reporting channels, editable report, export.
Hands off: report text + printable HTML (`ReportOutput`), from saved evidence and reviewer-confirmed details. Guide: [NEIGHBORHOOD_GUIDE.md](NEIGHBORHOOD_GUIDE.md).

- [x] Gemini call with structured JSON output; labeled as a draft; works without a key
- [x] Report draft built only from confirmed review details
- [x] Printable HTML with embedded photos, overlay and history
- [x] Only verified channels are offered
- [x] Pivot campus → neighborhood: hazard types, report wording, Tampa channels
- [x] Before/after aerial imagery: Esri Wayback (before) + NOAA post-Helene/Milton (after), capture dates, attribution
- [x] Aerial-aware Gemini prompt with hazard boxes (`regions`) and a CLI test
- [ ] Pick 2–3 demo streets with clearly visible debris (`python -m clearpath.satellite --preview`)
- [x] Verify Gemini API access and structured output on the engineering walkway demo
- [x] Test Gemini live on Davis Islands, Madeira Beach, and South Tampa, and tighten `AERIAL_PROMPT` to limit findings to visible areas
- [x] Verify aerial blockage detection and overlay placement on a controlled image pair with an inserted fallen tree
- [ ] Open each Tampa channel link yourself and put your name in `verified_by`; find the illegal-dumping page
- [x] Print the HTML report to PDF and inspect the US Letter layout with demo photos, overlays, and follow-up history
- [ ] Test the prompt on staged ground photos too; check it flags anything wire-like as "Downed power line" (the app's 911 warning depends on it)

## Together, before submitting

- [ ] Merge all three branches into `1.0`
- [ ] Full run with real photos: capture → compare → Gemini → review → report → follow-up
- [ ] Pitch includes the real evaluation numbers and the limits
