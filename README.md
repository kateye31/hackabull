# ClearPath

After a hurricane, people need to know which neighborhood streets, sidewalks and walkways they can actually use, and the city needs to know what to clear first. ClearPath documents storm damage blocking a neighborhood route, gets it to the right office, and confirms it was cleared.

1. **Before the storm.** Photograph key routes while they're clear: the sidewalk to the bus stop, curb ramps, the walkway to the shelter or clinic. That's the *before-storm reference*.
2. **Capture.** After the storm, take a photo from the same spot with a webcam or phone.
3. **Compare.** The photo is compared against the before-storm reference (DINOv2, with an OpenCV baseline), and what's new is highlighted: fallen trees, branches, debris, flood water, a downed sign.
4. **Describe.** Gemini drafts observations: what's blocking the route, hazards such as downed power lines, who it affects (people on foot, in wheelchairs, with strollers, or driving out), and a suggested action.
5. **Review.** A person checks the photos and confirms or edits the details. Nothing goes out unconfirmed.
6. **Report.** An editable report, plus a printable HTML export, goes to a **verified** local channel: the county or city storm-debris line, 311, or the power company for downed lines.
7. **Follow up.** After cleanup, a new photo is compared against the **same** before-storm reference, and the reviewer marks it cleared or still blocked.

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
| **2. Vision and data** | DINOv2, OpenCV baseline, SQLite, evaluation | Returns the comparison result and overlay. Keeps the after-storm and follow-up captures linked to the same before-storm reference. | `vision-data` |
| **3. Gemini and reporting** | AI observations, verified local reporting channels, editable report, export | Takes saved evidence and reviewer-confirmed details; returns report text and printable HTML. | `gemini-reporting` |

Checklists per person: [docs/PLAN.md](docs/PLAN.md). The hand-off types live in [clearpath/contracts.py](clearpath/contracts.py). Change them together.

| Path | Owner | What it does |
| --- | --- | --- |
| [app.py](app.py) | 1 | Streamlit app: locations, inspect flow, review form, report, follow-up |
| [clearpath/capture.py](clearpath/capture.py) | 1 | Saves webcam/upload photos as `SavedCapture` (fixes rotation, strips EXIF/GPS) |
| [clearpath/demo.py](clearpath/demo.py) | 1 | Demo neighborhood routes after a storm, so the app runs without a camera |
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

### Evaluation (synthetic storm-damage pairs, 40)

`python -m evaluation.make_synthetic && python -m evaluation.evaluate data/eval/synthetic`

Each obstructed pair has one kind of storm damage on the street: a fallen tree, scattered branches, a debris pile, flood water, a blown-over trash bin or a fallen sign. Half the pairs add a long shadow, the classic false alarm.

| Method | Exact verdict matches | Obstruction recall | Clear paths flagged | Shadowed clear paths flagged | Uncertain | AUC | CPU time per pair |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenCV baseline | 21 of 40 | 50% | 4 of 20 | 4 of 10 | 11 of 40 | 0.75 | 0.10 s |
| DINOv2-small | 26 of 40 | 80% | 2 of 20 | 2 of 10 | 10 of 40 | 0.89 | 0.65 s |

DINOv2 caught every fallen tree, branch and debris pair. It missed both small fallen signs (called clear) and sent one trash bin and one flood-water pair to a human as uncertain. Exact matches require a definite verdict that matches the label. CPU timing includes alignment and comparison, after model load, on a laptop CPU. Default generator seed, [DINOv2-small revision `ed25f3a`](https://huggingface.co/facebook/dinov2-small/tree/ed25f3a31f01632728cabb09d1542f84ab7b0056).

### Pilot on real photos (method check only)

This pilot ran before the project focused on neighborhoods after a storm. It used 11 pairs from an outdoor campus walkway and two indoor hallways, with a backpack as the only obstruction. It shows the method works on real photos, but it does **not** measure storm-damage detection on neighborhood streets. The outdoor walkway and first hallway provided eight development pairs; the second hallway was held out with three pairs. An edge placement counted as obstructed when the backpack occupied some of the walking surface.

| Split | Method | Exact verdict matches | Obstructions flagged | Clear captures flagged as obstructed | Uncertain | CPU time per pair |
| --- | --- | --- | --- | --- | --- | --- |
| Development | OpenCV | 5 of 8 | 2 of 5 | 0 of 3 | 3 of 8 | 0.44 s |
| Development | DINOv2-small | 7 of 8 | 5 of 5 | 0 of 3 | 1 of 8 | 0.61 s |
| Held-out hallway | OpenCV | 3 of 3 | 2 of 2 | 0 of 1 | 0 of 3 | 1.00 s |
| Held-out hallway | DINOv2-small | 3 of 3 | 2 of 2 | 0 of 1 | 0 of 3 | 1.19 s |

These counts describe verdicts. In the held-out hallway, alignment failed on the centered-backpack capture and the DINOv2 overlay highlighted much of the scene. A separate close-up with a backpack near the lens triggered both methods, while a blocked photo taken from farther back also produced a broad change alert. These two framing checks were outside the scored set. Both actual removal follow-ups in the scored set were called clear by both methods.

The shipped thresholds were kept. Lowering the OpenCV obstruction cutoff from 5% to 3.5% improved development recall, left the held-out results unchanged, and increased synthetic false alerts from 6 to 8 of 20 clear pairs. The pilot used a single object type and has no labeled shadow trials.

### Next: real neighborhood pairs

Collect 15–30 before/after pairs at a few neighborhood spots: sidewalks, curb ramps, the walkway to a bus stop or shelter. Storm damage can't be scheduled, so stage what a storm leaves behind, safely and on public sidewalk: fallen palm fronds and branches, a pile of yard debris, boards or a tarp, a tipped-over trash bin. Include clear, blocked, cleared follow-up, shadowed clear, and wet-pavement clear captures (after rain or a hose-down: wet ground is the post-storm version of the shadow problem). Take each reference with the route clear and reuse it for that spot's captures. Save each pair under `data/eval/real/<pair_id>/` as `reference.jpg` and `capture.jpg`. Person 1's `python -m clearpath.demo real ... --eval` writes pairs in this layout.

Create `data/eval/real/labels.csv` with columns `pair_id,label,obstruction,hard_case`. Use `clear` or `obstructed` for `label`, the kind of damage for `obstruction`, and `shadow` or `wet` in `hard_case`. Keep photos in the ignored `data/` directory.

```bash
python -m evaluation.evaluate data/eval/real --per-pair --out data/eval/real/results.md
```

Use a development subset to tune the patch-distance and verdict thresholds. Hold back pairs from a different spot for the final score when possible. Report the held-out counts and label the synthetic and pilot results separately. Add `--methods opencv` for an OpenCV-only run when weights are unavailable.

## Verified reporting channel

[config/channels.json](config/channels.json) ships empty on purpose. Person 3 copies each official contact (URL, email or phone) from the city's, county's or power company's own website, records `source_page`, `verified_by` and `verified_on`, and sets `verified: true`. Until then, the app warns that no verified channel exists and labels anything sent as "channel not verified."

## Limits

- Every flag is a suggestion. A person confirms details before anything is reported.
- Thin or small things, like a downed power line or a small fallen sign, are easy to miss in the patch grid. A person reviews every photo.
- The before-storm reference must be taken from roughly the same spot. Very different angles fail to align, and the app says so.
- Gemini output is a draft and is labeled as AI-generated. The prompt tells it not to describe people or licence plates.
- Photos are re-encoded on save, which removes EXIF data, including GPS.

The earlier ReTrace prototype (aerial flood mapping only) is preserved at git tag `retrace-v0`.
