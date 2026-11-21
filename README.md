# ClearPath

Document a blocked campus walkway, get it to the right office, and confirm it got fixed.

1. **Capture.** Take a photo of the blocked path with a webcam or phone.
2. **Compare.** The photo is compared against a *clear-path reference* photo of the same spot (DINOv2, with an OpenCV baseline), and the changed area is highlighted.
3. **Describe.** Gemini drafts observations: what's blocking it, the accessibility impact, and a suggested action.
4. **Review.** A person checks the photos and confirms or edits the details. Nothing goes out unconfirmed.
5. **Report.** An editable report, plus a printable HTML export, goes to a **verified** campus reporting channel.
6. **Follow up.** A later photo is compared against the **same** reference, and the reviewer marks it resolved or still blocked.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

In the app, go to **Locations → Add 3 demo locations**, then **Inspect → Start inspection → Demo photo**. No camera is needed.

Optional: `set GEMINI_API_KEY=...` (Windows) or `export GEMINI_API_KEY=...` before launching to turn on AI observations. Without a key, the reviewer fills in the details by hand.

Tests: `python -m unittest -v`

## Team

| Person | Owns | Hands off | Branch |
| --- | --- | --- | --- |
| **1. Capture and demo** | Webcam, Streamlit workflow, human review and resolution | Gives Person 2 a saved image with its inspection ID and phase. Integrates everyone's modules into `app.py`. | `capture-demo` |
| **2. Vision and data** | DINOv2, OpenCV baseline, SQLite, evaluation | Returns the comparison result and overlay. Keeps initial and follow-up captures linked to the same clear-path reference. | `vision-data` |
| **3. Gemini and reporting** | AI observations, verified campus reporting channel, editable report, export | Takes saved evidence and reviewer-confirmed details; returns report text and printable HTML. | `gemini-reporting` |

Checklists per person: [docs/PLAN.md](docs/PLAN.md). The hand-off types live in [clearpath/contracts.py](clearpath/contracts.py). Change them together.

| Path | Owner | What it does |
| --- | --- | --- |
| [app.py](app.py) | 1 | Streamlit app: locations, inspect flow, review form, report, follow-up |
| [clearpath/capture.py](clearpath/capture.py) | 1 | Saves webcam/upload photos as `SavedCapture` (fixes rotation, strips EXIF/GPS) |
| [clearpath/demo.py](clearpath/demo.py) | 1 | Demo walkways so the app runs without a camera; `demo real` imports your own campus photos as a backup run |
| [clearpath/preflight.py](clearpath/preflight.py) | 1 | `python -m clearpath.preflight`: checks the demo laptop (DINOv2 cached, camera, Gemini, channels, photos) |
| [docs/DEMO.md](docs/DEMO.md) | 1 | Photo shoot, room check, demo script and backup plan |
| [clearpath/vision/](clearpath/vision/) | 2 | `compare()` → `ComparisonResult`: alignment, DINOv2 patch comparison, OpenCV baseline, overlay |
| [clearpath/store.py](clearpath/store.py) | 2 | SQLite: locations, inspections, captures, results, reviews, reports, history |
| [evaluation/](evaluation/) | 2 | Synthetic test pairs and the DINOv2-vs-OpenCV scorecard |
| [clearpath/reporting/gemini.py](clearpath/reporting/gemini.py) | 3 | Gemini observations as structured JSON |
| [clearpath/reporting/channels.py](clearpath/reporting/channels.py) + [config/channels.json](config/channels.json) | 3 | Reporting channels; only verified ones are offered |
| [clearpath/reporting/report.py](clearpath/reporting/report.py) | 3 | Report text and printable HTML with embedded photos |

## How the comparison works

1. **Align.** ORB keypoints and a homography line the new photo up with the reference. If that fails, an ECC alignment takes over, which handles small handheld shifts and lighting changes.
2. **DINOv2.** Both photos become a 32 × 24 grid of patch features, and patches whose features moved far apart are flagged. The verdict uses the **largest connected changed region**: an object shows up as one solid region, while lighting and small misalignment leave scattered specks.
3. **OpenCV baseline.** A lighting-normalised pixel/colour difference runs on every photo, so the two can be compared side by side.
4. **Verdict.** *Obstructed*, *clear*, or *uncertain*. Uncertain means "a person should look," and a person reviews every inspection anyway.

### Evaluation (synthetic pairs, 40)

`python -m evaluation.make_synthetic && python -m evaluation.evaluate data/eval/synthetic`

| Method | Accuracy | Precision | Recall | Shadowed clear paths flagged | AUC |
| --- | --- | --- | --- | --- | --- |
| OpenCV baseline | 55% | 58% | 35% | 5 of 10 | 0.63 |
| DINOv2 | 78% | 87% | 65% | 2 of 10 | 0.81 |

These are synthetic drawings, not photos, so the thresholds in [clearpath/vision/\_\_init\_\_.py](clearpath/vision/__init__.py) were set from them. **Re-tune them on real campus pairs** (same folder layout, `data/eval/real/<pair>/reference.jpg`, `capture.jpg`, plus `labels.csv`) and report those numbers instead.

## Verified reporting channel

[config/channels.json](config/channels.json) ships empty on purpose. Person 3 copies the official contact (URL, email or phone) from the university's own website, records `source_page`, `verified_by` and `verified_on`, and sets `verified: true`. Until then, the app warns that no verified channel exists and labels anything sent as "channel not verified."

## Limits

- Every flag is a suggestion. A person confirms details before anything is reported.
- The reference photo must be taken from roughly the same spot. Very different angles fail to align, and the app says so.
- Gemini output is a draft and is labeled as AI-generated. The prompt tells it not to describe people or licence plates.
- Photos are re-encoded on save, which removes EXIF data, including GPS.

The earlier ReTrace flood-mapping prototype is preserved at git tag `retrace-v0`.
