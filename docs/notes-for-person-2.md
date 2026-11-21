# Notes for Person 2 (vision and data), from Person 1

## What ClearPath is for: neighborhoods after a hurricane

Not campus, and not everyday sidewalks. After a storm, ClearPath compares a **before-storm** photo of a neighborhood street, sidewalk or walkway with an **after-storm** photo, flags what's blocking it (fallen trees, branches, debris, flood water, downed lines, damaged pavement), a person reviews it, a report goes to the right local office, and a follow-up photo confirms it was cleared. Flooding is just one of the damage types.

## What I changed on your branch (commit after `169a555`)

- **`evaluation/make_synthetic.py`:** the synthetic obstructions are now storm damage: `tree`, `branches`, `debris`, `water`, `bin`, `sign`. The old scooter/cone/barrier/box are still drawable by name (`EXTRA_OBJECTS`), just not in the default set.
- **Re-ran the evaluation** on the new set and updated the README table. DINOv2 beats the baseline more clearly here: recall 80% vs 50%, AUC 0.89 vs 0.75. It catches every tree, branch and debris pair, but misses small fallen signs and sometimes calls flood water uncertain. Those are listed as limits.
- **Your campus pilot is kept, not deleted.** It's real data, so it stays in the README, now titled *Pilot on real photos (method check only)*, with a line saying it doesn't measure storm damage on neighborhood streets.
- **README "Next" section:** how to collect neighborhood pairs, staging storm debris safely (palm fronds, branches, yard debris, a tarp, a tipped bin). `hard_case` can now be `shadow` or `wet`: wet pavement after a storm is the new false-alarm risk.
- **Wording:** `store.py`, `vision/__init__.py`, `evaluate.py`, your PLAN items.

Tests pass (`python -m unittest`).

## What's still yours

1. **Collect 15–30 real neighborhood pairs** with staged storm debris. Include clear, blocked, cleared, shadow and wet-pavement captures. When I import my photo-shoot photos with `python -m clearpath.demo real ... --eval`, they land in `data/eval/real/` in your format, about 2 pairs per spot.
2. **Re-tune the thresholds** on those pairs. Then check that the demo locations on `capture-demo` still come out *Obstructed*, then *Clear* (`python -m clearpath.preflight --no-camera` checks one of them).
3. **Put the neighborhood numbers in the README and the pitch.**

## The app itself lives on `capture-demo`

`app.py`, the demo locations, the Gemini prompt and the reporting channels on your branch still say campus. That's just because your branch is older. The hurricane version is on `capture-demo`, which already includes your branch. To get it:

```bash
git checkout vision-data
git pull
git merge origin/capture-demo
```

## Heads-up: the tests were writing into the real `data/` folder

`python -m unittest` discovery imports the `clearpath` package before the test file sets `CLEARPATH_DATA`, so test inspections ended up in the real `data/clearpath.db`. It's fixed on `capture-demo`. If your local `data/` has INS-000x inspections reviewed by "Tester", they came from test runs.
