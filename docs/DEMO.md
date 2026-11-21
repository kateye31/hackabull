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
streamlit run app.py                     # reviewer:  http://localhost:8501
uvicorn api.main:app --port 8000         # residents: http://localhost:8000
```

The preflight checks packages, that the data folder is writable, that DINOv2, CLIP, SegFormer and RemoteCLIP are **already downloaded** (so the demo doesn't depend on venue Wi-Fi), the USGS imagery and OpenStreetMap services, the camera, Gemini, verified channels, and that every location's photos exist on this laptop. Add the demo locations **before** the event: that fetches the satellite images and the nearby-help lookup (about 45 s, once) and caches them. Exit code 0 means nothing will break; read the warnings anyway.

Then in the browser:

- Open **http://localhost:8501**. Don't use the "Network URL": browsers block the camera on plain-http addresses other than localhost.
- Allow camera access when asked. If you said no once, click the camera icon in the address bar to reset it.
- The laptop webcam faces *you*, not a street. For the live part, build a **tabletop street**: point the webcam (or a USB webcam) at a clear patch of table, add it on **Locations** as "Demo table" with the Camera option (that's the before-storm photo), then drop a handful of twigs and leaves or a crumpled bag across it (the storm). Check the lighting: projector lights can make frames very dark or blown out.
- Run one full report with the camera: **Report damage** → Demo table → camera → **Send report**, then **Review queue** → Open → confirm → mark as sent → clear the table → after-cleanup photo → **Confirm cleared**.

**Done when:** the preflight passes in the room and you've done one full camera inspection there.

## 3. Demo script (about 3 minutes)

Two websites, one database: **residents** use the residents' site (localhost:8000, the hi-vis one; open it in a phone-sized browser window), **the reviewer** works the Streamlit app (localhost:8501). Before you start, finish two reports (one *Cleared*, one *Awaiting cleanup*) so the queue looks real.

| Time | Do | Say |
| --- | --- | --- |
| 0:00 | Reviewer app → **Before-storm photos**: the map, one spot's photo and its satellite tile, "tree canopy 35%, storm risk high" | "Before hurricane season, a neighborhood photographs the routes people depend on. We pull the satellite view of each one and measure the tree canopy over it: that's where the storm will hit first." |
| 0:25 | Residents' site → photo (Demo photo or camera) → pick the spot or **Use my location** → note → **Send report** | "After the storm, a neighbor sends one photo. No account. Their phone's GPS puts it on the right spot." Point at the 911 power-line notice. Then the thank-you screen: "And they immediately get help near them: the nearest shelter, hospital, hardware store, with phone numbers." |
| 0:55 | Reviewer app → **Review queue** → *Needs review* → **Open** | "The reviewer sees every report in one queue, with the resident's note." |
| 1:05 | Before / after / highlighted, then **Damage analysis** | "DINOv2 finds what's new. SegFormer finds the walkway in the before photo, so we can measure: 38% of the walkway blocked, narrowest clear width 25%. CLIP suggests the kind of damage." Hover a metric to show the equation. |
| 1:30 | **Response plan** + nearby table | "From that, a plan: crew, equipment, steps, safety, and the real contractors nearby to call, from OpenStreetMap. With a Gemini key, Gemini plans it as an agent and looks up the contractors itself." |
| 1:50 | **From above: satellite check** (after using **Demo: synthetic damage** on that spot beforehand) | "From above, before vs after. This after image is synthetic for the demo; after a real storm it's NOAA's aerial survey or a drone." |
| 2:05 | Confirm details → **Mark as sent** | "A person signs off. Nothing goes out unconfirmed." |
| 2:20 | After cleanup: cleared photo → **Confirm cleared** | "Same spot, same before-storm photo: clear, so the route is open again." |
| 2:40 | **Back to queue** | "Every route in the neighborhood and whether it's passable. A recovery map built one photo at a time." |

Demo locations:

- **Your real staged locations** first. They're the strongest evidence, and the damage-type suggestions only work well on real photos.
- **Bayview Avenue curb ramp** (synthetic debris pile): DINOv2 *obstructed*, pixel baseline *clear*.
- The synthetic routes are cartoons: skip the "Looks like:" damage-type line on them (CLIP guesses wrong on drawings) and point at the walkway numbers instead.

## 4. Backup plan

If anything goes wrong live, switch the photo source to **Demo photo** on a real-photo location and keep talking. Same flow, no camera, no network.

| Problem | Fix on stage |
| --- | --- |
| Camera black or "in use" | Close Teams/Zoom, or switch to **Demo photo** |
| Gemini slow or fails | It falls back to "No AI observations"; fill the form by hand and say "we never depend on the AI" (fitting: after a storm the network is often down) |
| Wi-Fi down | Models, satellite images and nearby help are cached (preflight + demo locations added beforehand), so only Gemini is affected |
| Residents' site won't load | Use the reviewer app's **Report damage** page instead: same flow |
| App crashes | `Ctrl+C`, `streamlit run app.py` again; reports are saved in SQLite, so reopen from the **Review queue** |

Rehearse the whole script twice: once with the camera, once on the backup path only. Time both.
