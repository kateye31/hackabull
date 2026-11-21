# Notes for Person 2 (vision and data), from Person 1

## We switched from campus to neighborhood sidewalks

ClearPath now covers **neighborhood sidewalks reported to the city** (311 / public works), not campus walkways reported to the university. The code works the same; the wording, the demo locations and the reporting channels changed. It's all on `capture-demo` (commit `2abd36b`).

What that means for you:

- **Real evaluation pairs come from neighborhood sidewalks**, not campus. Same folder layout and same `labels.csv` as before.
- **Your README "Real campus evaluation" section** should say neighborhood. It's also the one merge conflict between `vision-data` and `capture-demo`: only the paragraph after the synthetic table conflicts. Keep your text and change "campus" to "neighborhood".

## Some real pairs will come to you automatically

When I import my photo-shoot photos, `--eval` writes them straight into your format:

```bash
python -m clearpath.demo real "Oak St & 3rd" photos/oak-3rd --where "Toes on the curb ramp, facing north" --eval
```

This writes `data/eval/real/<spot>-blocked/` (label `obstructed`) and `data/eval/real/<spot>-cleared/` (label `clear`), each with `reference.jpg` + `capture.jpg`, and updates `labels.csv` (`pair_id,label,obstruction,hard_case`). I checked that it loads in your stricter `evaluate.py`. `hard_case` is left empty, so mark the shadow trials as `shadow` yourself. That gives you about 2 pairs per spot. You still need more for 15–30, especially shadowed clear paths.

## Your changes work with mine

I trial-merged `vision-data` into `capture-demo` locally (nothing pushed). All 11 tests pass, and the three new demo locations still get the right verdicts with your `dino.py`:

| Demo location | Blocked photo | Follow-up | OpenCV on blocked |
| --- | --- | --- | --- |
| Oak Street sidewalk | obstructed | clear | clear (misses it; good pitch moment) |
| Maple Avenue curb ramp | obstructed | clear | uncertain |
| 5th Avenue bus stop | obstructed | clear | clear |

**When you re-tune the thresholds on real pairs**, please re-check these demo locations, or run `python -m clearpath.preflight --no-camera`, which compares the Oak Street pair and warns if it stops coming out obstructed. The demo script relies on all three being *Obstructed*, then *Clear*.

## Heads-up: the tests were writing into the real `data/` folder

`python -m unittest` discovery imports the `clearpath` package before the test file sets `CLEARPATH_DATA`, so test inspections ended up in the real `data/clearpath.db`. It's fixed on `capture-demo`: the test file reloads `config` and `demo`, and asserts that it's writing to the temp folder. If your local `data/` has INS-000x inspections reviewed by "Tester", they came from test runs.
