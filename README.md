# ClearPath

Neighborhood storm damage check. Residents enter coordinates, upload a current outside photo, and view satellite imagery centered on that location. Gemini can identify visible flooding, affected houses and cars, fallen trees, blocked driveways, and debris. The app also finds nearby mapped shelters, hospitals, fire stations, and hardware stores.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Set `GEMINI_API_KEY` for AI assessment. Satellite imagery and nearby listings need internet access. The image comes from Esri World Imagery; nearby listings come from OpenStreetMap via Overpass. Listings are not live availability reports.

## How comparison works

The satellite image gives overhead location context. A ground-level photo cannot be pixel matched to an overhead image to prove a before/after change. For actual visible change detection, upload an older ground-level photo of the same spot. AI observations are suggestions that residents should verify.

The earlier campus walkway prototype remains in git history and its supporting modules are still in this repository.
