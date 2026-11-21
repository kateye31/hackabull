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
- [ ] Take real clear-path reference photos at 2–3 campus spots (note where you stood)
- [ ] Test the webcam flow on the demo laptop, in the room you'll present in
- [ ] Rehearse the demo end to end; keep a backup run on demo photos

## Person 2: Vision and data (`vision-data`)

Owns: DINOv2, OpenCV baseline, SQLite, evaluation.
Hands off: `ComparisonResult` + overlay. Keeps initial and follow-up captures linked to the same clear-path reference.

- [x] Alignment: ORB homography with an ECC fallback
- [x] DINOv2 patch comparison; OpenCV baseline runs alongside
- [x] Overlay image with changed regions outlined
- [x] SQLite store; each inspection copies its reference path so follow-ups use the same one
- [x] Synthetic pairs + evaluation script (DINOv2 vs OpenCV)
- [ ] Collect 15–30 real pairs on campus (clear and blocked, different light) into `data/eval/real/`
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

## Together, before submitting

- [ ] Merge all three branches into `1.0`
- [ ] Full run with real photos: capture → compare → Gemini → review → report → follow-up
- [ ] Pitch includes the real evaluation numbers and the limits
