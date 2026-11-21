# Demo playbook (Person 1)

Three jobs: take real photos, check the laptop in the room, rehearse. Each section ends with the command that proves it's done.

## 1. Photo shoot in the neighborhood (about 30 minutes)

Pick 2–3 sidewalk spots near the venue: a curb ramp, a bus stop, a stretch of sidewalk in front of a row of houses. For each one, make a folder named after the spot, e.g. `photos/oak-3rd/`, and take three photos **from the same spot, same zoom, landscape**:

| File | What | Notes |
| --- | --- | --- |
| `reference.jpg` | The sidewalk when it's **clear** | Required. |
| `blocked.jpg` | Same spot with something in the way | Required. Use your own stuff: a backpack, a bike, a chair, a recycling bin. Put it **in the middle of the sidewalk**, never in the street, and make it cover a decent chunk of the frame. |
| `cleared.jpg` | Same spot, clear again, a few minutes later | Optional, but you need it for the follow-up step in the backup run. |

How to stand in the same spot every time:

- Pick a fixed mark: a curb ramp, a hydrant, a street sign, a driveway edge. Write down "toes on the curb ramp at Oak & 3rd, facing north." You'll pass this as `--where`.
- Hold the phone at chest height. Frame the sidewalk so it runs up the middle of the picture.
- No people's faces, licence plates or house numbers. Wait for people and cars to pass, and stay on public sidewalk (don't photograph into yards or windows).
- iPhone: set **Settings → Camera → Formats → Most Compatible** first, or the photos come out as HEIC and the import refuses them.

Take a few extra blocked/clear shots at each spot (different object, shadow, a step to the left). They're free evaluation data for Person 2.

Then, on the laptop:

```bash
python -m clearpath.demo real "Oak St & 3rd" photos/oak-3rd --where "Toes on the curb ramp, facing north" --eval
python -m clearpath.demo list
```

`--eval` also copies each set into `data/eval/real/` as labeled pairs (`blocked` → obstructed, `cleared` → clear), in the layout Person 2's `evaluation/evaluate.py` reads. Tell Person 2 when they're there.

**Done when:** `demo list` shows your real locations with `demo photos: initial, follow_up`, and in the app each one gets a red **Obstructed** on the blocked photo and green **Clear** on the cleared one. If a real spot comes back *Uncertain*, retake `blocked.jpg` with the object bigger in the frame, or tell Person 2 (it's the threshold re-tune they're doing).

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
- The laptop webcam faces *you*, not a sidewalk. For the live part, use the **tabletop sidewalk**: point the webcam (or a USB webcam) at a clear patch of table or floor, add it on **Locations** as "Demo table" with the Camera option, then put a water bottle or bag in the middle. Check the lighting: the room's projector lights can make frames very dark or blown out.
- Run one full inspection with the camera: capture → Obstructed → review → mark as sent → remove the object → follow-up → Confirm resolved.

**Done when:** the preflight passes in the room and you've done one full camera inspection there.

## 3. Demo script (about 3 minutes)

Have the app open on **Inspect**, sidebar visible. Two inspections already finished (one *Resolved*, one *Still blocked*) make **All inspections** look real.

| Time | Do | Say |
| --- | --- | --- |
| 0:00 | Locations page, point at a real reference photo | "Every sidewalk spot gets one photo of what clear looks like. That's what we compare against." |
| 0:20 | Inspect → real location (or Demo table) → Start → capture/Demo photo → **Check this photo** | "A neighbor sees a scooter dumped across the curb ramp and takes a photo from the same spot." |
| 0:40 | Point at the three images and the red outline | "DINOv2 compares the two photos patch by patch and outlines what's new. Lighting changes don't trip it; a bike does." Open **Comparison details**: "The pixel-diff baseline runs too, and here it misses it." (Oak Street sidewalk shows this: DINOv2 *obstructed*, OpenCV *clear*.) |
| 1:10 | AI observations (if Gemini is on) | "Gemini drafts a description. It's labeled as a draft, and nothing goes out until a person confirms it." |
| 1:30 | Fill the review form, tick the box, **Confirm details** | "The reviewer picks the type and severity and signs off." |
| 1:50 | Report: show the editable text, **Download printable report**, **Mark as sent** | "It goes to the city's verified reporting channel, 311 or public works, with the photos attached." |
| 2:20 | Follow-up: cleared photo → **Confirm resolved** | "Later, same spot, same reference. It's clear, so we close it. If it weren't, it goes back as still blocked." |
| 2:40 | **All inspections** | "Every sidewalk spot, its status, and its history." |

Use these demo locations:

- **Your real neighborhood locations** first. They're the strongest evidence.
- **Oak Street sidewalk** (synthetic): best for showing DINOv2 beating the baseline.
- **Maple Avenue curb ramp** and **5th Avenue bus stop** (synthetic): both come out *Obstructed*, then *Clear* on follow-up.

## 4. Backup plan

If anything goes wrong live, switch the photo source to **Demo photo** on a real-photo location and keep talking. Same flow, no camera, no network.

| Problem | Fix on stage |
| --- | --- |
| Camera black or "in use" | Close Teams/Zoom, or switch to **Demo photo** |
| Gemini slow or fails | It falls back to "No AI observations"; fill the form by hand and say "we never depend on the AI" |
| Wi-Fi down | DINOv2 is cached (preflight checked), so only Gemini is affected |
| App crashes | `Ctrl+C`, `streamlit run app.py` again; inspections are saved in SQLite, so reopen from **All inspections** |

Rehearse the whole script twice: once with the camera, once on the backup path only. Time both.
