"""AI observations from Gemini (Person 3).

Gemini sees the clear-path reference and the new capture and describes what is
blocking the path. Its output is a DRAFT for the human reviewer, never a final
call, and the app labels it as AI-generated.

Needs GEMINI_API_KEY (or GOOGLE_API_KEY). Without a key, observe() returns
{"available": False, ...} and the reviewer fills in details by hand.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .. import config
from ..contracts import OBSTRUCTION_TYPES

PROMPT = """You are helping a volunteer document hurricane damage in a residential neighborhood.

Image 1 is a photo of a street, sidewalk or walkway taken BEFORE the storm, when it was clear.
Image 2 is a photo of the same spot taken AFTER the storm.
{vision_hint}

Compare them and describe what storm damage, if any, now blocks or narrows the route.
Rules:
- Describe only what is visible. If unsure, say so and lower your confidence.
- Ignore differences in lighting, shadows, wet pavement, weather and camera angle.
- Do not identify or describe people, faces, licence plates or house numbers.
- If you see anything that could be a downed power line or wire, use "Downed power line" and say so in the first observation.
- obstruction_type must be one of: {types}, or "None" if the route is clear.
- observations: 2-5 short factual sentences a storm-debris or road crew can act on (what, where on the route, roughly how big).
- accessibility_impact: one sentence on who can no longer get through: people on foot, wheelchair or stroller users, cars, emergency vehicles.
- suggested_action: one sentence on what the cleanup crew or utility should do.
"""


class Observation(BaseModel):
    path_blocked: bool
    obstruction_type: str
    observations: list[str] = Field(default_factory=list)
    accessibility_impact: str = ""
    suggested_action: str = ""
    confidence: str = Field(description="low, medium or high")


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


def observe(reference_path: Path | str, capture_path: Path | str, comparison: dict | None = None) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not available():
        return {"available": False, "reason": "No GEMINI_API_KEY set; fill in details by hand.", "generated_at": stamp}
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"available": False, "reason": "google-genai is not installed.", "generated_at": stamp}

    hint = ""
    if comparison:
        hint = (f"An image comparison flagged about {comparison['changed_fraction']:.0%} of the scene as changed "
                f"(verdict: {comparison['verdict']}). Treat this as a hint, not a fact.")
    prompt = PROMPT.format(vision_hint=hint, types=", ".join(OBSTRUCTION_TYPES))
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=Path(reference_path).read_bytes(), mime_type="image/jpeg"),
                types.Part.from_bytes(data=Path(capture_path).read_bytes(), mime_type="image/jpeg"),
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
    return {"available": True, "model": config.GEMINI_MODEL, "generated_at": stamp, **out}
