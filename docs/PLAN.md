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
- [x] Storm-damage synthetic pairs (tree, branches, debris, flood water, bin, sign) and re-run evaluation
- [x] Real-photo pilot (campus/indoor, backpack): method check only, kept in the README
- [ ] Collect 15–30 real **neighborhood** pairs with staged storm debris (clear, blocked, cleared, shadow, wet) into `data/eval/real/`
- [ ] Re-tune `PATCH_THRESHOLD` (dino.py) and `OBSTRUCTED_AT` / `CLEAR_BELOW` (vision/__init__.py) on real pairs
- [ ] Put the real evaluation table in the README and the pitch

## Person 3: Gemini and reporting (`gemini-reporting`)

Owns: AI observations, verified campus reporting channel, editable report, export.
Hands off: report text + printable HTML (`ReportOutput`), from saved evidence and reviewer-confirmed details.

- [x] Gemini call with structured JSON output; labeled as a draft; works without a key
- [x] Report draft built only from confirmed review details
- [x] Printable HTML with embedded photos, overlay and history
- [x] Only verified channels are offered
- [ ] Get a Gemini API key; test `gemini.observe` on real photos and tighten the prompt
- [ ] Find the official campus channel for blocked walkways on the university website; fill in `config/channels.json` and mark it verified
- [ ] Print the HTML report to PDF once and check that it looks right on paper

## Together, before submitting

- [ ] Merge all three branches into `1.0`
- [ ] Full run with real photos: capture → compare → Gemini → review → report → follow-up
- [ ] Pitch includes the real evaluation numbers and the limits
