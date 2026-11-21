# Neighborhood pivot: imagery, AI and reporting (Person 3)

ClearPath now covers **neighborhood hazards on streets, sidewalks and the public right-of-way**:
storm debris, fallen trees, sand on roads, flooding, illegal dumping. The demo uses real
**before/after aerial imagery** from Tampa Bay after Hurricanes Helene (landfall Sep 26, 2024) and
Milton (Oct 9, 2024).

## 1. Data sources (free, no API key)

| Role | Source | What it is | Licence / credit |
| --- | --- | --- | --- |
| **Before** | [Esri World Imagery Wayback](https://livingatlas.arcgis.com/wayback/) | ~199 archived versions of Esri's basemap since 2014. Around Tampa it's State of Florida aerials, 7.5–15 cm/px. | Credit "Esri, Maxar, Earthstar Geographics, and the GIS User Community". Fine for a hackathon demo, not for a commercial product. |
| **After** | [NOAA NGS Emergency Response Imagery](https://storms.ngs.noaa.gov/) ([Milton](https://storms.ngs.noaa.gov/storms/milton/index.html), [Helene](https://storms.ngs.noaa.gov/storms/helene/index.html)) | Aerial photos flown a few days after each storm, in strips along the coast. | Public domain ([data.gov record](https://catalog.data.gov/dataset/2024-noaa-ngs-emergency-response-imagery-hurricane-milton)). |
| **Follow-up** | Esri Wayback "latest" | Newer basemap, if it was flown after the storm. | As above |

Esri's metadata service gives each image's real capture date, and `clearpath.satellite` writes
that date into `site.json` and the report. **Use the capture date, not the Wayback release date.**
Example: around Tampa, Esri's newest image (release 2026-11-18) was taken on 2023-02-26, before the
storms. The tool therefore refuses to use it as a "cleared" follow-up. Madeira Beach has a
2025-01-25 image, so the full before/after/cleared story works there.

Other sources, if you need more:
- **NAIP** (USDA, 60 cm, public domain, flown every ~2 years), through Microsoft Planetary Computer.
  Needs `pystac-client` and `rasterio`.
- **Sentinel-2** (10 m). Too coarse for debris; useful only for flooding extent.
- **Maxar Open Data** releases disaster imagery at times. Check the licence before using it.

## 2. Getting the imagery

```bash
source .venv/bin/activate          # or pip install -r requirements.txt
python -m clearpath.satellite --demo                 # 3 preset sites, registered as app locations
python -m clearpath.satellite --list-esri            # every Esri release date
python -m clearpath.satellite --name "Bayshore & Howard" --lat 27.9301 --lon -82.4853 \
    --before esri:2024-09-19 --after noaa:milton --followup esri:latest --preview
```

- `--preview` saves the images to `data/demo/<slug>/` without adding a location. Look at them first.
- `--after noaa:helene | noaa:milton | noaa:ian | noaa:idalia | noaa:<layer-id>`. The tool tries
  each flight strip that covers the point and keeps the first one that has imagery.
- `--zoom 19` is about 30 cm per pixel over 230 m. Use `--zoom 20` to see curbside debris.

**Picking good spots** (do this first, it decides how good the demo looks):
1. Open the NOAA Milton or Helene viewer and find streets with visible curb debris, sand on the
   road or downed trees. The barrier islands (Madeira Beach, Treasure Island, Redington) show it
   most clearly. In Tampa, try Davis Islands, Bayshore, Ballast Point and Port Tampa.
2. Copy the lat/lon of the street from the map and run `--preview`.
3. Keep 2–3 sites where the difference is obvious, and drop the `--preview` flag to register them.

## 3. Gemini

- Get a key at <https://aistudio.google.com/apikey>, then run `export GEMINI_API_KEY=...`.
- Test without the app:
  ```bash
  python -m clearpath.reporting.gemini data/demo/<site>/reference.jpg data/demo/<site>/initial.jpg
  ```
  It prints the structured JSON and saves `gemini_boxes.jpg` with the boxes Gemini drew. Without a
  key, it prints the exact prompt it would send.
- The mode is chosen automatically. Locations made by `clearpath.satellite` use the **aerial**
  prompt, which is told about the image sources and dates and told to ignore colour and shadow
  differences. Webcam photos use the **ground** prompt.
- Output fields: `path_blocked`, `obstruction_type` (from `OBSTRUCTION_TYPES`), `observations`,
  `accessibility_impact`, `suggested_action`, `confidence`, and `regions` (0–1 boxes).
- Tuning: run it on every site, compare the output with what you can see, and edit
  `AERIAL_PROMPT` in [clearpath/reporting/gemini.py](../clearpath/reporting/gemini.py). Keep a few
  outputs, good and bad, for the pitch.

## 4. Reporting channels

[config/channels.json](../config/channels.json) now lists City of Tampa channels. Claude Code read
each one from tampa.gov on 2026-11-21:
- **Objects in the right-of-way**, through the Tampa Connect form. Emergency clean-up goes to
  (813) 274-3101, 24 hours a day.
- **Tampa Connect** (Customer Service Center), for general requests.
- **TECO emergency line** (813) 228-1111, for power lines brought down by fallen trees.

To do: open each link yourself and put your name in `verified_by`. Two channels are still
unverified. The **illegal dumping** page returned 404, so find the current one. **Madeira Beach**
is only needed if you demo that preset, because it isn't City of Tampa.

## 5. What changed in the code

| File | Change |
| --- | --- |
| `clearpath/satellite.py` (new) | Esri Wayback and NOAA tile fetch, mosaic, capture-date lookup, sites → locations |
| `clearpath/reporting/gemini.py` | Aerial and ground prompts, image-date context, `regions` boxes, CLI test |
| `clearpath/reporting/report.py` | Neighborhood wording, coordinates and map link, image sources and capture dates, attribution |
| `clearpath/contracts.py` | **Shared:** neighborhood `OBSTRUCTION_TYPES` and `SEVERITIES` |
| `config/channels.json` | City of Tampa channels |

**Tell your teammates:**
- **Person 1:** `contracts.py` hazard types changed. `app.py` still says "campus" or "walkway" in a
  few labels (lines ~1, 120, 201, 237, 309). Locations from `clearpath.satellite` reuse the
  `data/demo/` folder, so the "Demo photo" button works with them unchanged.
- **Person 2:** NOAA images are much darker and bluer than Esri's, so expect a large changed area
  across the whole image. Colour normalisation (for example, histogram matching to the reference)
  before comparing would help, and real before/after pairs for `evaluation/` can now come from
  `python -m clearpath.satellite`. Separately, with `torch` missing, `CLEARPATH_VISION=auto`
  crashes instead of falling back to OpenCV.

## 6. Pitch facts you can use (re-check numbers before quoting)

- NOAA flew post-Milton imagery Oct 11–14, 2024, and post-Helene imagery Sep 27 to Oct 8, 2024, all
  public domain.
- Esri imagery around Tampa is State of Florida aerials at 7.5–15 cm/px. That is enough to see curb
  debris piles and sand on roads, but not individual small objects.
- Limits: aerial images show only what's visible from above (not under tree canopy), and the
  imagery dates are fixed, so they aren't live. A person still confirms every report.
