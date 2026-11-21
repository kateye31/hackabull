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
| [clearpath/demo.py](clearpath/demo.py) | 1 | Demo walkways so the app runs without a camera |
| [clearpath/vision/](clearpath/vision/) | 2 | `compare()` → `ComparisonResult`: alignment, DINOv2 patch comparison, OpenCV baseline, overlay |
| [clearpath/store.py](clearpath/store.py) | 2 | SQLite: locations, inspections, captures, results, reviews, reports, history |
| [evaluation/](evaluation/) | 2 | Synthetic test pairs and the DINOv2-vs-OpenCV scorecard |
| [clearpath/reporting/gemini.py](clearpath/reporting/gemini.py) | 3 | Gemini observations as structured JSON |
| [clearpath/reporting/channels.py](clearpath/reporting/channels.py) + [config/channels.json](config/channels.json) | 3 | Reporting channels; only verified ones are offered |
| [clearpath/reporting/report.py](clearpath/reporting/report.py) | 3 | Report text and printable HTML with embedded photos |

## How the comparison works

1. **Align.** ORB keypoints and a homography line the new photo up with the reference. ECC is a fallback for small handheld shifts and lighting changes. The result records whether either method succeeded.
2. **DINOv2.** Both photos become a 32 × 24 grid of patch features. The comparison reuses reference features for repeated captures and bases the verdict on the largest connected changed region after removing small specks.
3. **OpenCV baseline.** A lighting-normalised pixel/colour difference runs on every photo, so the two can be compared side by side.
4. **Verdict.** *Obstructed*, *clear*, or *uncertain*. Uncertain means "a person should look," and a person reviews every inspection anyway.

### Evaluation (synthetic pairs, 40)

`python -m evaluation.make_synthetic && python -m evaluation.evaluate data/eval/synthetic`

| Method | Exact verdict matches | Obstruction recall | Clear paths flagged | Uncertain | AUC | CPU time per pair |
| --- | --- | --- | --- | --- | --- | --- |
| OpenCV baseline | 17 of 40 | 40% | 6 of 20 | 11 of 40 | 0.60 | 0.10 s |
| DINOv2-small | 21 of 40 | 60% | 3 of 20 | 13 of 40 | 0.77 | 0.40 s |

On this synthetic set, DINOv2 flagged 2 of 10 shadowed clear paths and OpenCV flagged 5. Exact matches require a definite verdict that matches the label. CPU timing includes alignment and comparison, after model load. This run used the default generator seed and [DINOv2-small revision `ed25f3a`](https://huggingface.co/facebook/dinov2-small/tree/ed25f3a31f01632728cabb09d1542f84ab7b0056).

### Real campus evaluation

The first campus pilot used 11 pairs from an outdoor walkway and two indoor hallways. The outdoor walkway and first hallway provided eight development pairs. The second hallway was held out with three pairs. An edge placement counted as obstructed when the backpack occupied some of the walking surface.

| Split | Method | Exact verdict matches | Obstructions flagged | Clear captures flagged as obstructed | Uncertain | CPU time per pair |
| --- | --- | --- | --- | --- | --- | --- |
| Development | OpenCV | 5 of 8 | 2 of 5 | 0 of 3 | 3 of 8 | 0.44 s |
| Development | DINOv2-small | 7 of 8 | 5 of 5 | 0 of 3 | 1 of 8 | 0.61 s |
| Held-out hallway | OpenCV | 3 of 3 | 2 of 2 | 0 of 1 | 0 of 3 | 1.00 s |
| Held-out hallway | DINOv2-small | 3 of 3 | 2 of 2 | 0 of 1 | 0 of 3 | 1.19 s |

These counts describe verdicts. In the held-out hallway, alignment failed on the centered-backpack capture and the DINOv2 overlay highlighted much of the scene. A separate close-up with a backpack near the lens triggered both methods, while a blocked photo taken from farther back also produced a broad change alert. These two framing checks were outside the scored set. Both actual removal follow-ups in the scored set were called clear by both methods.

The shipped thresholds were kept. Lowering the OpenCV obstruction cutoff from 5% to 3.5% improved development recall, left the held-out results unchanged, and increased synthetic false alerts from 6 to 8 of 20 clear pairs. The pilot used a single object type and has no labeled shadow trials.

To extend the benchmark:

Collect 15–30 reference/capture pairs at a few campus locations. Include clear, blocked, cleared follow-up, and shadowed clear captures. Take each reference with the path clear. Reuse that reference for the corresponding captures. Save each pair under `data/eval/real/<pair_id>/` as `reference.jpg` and `capture.jpg`.

Create `data/eval/real/labels.csv` with columns `pair_id,label,hard_case`. Use `clear` or `obstructed` for `label` and enter `shadow` in `hard_case` for shadow trials. Keep photos in the ignored `data/` directory.

```bash
python -m evaluation.evaluate data/eval/real --per-pair --out data/eval/real/results.md
```

Use a development subset to tune the patch-distance and verdict thresholds. Hold back pairs from a different spot for the final score when possible. Report the held-out counts and label the synthetic results separately. Add `--methods opencv` for an OpenCV-only run when weights are unavailable.

## Verified reporting channel

[config/channels.json](config/channels.json) ships empty on purpose. Person 3 copies the official contact (URL, email or phone) from the university's own website, records `source_page`, `verified_by` and `verified_on`, and sets `verified: true`. Until then, the app warns that no verified channel exists and labels anything sent as "channel not verified."

## Limits

- Every flag is a suggestion. A person confirms details before anything is reported.
- The reference photo must be taken from roughly the same spot. Very different angles fail to align, and the app says so.
- Gemini output is a draft and is labeled as AI-generated. The prompt tells it not to describe people or licence plates.
- Photos are re-encoded on save, which removes EXIF data, including GPS.

The earlier ReTrace flood-mapping prototype is preserved at git tag `retrace-v0`.
