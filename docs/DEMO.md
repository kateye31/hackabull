# Demo playbook (Person 1)

The story: **after a hurricane, a neighborhood needs to know which streets, sidewalks and walkways are passable, and the city needs to know what to clear first.** ClearPath compares a before-storm photo of each route with an after-storm photo, a person confirms the damage, the report goes to the right office, and an after-cleanup photo closes it.

Three jobs: take real photos, check the laptop in the room, rehearse. Each section ends with how you know it's done.

## 1. Photo shoot in the neighborhood (about 45 minutes)

You can't schedule a hurricane, so **stage the storm damage**. Pick 2–3 routes near the venue that people would need after a storm: the sidewalk to a bus stop, a curb ramp, the walkway to a community building. For each one, make a folder, e.g. `photos/palm-bus/`, and take three photos **from the same spot, same zoom, landscape**:

| File | What | Notes |
| --- | --- | --- |
| `reference.jpg` | **Before the storm**: the route clear | Required. |
| `blocked.jpg` | **After the storm**: same spot with storm debris | Required. Use what a storm actually leaves: fallen palm fronds, branches, a pile of yard waste, a board or tarp, a tipped-over trash bin. Spread it **across the sidewalk** (never in the street) so it covers a good chunk of the frame. |
| `cleared.jpg` | **After cleanup**: same spot, debris gone | Optional, but you need it for the last step in the backup run. |

How to stand in the same spot every time:

- Pick a fixed mark: a hydrant, a street sign, a mailbox, a driveway edge. Write down "next to the hydrant, facing the bus shelter." You'll pass this as `--where`.
- Hold the phone at chest height. Frame the route so it runs up the middle of the picture.
- No people's faces, licence plates or house numbers. Wait for people and cars to pass, and stay on public sidewalk.
- Clean up every bit of staged debris when you're done.
- iPhone: set **Settings → Camera → Formats → Most Compatible** first, or the photos come out as HEIC and the import refuses them.

Extras are free evaluation data for Person 2: a different kind of debris, a clear shot with a long shadow, and a clear shot of **wet pavement** (after rain, or hose a patch down). Wet ground after a storm is the false alarm we most need to test.

Then, on the laptop:

```bash
python -m clearpath.demo real "Palm St bus stop" photos/palm-bus --where "Next to the hydrant, facing the shelter" --eval
python -m clearpath.demo list
```

`--eval` also copies each set into `data/eval/real/` as labeled pairs (`blocked` → obstructed, `cleared` → clear), in the layout Person 2's `evaluation/evaluate.py` reads. Tell Person 2 when they're there.

**Done when:** `demo list` shows your real locations with `demo photos: initial, follow_up`, and in the app each one gets a red **Obstructed** after the storm and a green **Clear** after cleanup. If a spot comes back *Uncertain*, retake `blocked.jpg` with more debris in the frame, or tell Person 2 (it's the threshold re-tune they're doing).

## 2. Laptop check, in the presenting room

Do this on the actual demo laptop, on the room's Wi-Fi, with the browser closed (Windows lets only one app use the camera at a time):

```bash
python -m clearpath.preflight            # add --gemini once Person 3 has a key
streamlit run app.py
```

The preflight checks packages, that the data folder is writable, that DINOv2 is **already downloaded** (so the demo doesn't depend on venue Wi-Fi), the camera, Gemini, verified channels, and that every location's photos exist on this laptop. Exit code 0 means nothing will break; read the warnings anyway.

Then in the browser:

- Open **http://localhost:8501**. Don't use the "Network URL": browsers block the camera on plain-http addresses other than localhost.
- Allow camera access when asked. If you said no once, click the camera icon in the address bar to reset it.
- The laptop webcam faces *you*, not a street. For the live part, build a **tabletop street**: point the webcam (or a USB webcam) at a clear patch of table, add it on **Locations** as "Demo table" with the Camera option (that's the before-storm photo), then drop a handful of twigs and leaves or a crumpled bag across it (the storm). Check the lighting: projector lights can make frames very dark or blown out.
- Run one full inspection with the camera: after-storm photo → Obstructed → review → mark as sent → clear the table → after-cleanup photo → **Confirm cleared**.

**Done when:** the preflight passes in the room and you've done one full camera inspection there.

## 3. Demo script (about 3 minutes)

Have the app open on **Inspect**, sidebar visible. Finish two inspections beforehand (one *Cleared*, one *Still blocked*) so **All inspections** looks like a real neighborhood after a storm.

| Time | Do | Say |
| --- | --- | --- |
| 0:00 | Locations page, point at a before-storm photo | "Before hurricane season, a neighborhood photographs the routes people depend on: the sidewalk to the bus stop, the curb ramps, the walkway to the community center." |
| 0:20 | Inspect → a real location (or Demo table) → Start → camera/Demo photo → **Check this photo** | "The storm passes. A neighbor goes back to the same spot and takes one photo." |
| 0:40 | Point at before / after / highlighted | "DINOv2 compares the two photos patch by patch and outlines what's new. Shadows and lighting changes mostly don't trip it; a debris pile does." Open **Comparison details**: "A pixel-diff baseline runs too, and here it misses it." (Bayview Avenue curb ramp shows this: DINOv2 *obstructed*, OpenCV *clear*.) |
| 1:10 | AI observations (if Gemini is on) | "Gemini drafts what it sees and who can't get through: wheelchair users, strollers, cars. It's labeled a draft. And if it sees a downed line, the app tells you to stay away and call 911 first." |
| 1:30 | Fill the review form, tick the box, **Confirm details** | "A person picks the damage type and how bad it is, and signs off. Nothing goes out unconfirmed." |
| 1:50 | Report: editable text, **Download printable report**, **Mark as sent** | "It goes to the verified storm-debris line with the photos attached, so the crew knows exactly what to bring." |
| 2:20 | After cleanup: cleared photo → **Confirm cleared** | "After the crew comes, same spot, same before-storm photo. It's clear, so the route is open again. If not, it goes back as still blocked." |
| 2:40 | **All inspections** | "Every route in the neighborhood and whether it's passable: a recovery map built one photo at a time." |

Demo locations:

- **Your real staged locations** first. They're the strongest evidence.
- **Bayview Avenue curb ramp** (synthetic debris pile): best for showing DINOv2 beating the baseline.
- **Palm Street sidewalk** (fallen tree), **Walkway to the community center** (branches), **5th Avenue bus stop** (flooding): all come out *Obstructed*, then *Clear* after cleanup. Use one to show it's not just flooding.

## 4. Backup plan

If anything goes wrong live, switch the photo source to **Demo photo** on a real-photo location and keep talking. Same flow, no camera, no network.

| Problem | Fix on stage |
| --- | --- |
| Camera black or "in use" | Close Teams/Zoom, or switch to **Demo photo** |
| Gemini slow or fails | It falls back to "No AI observations"; fill the form by hand and say "we never depend on the AI" (fitting: after a storm the network is often down) |
| Wi-Fi down | DINOv2 is cached (preflight checked), so only Gemini is affected |
| App crashes | `Ctrl+C`, `streamlit run app.py` again; inspections are saved in SQLite, so reopen from **All inspections** |

Rehearse the whole script twice: once with the camera, once on the backup path only. Time both.
