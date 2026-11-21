# Build plan

Two people, seven hours. **Features freeze at hour 4**; after that, only fixes, measurements and the pitch.

Checked items are already in the repo and working on the synthetic demo scene. Unchecked items are what's left.

## Person A — detection ([detection/](../detection/))

### Hours 0–1 · Gather before/after views
- [x] Synthetic before/after scene with ground truth (`python -m detection.make_demo_scene`)
- [ ] Pick one real neighborhood with before and after imagery of the same area
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
- [ ] Download a handful of FloodNet images + labels; confirm the class ids; run on ~10 images
- [ ] Hand-label the real scene's new water (even roughly) and run `evaluate scene`
- [ ] Put the real numbers in the README and the pitch, even if modest

## Person B — app ([app/](../app/))

### Hours 0–1 · Crew map and report form
- [x] Crew map with before/after/new-water layers (`static/index.html`, `crew.js`)
- [x] Resident form: pin, what you see, depth, moving/still, blocks road, photo (`static/report.html`)
- [ ] Test the form on a real phone with `python run_demo.py --lan`

### Hours 1–3 · Issue cards, priority rules, cost ranges
- [x] Issue cards with before/after crops or resident photo, source, depth, time, next steps, cost
- [x] Priority rules in one place (`priority.py`)
- [x] Building cost from affected sq ft × $7.00–$7.50 (sourced)
- [ ] Replace placeholder drywall rate and flat ranges in `priority.py` with sourced numbers; add sources to the README

### Hours 3–4 · Status updates, final polish
- [x] Verified / Assigned / Cleared, False alarm, Reopen, history
- [x] Live refresh every 4 s; new reports pulse on the map
- [ ] Walk the demo script in the README end to end; fix anything that feels slow or confusing

### Hours 4–7 · Pitch, demo video, submission
- [ ] Time a new user finding the highest-priority problem (target: under 30 s)
- [ ] Pitch slides: problem → before/after → live report → crew acts → results → limits
- [ ] Record the demo video (follow the demo script)
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
