"""Response plan for one report: priority, crew, equipment, steps, safety, who to call (Person 3).

With a Gemini key, Gemini plans it as an agent: it gets the confirmed details, the damage
numbers and a `find_nearby(category)` tool it can call to look up real contractors and
resources from OpenStreetMap, and returns a structured plan. Without a key (or if the call
fails), the same structure comes from rules, so the demo never depends on the network.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .. import config
from . import resources

RULES = {
    "Fallen tree or large branches": ("Tree crew with chainsaws",
                                      ["chainsaw", "truck or chipper for the wood", "cones or barricade tape"]),
    "Storm debris pile": ("Debris pickup crew", ["truck or trailer", "heavy gloves", "loader for large piles"]),
    "Flooding or standing water": ("Road and drainage crew", ["water pump", "barricades", "'road flooded' signs"]),
    "Downed power line": ("Electric utility crew (only they touch the line)", ["nothing: keep people away"]),
    "Fallen sign, pole or fence": ("Public works or builder", ["truck", "hand tools", "replacement sign or fence panel"]),
    "Displaced bin, vehicle or boat": ("Tow truck, or the owner", ["tow truck", "trailer for boats"]),
    "Damaged or washed-out pavement": ("Road repair crew", ["barricades", "cold-patch asphalt or gravel"]),
    "Other": ("Public works crew", ["truck", "hand tools"]),
}
SAFETY = {
    "Downed power line": ["Treat the line as live. Stay at least 35 feet (10 m) away and keep others back.",
                          "Call 911 and the power company before anything else.",
                          "Don't touch anything the line is touching, including fences, cars and water."],
    "Flooding or standing water": ["Don't walk or drive through flood water: 6 inches of moving water can knock a "
                                   "person down and 1 foot can carry away a car (National Weather Service).",
                                   "Flood water can hide open drains and live wires."],
    "Fallen tree or large branches": ["Look up and around for hanging branches and wires before going near.",
                                      "Only trained people should use chainsaws on storm-damaged trees."],
}
STEPS = {
    "Downed power line": ["Call 911 and the power company", "Block off the area from a safe distance",
                          "Utility de-energises and repairs the line", "Then clear any debris"],
    "Flooding or standing water": ["Put up 'road flooded' signs or barricades", "Check drains for blockage",
                                   "Pump or wait for the water to drop", "Check the pavement underneath for washouts"],
    "Fallen tree or large branches": ["Check for wires in the tree", "Cut a path through first so people can pass",
                                      "Remove the rest of the tree", "Sweep the route"],
}


class Contact(BaseModel):
    name: str
    category: str = ""
    why: str = ""
    phone: str = ""
    distance_m: int | None = None


class Plan(BaseModel):
    priority: str = Field(description="Critical, High, Medium or Low")
    summary: str
    crew: str
    equipment: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    safety: list[str] = Field(default_factory=list)
    call_first: list[Contact] = Field(default_factory=list)


def priority(damage_type: str | None, severity: str | None, damage_index: float | None) -> str:
    if damage_type == "Downed power line":
        return "Critical"
    if severity and severity.startswith("Impassable"):
        return "Critical" if damage_type == "Flooding or standing water" else "High"
    if (severity and severity.startswith("Partly")) or (damage_index or 0) >= 15:
        return "Medium"
    return "Low"


def _contacts(near: dict, damage_type: str | None, limit: int = 4) -> list[dict]:
    out = []
    for cat in resources.needed_categories(damage_type):
        for p in near.get("by_category", {}).get(cat, [])[:1]:
            out.append({"name": p["name"], "category": p["category_label"], "phone": p["phone"],
                        "distance_m": p["distance_m"], "why": f"Closest {p['category_label'].lower()}"})
    return out[:limit]


def rule_plan(damage_type: str | None, severity: str | None, damage_index: float | None, near: dict,
              place: str = "") -> dict:
    t = damage_type if damage_type in RULES else "Other"
    crew, equipment = RULES[t]
    pr = priority(damage_type, severity, damage_index)
    who = "Needs the utility first." if t == "Downed power line" else f"Send: {crew.lower()}."
    return Plan(priority=pr, summary=f"{t} at {place or 'this spot'}. {severity or ''} {who}".strip(),
                crew=crew, equipment=equipment, steps=STEPS.get(t, ["Block off the hazard", "Clear the route",
                                                                    "Take an after-cleanup photo to close it"]),
                safety=SAFETY.get(t, []), call_first=[Contact(**c) for c in _contacts(near, damage_type)]).model_dump()


GEMINI_PROMPT = """You coordinate neighborhood recovery after a hurricane.
A reviewer confirmed this report:
{facts}

Plan the response for a city or volunteer crew. Use the find_nearby tool to look up real
nearby contractors and resources (call it for each category you need; categories: {cats}).
Only recommend places the tool returned. Put safety first: downed lines mean 911 and the utility.

Reply with ONLY a JSON object with keys: priority (Critical/High/Medium/Low), summary (2 sentences),
crew, equipment (list), steps (ordered list, max 5), safety (list), call_first (list of
{{name, category, why, phone, distance_m}}, max 4).
"""


def gemini_plan(facts: dict, lat: float, lon: float, elements: list[dict]) -> dict | None:
    """Gemini with a find_nearby tool (automatic function calling). None if unavailable or it fails."""
    if not config.GEMINI_API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    def find_nearby(category: str) -> list[dict]:
        """Closest places in one category near the damaged spot.

        Args:
            category: one of tree_service, hardware, builder, electrician, plumber, waste, towing,
                fire, hospital, shelter, pharmacy, fuel.
        """
        if category not in resources.CATEGORIES:
            return []
        got = resources.nearby(lat, lon, [category], per_category=5, elements=elements)
        return [{k: p[k] for k in ("name", "category_label", "phone", "distance_m", "address")}
                for p in got["by_category"].get(category, [])]

    prompt = GEMINI_PROMPT.format(facts=json.dumps(facts, indent=1), cats=", ".join(resources.CATEGORIES))
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(tools=[find_nearby], temperature=0.2))
        m = re.search(r"\{.*\}", resp.text or "", re.S)
        return Plan.model_validate_json(m.group(0)).model_dump() if m else None
    except Exception:
        return None


def make_plan(bundle: dict) -> dict:
    """Plan for an inspection bundle. Uses confirmed review details first, then the ML suggestion."""
    loc = bundle["location"]
    review = bundle.get("review") or {}
    comp = ((bundle.get("initial") or {}).get("comparison") or {})
    dmg = comp.get("details", {}).get("damage", {}) if comp else {}
    obs = ((bundle.get("initial") or {}).get("observation") or {})
    dtype = review.get("obstruction_type") or dmg.get("likely_type") or (
        obs.get("obstruction_type") if obs.get("available") else None)
    severity = review.get("severity") or dmg.get("suggested_severity")
    di = dmg.get("damage_index")
    lat, lon = loc.get("lat"), loc.get("lon")
    elements = resources.fetch(lat, lon) if lat is not None and lon is not None else None
    near = resources.nearby(lat, lon, resources.needed_categories(dtype), elements=elements) if elements is not None \
        else resources.for_damage(lat, lon, dtype)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan = None
    if elements is not None and review.get("confirmed"):
        facts = {"place": loc["name"], "damage_type": dtype, "severity": severity, "damage_index": di,
                 "blocked_share": dmg.get("blocked_share"), "description": review.get("description"),
                 "exact_spot": review.get("location_note")}
        plan = gemini_plan(facts, lat, lon, elements)
    source = "gemini" if plan else "rules"
    plan = plan or rule_plan(dtype, severity, di, near, loc["name"])
    return {"source": source, "model": config.GEMINI_MODEL if source == "gemini" else None,
            "damage_type": dtype, "generated_at": stamp, "plan": plan, "nearby": near}
