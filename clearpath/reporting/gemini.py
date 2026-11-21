"""AI observations from Gemini (Person 3).

Gemini sees the "before" reference and the new image of the same neighborhood
spot and describes hazards on the street, sidewalk or public right-of-way. Its
output is a DRAFT for the human reviewer, never a final call, and the app labels
it as AI-generated.

Two modes, picked automatically:
* ``aerial``: the location came from clearpath.satellite (site.json next to the
  reference). Both images are top-down aerial/satellite tiles of the same area.
* ``ground``: a phone/webcam photo compared with a street-level reference.

Needs GEMINI_API_KEY (or GOOGLE_API_KEY). Without a key, observe() returns
{"available": False, ...} and the reviewer fills in details by hand.

Quick test on real imagery (no app needed):
    python -m clearpath.reporting.gemini data/demo/<site>/reference.jpg data/demo/<site>/initial.jpg
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .. import config
from ..contracts import OBSTRUCTION_TYPES

COMMON_RULES = """
- Set path_blocked to true only if a hazard visibly occupies, narrows or damages
  a road, sidewalk, driveway apron or other public right-of-way. If nothing can
  be established, set it to false and obstruction_type to "None".
- If the images don't clearly show the same place, or the area is hidden
  (clouds, shadow, tree canopy, blur), say what cannot be judged, set confidence
  to "low", and suggest getting a clearer image. Lack of evidence is inconclusive.
- For a visible hazard, choose the primary obstruction_type from: {types}.
- Write 1-4 short factual observations: what changed, where it sits (use
  directions in the image: top-left, along the street running left-right, etc.)
  and what remains open. Avoid exact dimensions, legal or code-compliance
  judgments, and claims about cause, fault or ownership.
- Do not identify or describe people, faces, licence plates or specific homes'
  occupants. Refer to buildings generically ("the house at the top-right").
- Describe the likely impact on residents (access, mobility, emergency vehicles,
  drainage) and one practical action for the city in separate sentences. Use
  empty strings for these if nothing is found.
- In regions, list up to 5 boxes around the hazards in image 2 as
  [x_min, y_min, x_max, y_max] fractions of the image width/height (0-1).
  Each box must have positive width and height. Use [] if you cannot place a box.
"""

GROUND_PROMPT = """You are helping a resident document a neighborhood hazard for the city.

Image 1 is a reference photo of a street or sidewalk when it was clear.
Image 2 is a new photo of the same spot.
{context}

Find the same section in both photos using fixed landmarks (curbs, poles,
driveways, buildings). Ignore lighting, shadows, weather and camera angle.
""" + COMMON_RULES

AERIAL_PROMPT = """You are helping a neighborhood resilience team review aerial imagery.

Both images are top-down aerial/satellite views of the SAME area, north up,
same scale, roughly aligned.
Image 1 ("before"): {before}.
Image 2 ("after"): {after}.
{context}

Compare them and look for changes on streets, sidewalks, alleys and the strip
between road and property line: piles of debris or furniture at the curb, sand
or sediment covering pavement, fallen trees, standing water, boats/vehicles or
objects displaced into the road, washed-out or damaged pavement, and blue tarps
or missing roofing that signal structural damage nearby.

Ignore differences that are just the imagery: colour/brightness, sun angle and
shadows, seasonal vegetation, water colour, slight misalignment, and ordinary
parked cars. Don't overclaim from small or blurry features.

Limit a clear finding to the road segments you can see. Explicitly mention
sidewalks or road edges hidden by canopy, shadow or limited resolution.
Never infer wheelchair access, emergency vehicle access or municipal priority
from a clear-looking road. If no obstruction is visible, leave both
accessibility_impact and suggested_action empty, unless an inconclusive view
calls for a clearer image.
Always return at least one sentence in observations, even when path_blocked
is false. Name the visible road segment and any limits on what can be judged.
For a clearly located obstruction (path_blocked true and confidence high),
include at least one approximate box around the visible object in Image 2.
Use decimal fractions: the image center is (0.50, 0.50), the upper-left corner
is (0.00, 0.00), and the lower-right corner is (1.00, 1.00).
""" + COMMON_RULES


class Observation(BaseModel):
    path_blocked: bool
    obstruction_type: str
    observations: list[str] = Field(default_factory=list)
    accessibility_impact: str = ""
    suggested_action: str = ""
    confidence: str = Field(description="low, medium or high")
    regions: list[list[float]] = Field(default_factory=list,
                                       description="boxes [x_min, y_min, x_max, y_max] as 0-1 fractions of image 2")


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


def _mime(p: Path) -> str:
    return {".png": "image/png", ".webp": "image/webp"}.get(p.suffix.lower(), "image/jpeg")


def _describe(info: dict | None) -> str:
    if not info:
        return "date unknown"
    when = f"captured {info['captured']}" if info.get("captured") else "capture date unknown"
    return f"{info.get('label', 'imagery')}, {when}" + (f" ({info['detail']})" if info.get("detail") else "")


def build_prompt(reference_path: Path | str, comparison: dict | None = None, imagery: dict | None = None):
    """(mode, prompt). imagery = {"before": {...}, "after": {...}} or None to auto-detect from site.json."""
    if imagery is None:
        from .. import satellite
        meta = satellite.site_meta(reference_path)
        if meta:
            imgs = meta.get("images", {})
            imagery = {"before": imgs.get("reference.jpg"), "after": imgs.get("initial.jpg"),
                       "lat": meta.get("lat"), "lon": meta.get("lon")}
    context = ""
    if comparison:
        context = (f"An automatic image comparison flagged about {comparison['changed_fraction']:.0%} of the "
                   f"scene as changed (verdict: {comparison['verdict']}). Treat this as a weak hint, not a fact.")
    types = ", ".join(OBSTRUCTION_TYPES)
    if imagery:
        return "aerial", AERIAL_PROMPT.format(before=_describe(imagery.get("before")),
                                              after=_describe(imagery.get("after")), context=context, types=types)
    return "ground", GROUND_PROMPT.format(context=context, types=types)


def observe(reference_path: Path | str, capture_path: Path | str, comparison: dict | None = None,
            imagery: dict | None = None) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not available():
        return {"available": False, "reason": "No GEMINI_API_KEY set; fill in details by hand.", "generated_at": stamp}
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"available": False, "reason": "google-genai is not installed.", "generated_at": stamp}

    mode, prompt = build_prompt(reference_path, comparison, imagery)
    ref, cap = Path(reference_path), Path(capture_path)
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                "Image 1 (before / reference):",
                types.Part.from_bytes(data=ref.read_bytes(), mime_type=_mime(ref)),
                "Image 2 (after / new):",
                types.Part.from_bytes(data=cap.read_bytes(), mime_type=_mime(cap)),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Observation,
                temperature=0.2,
            ),
        )
        obs = resp.parsed if isinstance(resp.parsed, Observation) else Observation.model_validate_json(resp.text)
    except Exception as e:  # network, quota, bad key, safety block
        return {"available": False, "reason": f"Gemini call failed: {e}", "generated_at": stamp}

    out = obs.model_dump()
    if out["obstruction_type"] not in OBSTRUCTION_TYPES and out["obstruction_type"] != "None":
        out["obstruction_type"] = "Other"
    out["regions"] = _valid_regions(out["regions"])[:5]
    return {"available": True, "model": config.GEMINI_MODEL, "mode": mode, "generated_at": stamp, **out}


def _valid_regions(regions: list[list[float]]) -> list[list[float]]:
    boxes = []
    for region in regions:
        if len(region) != 4:
            continue
        x0, y0, x1, y1 = (min(max(value, 0.0), 1.0) for value in region)
        if x0 < x1 and y0 < y1:
            boxes.append([x0, y0, x1, y1])
    return boxes


def draw_regions(capture_path: Path | str, regions: list[list[float]], out_path: Path | str) -> Path | None:
    """Save a copy of the capture with Gemini's boxes drawn on it (for the report/app)."""
    regions = _valid_regions(regions)
    if not regions:
        return None
    from PIL import Image, ImageDraw
    img = Image.open(capture_path).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in regions:
        d.rectangle([x0 * w, y0 * h, x1 * w, y1 * h], outline=(255, 64, 32), width=max(3, w // 200))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python -m clearpath.reporting.gemini REFERENCE.jpg NEW.jpg")
    if not available():
        mode, prompt = build_prompt(sys.argv[1])
        print(f"No GEMINI_API_KEY set. Prompt that would be sent ({mode} mode):\n{prompt}")
        sys.exit(1)
    result = observe(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
    if not result["available"]:
        sys.exit(1)
    if result.get("regions"):
        p = draw_regions(sys.argv[2], result["regions"], Path(sys.argv[2]).with_name("gemini_boxes.jpg"))
        print(f"boxes drawn -> {p}")
