# ClearPath

After a hurricane, people need to know which neighborhood streets, sidewalks and walkways they can actually use, and the city needs to know what to clear first. ClearPath documents storm damage blocking a neighborhood route, gets it to the right office, and confirms it was cleared.

1. **Before the storm.** Photograph key routes while they're clear: the sidewalk to the bus stop, curb ramps, the walkway to the shelter or clinic. That's the *before-storm reference*.
2. **Report (residents).** After the storm, a resident opens the **Report damage** page, picks the spot, and sends one photo from the same place, with an optional note. The link `…/?page=report` shows only that page.
3. **Compare.** The photo is compared against the before-storm reference (DINOv2, with an OpenCV baseline), and what's new is highlighted: fallen trees, branches, debris, flood water, a downed sign.
4. **Describe.** Gemini drafts observations: what's blocking the route, hazards such as downed power lines, who it affects (people on foot, in wheelchairs, with strollers, or driving out), and a suggested action.
5. **Review (reviewer).** On the **Review queue** page, a neighborhood reviewer checks the photos and the resident's note, and confirms or edits the details. Nothing goes out unconfirmed.
6. **Report.** An editable report, plus a printable HTML export, goes to a **verified** local channel: the county or city storm-debris line, 311, or the power company for downed lines.
7. **Follow up.** After cleanup, a new photo is compared against the **same** before-storm reference, and the reviewer marks it cleared or still blocked.

## Quick start

```bash
pip install -r requirements.txt
python -m clearpath.preflight --no-camera     # downloads and caches the models; checks map services
streamlit run app.py                          # the reviewer app: http://localhost:8501
uvicorn api.main:app --port 8000              # the residents' website + API: http://localhost:8000
```

Both read and write the same SQLite database (`data/`). In the reviewer app, go to **Before-storm photos → Add demo locations**: four demo routes in a residential area of Tampa, each with a real USGS satellite image and nearby help from OpenStreetMap (set `CLEARPATH_DEMO_CENTER=lat,lon` for another neighborhood). Then send a report from the residents' website (**Demo photo** works without a camera) and open it in the reviewer's **Review queue**.

| Setting | Default | What it does |
| --- | --- | --- |
| `GEMINI_API_KEY` | none | Gemini observations and the Gemini response planner. Without it, rules plan the response. |
| `CLEARPATH_ML` | `auto` | `off` skips CLIP, SegFormer and RemoteCLIP (DINOv2 still runs). |
| `CLEARPATH_OFFLINE` | `0` | `1` = no satellite or OpenStreetMap calls; cached data still works. |
| `CLEARPATH_DEMO_CENTER` | `28.0006,-82.4594` | Where demo routes are placed. |
| `CLEARPATH_RESIDENT_URL` | `http://localhost:8000` | Link to the residents' site shown in the reviewer app. |

Tests: `python -m unittest -v` (26 tests, offline, models off).

## How it fits together

```
 residents' website (web/index.html)        reviewer app (app.py, Streamlit)
        │  photo + note + GPS                         │  queue → review → plan → report → after cleanup
        ▼                                             ▼
 FastAPI backend (api/main.py) ──► clearpath/pipeline.py ◄────────────┘
                                      │
   locate (photo GPS → phone GPS → pick) · save (EXIF stripped) · compare with before-storm photo (DINOv2)
   damage analysis (CLIP type, SegFormer walkway, equations) · Gemini observations · response plan
   (Gemini + find_nearby tool, or rules) · nearby help (OpenStreetMap) · satellite (USGS NAIP, RemoteCLIP)
                                      │
                                SQLite (clearpath/store.py)
```

## Models and what we measured

Every model output is a suggestion for the reviewer, never a fact. We tested before choosing:

| Job | Model (Hugging Face) | What we found |
| --- | --- | --- |
| What changed since before the storm | `facebook/dinov2-small` | Synthetic storm pairs: 80% recall, 2 of 20 clear paths flagged, AUC 0.89 (vs 50% / 4 of 20 / 0.75 for a pixel diff). |
| Which kind of damage | `openai/clip-vit-base-patch32`, zero-shot | 0.3 s a photo. On 4 public post-hurricane photos: top guess right on both fallen-tree photos; on the two debris photos "debris" came 2nd and 3rd. Wrong on our cartoon demo drawings. |
| Where the walkway is | `nvidia/segformer-b0-finetuned-ade-512-512` | 0.3 s. Found 87% of the true walkway (IoU) on a synthetic scene. |
| What changed from above | `MVRL/remote-clip-vit-base-patch32` (RemoteCLIP, via open_clip) | 0.1 s. Unreliable on one image (called a normal block "flooded" at 0.78), so only the before→after shift is shown. |
| Tried and dropped | `google/owlvit-base-patch32` (open-vocabulary detector) | 10–17 s a photo on a laptop CPU, found the two fallen trees, missed both debris photos. |

## The damage equations

With W = walkable surface in the before-storm photo (SegFormer) and C = the DINOv2 change mask after alignment:

- **Walkway blocked** B = |W ∩ C| / |W|
- **Narrowest clear width** N = 10th percentile, over image rows near the camera, of |Wᵧ \ C| / |Wᵧ|
- **Damage index** DI = 100 · B · weight(type), weights from 1.0 (downed line) to 0.5 (fallen sign)
- **Suggested severity**: impassable if N < 0.25 or B ≥ 0.6; partly blocked if B ≥ 0.15; downed lines are always critical
- **Tree canopy around a spot** (satellite): share of pixels with excess-green 2g − r − b > 0.05 and brightness < 0.45, within the central circle. ≥35% = high storm risk.
- Distances: haversine. Nearby help is sorted by distance (hospitals with an emergency room first).

## Satellite and the ground photo

A top-down satellite image and a street-level photo share almost nothing pixel to pixel, so they are not compared directly. Instead:

1. **Before-storm satellite** (USGS NAIP, ~0.6 m/pixel, public domain) for each spot: map context and tree-canopy risk.
2. **Before vs after from above**: upload a NOAA post-storm aerial or a drone photo taken straight down on **Before-storm photos → After-storm aerial**. DINOv2 compares the two top-down images; RemoteCLIP says what shifted (e.g. "+44% flooded"). **Demo: synthetic damage** draws storm damage onto the real tile and is always labelled SYNTHETIC.
3. **Consistency check** on every report: does the view from above support the ground photo? (A fallen tree reported where there's almost no canopy gets flagged.)

## Maps

Both sites use Leaflet with a **Streets / Satellite** switch (OpenStreetMap tiles, USGS The National Map imagery). On the residents' site, tap a spot's pin to choose it; "Use my location" shows where you are; after sending, a numbered map of nearby help matches the list. In the reviewer app ([clearpath/mapview.py](clearpath/mapview.py)), every spot is coloured by its most urgent open report (needs review, ready to report, awaiting cleanup, cleared), with a toggleable layer of nearby help. The map only reads cached map data, so it never waits on OpenStreetMap; offline it says so and the lists still work.

## Nearby help and the response plan

One OpenStreetMap (Overpass) query per ~1 km neighborhood cell, fetched when a spot is added and cached for 7 days, so reports never wait for it (a query can take 40 s). Each damage type maps to what it needs: fallen tree → tree service, hardware, builder; flooding → plumber/pumps, hardware, shelter; downed line → fire station, electrician (and 911 + the utility first). Hospitals and shelters are always included.

With a Gemini key, Gemini plans the response as an agent: it gets the confirmed details and the damage numbers, calls a `find_nearby(category)` tool for real places, and returns priority, crew, equipment, steps, safety and who to call. Without a key, rules produce the same structure. OpenStreetMap coverage varies: a missing category means "none mapped nearby", not "none exist".

## Team

| Person | Owns | Hands off | Branch |
| --- | --- | --- | --- |
| **1. Capture and demo** | Webcam, Streamlit workflow, human review and resolution | Gives Person 2 a saved image with its inspection ID and phase. Integrates everyone's modules into `app.py`. | `capture-demo` |
| **2. Vision and data** | DINOv2, OpenCV baseline, SQLite, evaluation | Returns the comparison result and overlay. Keeps the after-storm and follow-up captures linked to the same before-storm reference. | `vision-data` |
| **3. Gemini and reporting** | AI observations, verified local reporting channels, editable report, export | Takes saved evidence and reviewer-confirmed details; returns report text and printable HTML. | `gemini-reporting` |

Checklists per person: [docs/PLAN.md](docs/PLAN.md). The hand-off types live in [clearpath/contracts.py](clearpath/contracts.py). Change them together.

| Path | Owner | What it does |
| --- | --- | --- |
| [app.py](app.py) | 1 | Streamlit app: residents' Report damage page; reviewer's queue, review form, report, after-cleanup follow-up; before-storm photos |
| [clearpath/capture.py](clearpath/capture.py) | 1 | Saves webcam/upload photos as `SavedCapture` (fixes rotation, strips EXIF/GPS) |
| [clearpath/demo.py](clearpath/demo.py) | 1 | Demo neighborhood routes after a storm, so the app runs without a camera; `demo real` imports your own before/after photos as a backup run |
| [clearpath/preflight.py](clearpath/preflight.py) | 1 | `python -m clearpath.preflight`: checks the demo laptop (DINOv2 cached, camera, Gemini, channels, photos) |
| [docs/DEMO.md](docs/DEMO.md) | 1 | Photo shoot, room check, demo script and backup plan |
| [api/main.py](api/main.py) + [web/index.html](web/index.html) | 1 | FastAPI backend and the residents' website (separate from the reviewer app, same database) |
| [clearpath/pipeline.py](clearpath/pipeline.py) | 1 | One photo → located, saved, compared, analysed, planned; used by both websites |
| [clearpath/geo.py](clearpath/geo.py) | 2 | GPS from photos, USGS satellite images, tree-canopy index, geocoding, distances |
| [clearpath/vision/ml.py](clearpath/vision/ml.py) | 2 | CLIP damage type, SegFormer walkway, damage equations |
| [clearpath/vision/aerial.py](clearpath/vision/aerial.py) | 2 | Before/after aerial comparison, RemoteCLIP, satellite consistency check |
| [clearpath/reporting/resources.py](clearpath/reporting/resources.py) | 3 | Contractors and resources near a spot, from OpenStreetMap |
| [clearpath/reporting/plan.py](clearpath/reporting/plan.py) | 3 | Response plan: Gemini with a `find_nearby` tool, or rules |
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
- No login yet: the residents' site is a separate address, but the reviewer app is not password-protected. Run both on localhost for the demo.
- Damage-type suggestions are weakest on debris and on anything that isn't a real photo; the walkway equations assume the before-storm photo shows the walkway.
- A downed power line is an emergency, not a report: the app tells people to stay at least 35 feet away and call 911 and the power company first.
- Thin or small things, like a downed power line or a small fallen sign, are easy to miss in the patch grid. A person reviews every photo.
- The before-storm reference must be taken from roughly the same spot. Very different angles fail to align, and the app says so.
- Gemini output is a draft and is labeled as AI-generated. The prompt tells it not to describe people or licence plates.
- Photos are re-encoded on save, which removes EXIF data, including GPS.

The earlier ReTrace prototype (aerial flood mapping only) is preserved at git tag `retrace-v0`.
