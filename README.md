# ReTrace

One map for hurricane flood recovery crews: where a neighborhood flooded, how bad it is, and what to handle first.

ReTrace compares views of a neighborhood from **before and after** a storm to find **new** water (so pools and ponds don't get flagged), adds **resident reports** (photo, pin, depth), and gives crews a prioritized list with next steps, a rough cleanup cost range, and Verified / Assigned / Cleared status.

Proposal: [ReTrace — Flood Recovery Proposal](https://claude.ai/artifact/FGcMPbbjmubfTKTSaffKZf) · Track: Home Turf (Best Overall as another fit) · Hackabull 2026

## Quick start

```bash
pip install -r requirements.txt
python run_demo.py
```

Then open:

- **Crew map:** http://localhost:5000
- **Resident report form:** http://localhost:5000/report (`python run_demo.py --lan` to open it from a phone on the same Wi-Fi)

`run_demo.py` builds a synthetic before/after neighborhood, runs detection, scores it, and starts the app. Run the tests with `python -m unittest -v`.

## Demo script (2 minutes)

1. **Before/after.** In the map's layer box, toggle *Before storm* / *After storm*. Turn on *Detected new water*: the flood is red, the pond and pools stay blue (already there, not flagged).
2. **Resident report, live.** On a phone, open `/report`, drop a pin, pick *Water on the road*, *Knee*, *Moving*, attach a photo, send.
3. **It lands on the crew map** within ~4 s, at the top of the list as *Highest*, with a pulsing pin.
4. **Open a flooded home's card.** Before/after crops, next steps, and the cost range. Enter `650` sq ft to get a dollar range.
5. **Mark it Verified, then Cleared.** It drops to the bottom; the history shows each step.

## Who's doing what

Three people, seven hours, features freeze at hour 4. The full checklist is in [docs/PLAN.md](docs/PLAN.md).

| | Person A — detection | Person B — app | Person C — research & pitch |
| --- | --- | --- | --- |
| Branch | `detection` | `app` | `pitch` |
| Owns | [detection/](detection/) | [app/](app/) | [docs/](docs/) |
| 0–1 h | Set up the real scene once C sends images | Crew map + report form | Find real before/after images and cost sources |
| 1–3 h | Find new water | Issue cards, priority rules, cost ranges | Download FloodNet for A; start the slides |
| 3–4 h | Connect detection to the map | Status updates, polish | Phone test; time a new user |
| 4–7 h | Measure results | Fix bugs from testing; run the live demo | Pitch, demo video, submission |

The hand-off between the two halves is one file: `data/scenes/<scene>/detections.json`. Detection writes it; the server loads every one at startup.

## How it works

```
before.png ─┐                          ┌─ water mask (before) ─┐
            ├─ align (ORB + RANSAC) ───┤                       ├─ new water = after AND NOT before
after.png ──┘                          └─ water mask (after) ──┘            │
                                                                            ▼
roads.png / buildings.png ──────────────► label each blob: flooded_road (per ~80 m stretch),
                                          flooded_building (per house it touches), standing_water
                                                                            │
                                                                            ▼
                     detections.json + overlay.png + before/after crops per issue
                                                                            │
resident form ── POST /api/reports ──►  SQLite  ◄── loaded at startup ──────┘
                                          │
                                          ▼
                     crew map: priority, next steps, cost range, status (priority.py)
```

| Path | What it does |
| --- | --- |
| [detection/make_demo_scene.py](detection/make_demo_scene.py) | Synthetic neighborhood + ground-truth masks, so everything runs offline |
| [detection/align.py](detection/align.py) | Lines the after image up with the before image |
| [detection/water.py](detection/water.py) | Water mask: colour + smoothness rules for RGB, NDWI for 4-band (near-infrared) imagery |
| [detection/detect.py](detection/detect.py) | New water → issues, overlay, crops, `detections.json` |
| [detection/evaluate.py](detection/evaluate.py) | The success metrics, on a labeled scene or on FloodNet |
| [app/priority.py](app/priority.py) | Every rule crews see: priority, next steps, cost ranges |
| [app/server.py](app/server.py) | Flask API + pages |
| [app/static/](app/static/) | Crew map (`index.html`, `crew.js`) and resident form (`report.html`, `report.js`) |

### Priority rules

- Flooded road, or anything a resident says **blocks the road** → **Highest**.
- Flooded building → **High**; standing water and debris → **Medium**.
- Waist-deep / above-a-tire water, or moving water, bumps an issue up one level.
- Within a level: deeper first, then oldest first. Cleared and dismissed issues sink to the bottom.

### Cost ranges

Storm floodwater is treated as contaminated: about **$7.00–$7.50 per sq ft** to remove and dry ([Bob Vila cost guide](https://www.bobvila.com/articles/water-damage-restoration-cost/)). Crews enter the affected square footage after checking in person.

> **To do before the demo:** the drywall rate and the flat ranges for standing water and debris in [app/priority.py](app/priority.py) are placeholders. Replace them with sourced numbers and cite them.

## Measuring success

```bash
python -m detection.evaluate scene data/scenes/demo --out results.md
python -m detection.evaluate floodnet path/to/images path/to/labels --limit 10
```

On the synthetic demo scene (these numbers are high because the scene is synthetic; real imagery will score lower, and we'll report what we get):

| Metric | Result |
| --- | --- |
| New-water (flood) IoU | 97.1% |
| Pools/ponds wrongly flagged, after image only | 7 of 7 |
| Pools/ponds wrongly flagged, with before/after | 0 of 7 |

FloodNet ([paper](https://arxiv.org/abs/2012.02951)) is post-Hurricane Harvey drone imagery with pixel labels. It has no "before" images, so it scores only the single-image water mask. Check the class ids in its README; `--water-classes` defaults to `3,5,8`.

Usability target: a new user finds the highest-priority problem in under 30 seconds. It's always the first card, marked *Next up*.

## Using real imagery

Make a folder `data/scenes/<name>/` with:

| File | Needed | Notes |
| --- | --- | --- |
| `before.png`, `after.png` | yes | Same area, north-up. Rough alignment is fine; `align.py` fixes small shifts and rotation. |
| `scene.json` | yes | `{"name": "...", "bounds": [[south, west], [north, east]], "gsd_m": 0.5}` (bounds of `before.png`; `gsd_m` = metres per pixel) |
| `roads.png`, `buildings.png` | no | White = road / building, same size as `before.png`. Without them every blob is `standing_water`. Rasterise from OpenStreetMap. |

Then `python -m detection.detect data/scenes/<name>` (add `--bands rgbn` for 4-band imagery) and restart the server.

## Limits

- ReTrace flags visible new water for people to check. Every flag is a suggestion, not a final call.
- It can't measure depth from above; depth comes from residents.
- It can't confirm damage inside buildings. Water around a home is marked "possible interior flooding — verify."
- The RGB water rules are hand-tuned. Brown roofs and dirt can look like muddy water; the before/after comparison removes most of that, but a trained model would do better.
- Costs are rough ranges, not quotes or structural assessments.

**Future work:** low-cost street sensors for live depth, elevation data to estimate depth, live image feeds, and connecting to city 311 and emergency management systems.
