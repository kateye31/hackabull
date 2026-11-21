# Notes for Person 3 (Gemini and reporting), from Person 1

## We switched from campus to neighborhood sidewalks

ClearPath now covers **neighborhood sidewalks reported to the city**, not campus walkways reported to the university. It's all on `capture-demo` (commit `2abd36b`). I had to touch three of your files for the wording:

| File | What changed |
| --- | --- |
| `config/channels.json` | The two channels are now **"City 311 service request"** (`id: city311`) and **"City ADA coordinator"** (`id: ada`). Both are still empty and `verified: false`. |
| `clearpath/reporting/gemini.py` | Prompt: "neighborhood sidewalk accessibility inspector", "sidewalk" instead of "walkway", and the audience is "a city public works crew" instead of facilities. Logic and schema unchanged. |
| `clearpath/reporting/report.py` | Titles say "Blocked sidewalk" instead of "Blocked walkway". Nothing else. |

**Before you edit any of those three files, merge my changes into your branch first** to avoid merge conflicts later:

```bash
git checkout gemini-reporting
git fetch origin
git merge origin/capture-demo
```

## Your checklist, updated

- **Reporting channel:** find the **city's** official way to report a blocked sidewalk, not the university's. Look for a 311 service request (often a "sidewalk obstruction" or "sidewalk repair" category), public works, or the city's ADA coordinator. Copy the URL/email/phone from the city's own website into `config/channels.json`, fill in `source_page`, `verified_by`, `verified_on`, and set `verified: true`. If the city uses an app (SeeClickFix etc.), only list it if the city's own site links to it.
- **Gemini prompt:** test it on real sidewalk photos. Sidewalk-specific things to watch: trash and recycling bins on collection day, cars parked across the sidewalk, overgrown hedges, and e-scooters. Check that it still refuses to describe people, licence plates and **house numbers** (worth adding to the rules list; I didn't change the rules).
- **PDF check:** unchanged. Print the HTML report once and check it on paper.

## Demo locations for testing

`python -m clearpath.demo` now creates Oak Street sidewalk, Maple Avenue curb ramp and 5th Avenue bus stop. All three come out *Obstructed* on the blocked photo and *Clear* on the follow-up, so they're good for testing Gemini output and the report end to end. `python -m clearpath.preflight --gemini` makes one real Gemini call on a demo pair once you have a key.
