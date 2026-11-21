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
- [ ] Take real clear-path reference photos at 2–3 neighborhood spots (note where you stood); import with `--eval` so Person 2 gets the pairs ([DEMO.md §1](DEMO.md#1-photo-shoot-in-the-neighborhood-about-30-minutes))
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
- [ ] Collect 15–30 real pairs in the neighborhood (clear and blocked, different light) into `data/eval/real/`
- [ ] Re-tune `PATCH_THRESHOLD` (dino.py) and `OBSTRUCTED_AT` / `CLEAR_BELOW` (vision/__init__.py) on real pairs
- [ ] Put the real evaluation table in the README and the pitch

## Person 3: Gemini and reporting (`gemini-reporting`)

Owns: AI observations, verified city reporting channel, editable report, export.
Hands off: report text + printable HTML (`ReportOutput`), from saved evidence and reviewer-confirmed details.

- [x] Gemini call with structured JSON output; labeled as a draft; works without a key
- [x] Report draft built only from confirmed review details
- [x] Printable HTML with embedded photos, overlay and history
- [x] Only verified channels are offered
- [ ] Get a Gemini API key; test `gemini.observe` on real photos and tighten the prompt
- [ ] Find the city's official channel for blocked sidewalks (311 / public works / ADA coordinator) on the city website; fill in `config/channels.json` and mark it verified
- [ ] Print the HTML report to PDF once and check that it looks right on paper

## Together, before submitting

- [ ] Merge all three branches into `1.0`
- [ ] Full run with real photos: capture → compare → Gemini → review → report → follow-up
- [ ] Pitch includes the real evaluation numbers and the limits
