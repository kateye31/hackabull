# Build plan

Three people, seven hours. **Features freeze at hour 4**; after that, only fixes, measurements and the pitch.

| Person | Branch | Owns |
| --- | --- | --- |
| A — detection | `detection` | [detection/](../detection/) |
| B — app | `app` | [app/](../app/) |
| C — research & pitch | `pitch` | [docs/](./) — slides, sources, notes |

Checked items are already in the repo and working on the synthetic demo scene. Unchecked items are what's left. Merge your branch into `1.0` when a task works.

## Person A — detection ([detection/](../detection/))

### Hours 0–1 · Set up the real scene
- [x] Synthetic before/after scene with ground truth (`python -m detection.make_demo_scene`)
- [ ] Get real before/after images of one neighborhood from Person C
- [ ] Save as `data/scenes/<name>/before.png`, `after.png`, `scene.json` (bounds + metres per pixel)
- [ ] Optional: `roads.png` / `buildings.png` masks from OpenStreetMap for that area

### Hours 1–3 · Find new water
- [x] Align after → before (`align.py`)
- [x] Water mask: RGB rules + NDWI for 4-band imagery (`water.py`)
- [x] New water = after AND NOT before; drop tiny blobs (`detect.py`)
- [x] Label blobs: flooded road stretches, flooded buildings, standing water
- [ ] Tune `CLEAR_HUE`, `MUDDY_HUE`, `MAX_LOCAL_STD` in `water.py` on the real scene
- [ ] Check `overlay.png`: the pond/pool test case must stay blue

### Hours 3–4 · Connect detection to the map
- [x] `detections.json` + overlay + before/after crops, loaded by the server at startup
- [ ] Run `python -m detection.detect data/scenes/<name>` on the real scene and confirm pins land on the right streets

### Hours 4–7 · Measure results
- [x] `python -m detection.evaluate scene ...` (IoU, pools/ponds flagged with vs without comparison)
- [x] `python -m detection.evaluate floodnet ...` (single-image water IoU)
- [ ] Run on the FloodNet images Person C downloads (~10 images)
- [ ] Hand-label the real scene's new water (even roughly) and run `evaluate scene`
- [ ] Give the real numbers to Person C for the slides, even if modest

## Person B — app ([app/](../app/))

### Hours 0–1 · Crew map and report form
- [x] Crew map with before/after/new-water layers (`static/index.html`, `crew.js`)
- [x] Resident form: pin, what you see, depth, moving/still, blocks road, photo (`static/report.html`)
- [ ] Start the app with `python run_demo.py --lan` so Person C can test on a phone

### Hours 1–3 · Issue cards, priority rules, cost ranges
- [x] Issue cards with before/after crops or resident photo, source, depth, time, next steps, cost
- [x] Priority rules in one place (`priority.py`)
- [x] Building cost from affected sq ft × $7.00–$7.50 (sourced)
- [ ] Put Person C's cited numbers into `priority.py` (drywall rate, standing-water and debris ranges); add sources to the README

### Hours 3–4 · Status updates, final polish
- [x] Verified / Assigned / Cleared, False alarm, Reopen, history
- [x] Live refresh every 4 s; new reports pulse on the map
- [ ] Fix whatever Person C's phone and timing tests turn up

### Hours 4–7 · Bug fixes and the live demo
- [ ] Bug fixes only; no new features after hour 4
- [ ] Run the live demo during the pitch (demo script in the README)

## Person C — research & pitch ([docs/](./))

### Hours 0–1 · Find real data and sources
- [ ] Find before and after images of the same neighborhood after a real hurricane; send to Person A with the map corners (lat/lon) and metres per pixel if available
- [ ] Find cited prices for drywall replacement, pumping out standing water, and hauling debris; send to Person B with links

### Hours 1–3 · Test data and slides
- [ ] Download ~10 FloodNet images + labels for Person A ([paper](https://arxiv.org/abs/2012.02951))
- [ ] Confirm which FloodNet label ids mean water (the script guesses 3, 5, 8) and tell Person A
- [ ] Start the slides: problem → before/after → live report → crew acts → results → limits

### Hours 3–4 · Test it like a user
- [ ] Send a report from a real phone and confirm it shows up on the crew map
- [ ] Time a new user finding the highest-priority problem (target: under 30 s)
- [ ] Send Person B a short list of anything confusing or broken

### Hours 4–7 · Pitch, video, submission
- [ ] Add Person A's real scores to the slides
- [ ] Record the demo video (follow the demo script in the README)
- [ ] Rehearse twice with Person B running the demo
- [ ] Submit: Home Turf track (Best Overall as another fit)

## Hand-off contract

`data/scenes/<scene>/detections.json`:

```json
{
  "scene": "demo",
  "bounds": [[27.96, -82.46], [27.9627, -82.4559]],
  "images": {"before": "demo/before.png", "after": "demo/after_aligned.png", "overlay": "demo/overlay.png"},
  "issues": [
    {"id": "A-demo-001", "source": "aerial", "category": "flooded_road",
     "lat": 27.961374, "lon": -82.459475, "area_m2": 882.5, "blocks_road": true,
     "note": "...", "crops": {"before": "demo/crops/A-demo-001_before.png", "after": "..."}}
  ]
}
```

Categories: `flooded_road`, `flooded_building`, `standing_water`, `debris`. Re-running detection keeps crews' statuses for issue ids that already exist.
