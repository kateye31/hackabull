# Notes for Person 3 (Gemini and reporting), from Person 1

## What ClearPath is for: neighborhoods after a hurricane

Not campus, and not everyday sidewalks. After a storm, ClearPath compares a **before-storm** photo of a neighborhood street, sidewalk or walkway with an **after-storm** photo, flags what's blocking it (fallen trees, branches, debris, flooding, downed lines, damaged pavement), a person reviews it, a report goes to the right local office, and an **after-cleanup** photo confirms it was cleared. Flooding is just one of the damage types.

It's all on `capture-demo` (merged with Person 2's `vision-data`). **Before you edit any of your files, merge it into your branch** so we don't conflict:

```bash
git checkout gemini-reporting
git pull
git merge origin/capture-demo
```

## What I changed in your area

| File | What changed |
| --- | --- |
| `clearpath/contracts.py` (shared) | `OBSTRUCTION_TYPES` are now storm damage: Fallen tree or large branches, Storm debris pile, Flooding or standing water, **Downed power line**, Fallen sign/pole/fence, Displaced bin/vehicle/boat, Damaged or washed-out pavement, Other. New `HAZARD_TYPES = ("Downed power line",)`. Severities: Impassable / Partly blocked / Minor. Status "resolved" shows as **Cleared**. |
| `clearpath/reporting/gemini.py` | The prompt is now for a volunteer documenting hurricane damage: image 1 = before the storm, image 2 = after. It ignores wet pavement, never describes house numbers, flags anything wire-like as "Downed power line" in the first observation, and the impact sentence says who can't get through (on foot, wheelchair, stroller, cars, emergency vehicles). Schema unchanged. |
| `config/channels.json` | Three empty, unverified channels: **City/County storm debris and road clearing (311)**, **County emergency management (non-emergency line)**, **Electric utility: downed lines and outages (call 911 too)**. |
| `clearpath/reporting/report.py` | Titles say "Storm damage" instead of "Blocked walkway". Nothing else. |

The app now shows a red "treat it as live, stay 35 feet away, call 911 and the power company" warning whenever the damage type is a downed power line. A downed line is an emergency first, a report second.

## Your checklist, updated

- **Channels:** find each one on that organization's **own website**: the city/county storm-debris or 311 page, county emergency management's non-emergency contact, and the electric utility's downed-line number. Fill in `url`/`email`/`phone`, `source_page`, `verified_by`, `verified_on`, and set `verified: true`.
- **Gemini key + prompt:** test it on staged storm-debris photos (palm fronds, branches, a debris pile, a tipped bin, water on the path). Check that it picks the right type, doesn't call wet pavement damage, and flags anything wire-like as a downed power line.
- **PDF check:** print the HTML report once and check it on paper.

## Demo locations for testing

`python -m clearpath.demo` now creates four routes after a storm: Palm Street sidewalk (fallen tree), Bayview Avenue curb ramp (debris pile), Walkway to the community center (branches), 5th Avenue bus stop (flooding). All come out *Obstructed* after the storm and *Clear* after cleanup. `python -m clearpath.preflight --gemini` makes one real Gemini call on a demo pair once you have a key.
