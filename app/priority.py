"""Priority, next steps and cost range for each issue (the "What crews see" table).

All rules live here so the team can tune them in one place. compute() is called on
every read, so a rule change shows up on the map as soon as the server reloads.
"""
from __future__ import annotations

CATEGORIES = {
    "flooded_road": "Flooded road",
    "flooded_building": "Flooded building",
    "standing_water": "Standing water near homes",
    "debris": "Debris left by water",
}

# 1 = top of the list
PRIORITY_LABELS = {1: "Highest", 2: "High", 3: "Medium"}
BASE_PRIORITY = {"flooded_road": 1, "flooded_building": 2, "standing_water": 3, "debris": 3}

DEPTHS = ["ankle", "knee", "waist", "above_tire"]
DEPTH_LABELS = {"ankle": "Ankle", "knee": "Knee", "waist": "Waist", "above_tire": "Above a car tire"}

STATUSES = ["New", "Verified", "Assigned", "Cleared", "Dismissed"]
CLOSED = {"Cleared", "Dismissed"}

NEXT_STEPS = {
    "flooded_road": ["Mark road closed", "Route crews and rescue around it", "Recheck in a few hours"],
    "flooded_building": ["Pump out water", "Remove mud", "Cut out wet drywall", "Dry the structure", "Check for mold"],
    "standing_water": ["Pump out", "Clear storm drains"],
    "debris": ["Clear debris", "Haul away"],
}

# Cost guide. Contaminated (storm) floodwater removal + drying runs about $7.00-$7.50
# per sq ft (Bob Vila water damage restoration cost guide, cited in the proposal).
CLEANUP_PER_SQFT = (7.00, 7.50)
# PLACEHOLDERS - replace with sourced numbers before the demo and cite them.
DRYWALL_PER_SQFT = (2.00, 3.50)    # flood-cut drywall replacement, per sq ft of floor affected
STANDING_WATER_FLAT = (150, 500)   # pump-out + drain clearing visit
DEBRIS_FLAT = (300, 1_200)         # clear + haul one site


def compute(issue: dict) -> dict:
    cat = issue.get("category") or "standing_water"
    depth = issue.get("depth")
    blocks_road = bool(issue.get("blocks_road")) or cat == "flooded_road"

    p = BASE_PRIORITY.get(cat, 3)
    reasons = []
    if blocks_road:
        p = 1
        reasons.append("blocks road access")
    if depth in ("waist", "above_tire") and p > 1:
        p -= 1
        reasons.append(f"{DEPTH_LABELS[depth].lower()}-deep water")
    if issue.get("moving") and p > 1:
        p -= 1
        reasons.append("moving water")

    return {
        "category_label": CATEGORIES.get(cat, cat),
        "priority": p,
        "priority_label": PRIORITY_LABELS[p],
        "priority_reasons": reasons,
        "depth_label": DEPTH_LABELS.get(depth) if depth else None,
        "next_steps": NEXT_STEPS.get(cat, []),
        "cost": cost(cat, issue.get("affected_sqft")),
        "open": issue.get("status", "New") not in CLOSED,
    }


def cost(cat: str, sqft: float | None) -> dict:
    if cat == "flooded_road":
        return {"low": None, "high": None, "text": "None; flagged for rescue routing", "needs_sqft": False}
    if cat == "flooded_building":
        if not sqft:
            return {
                "low": None, "high": None, "needs_sqft": True,
                "text": f"${CLEANUP_PER_SQFT[0]:.2f}–${CLEANUP_PER_SQFT[1]:.2f} per sq ft + drywall. Enter affected sq ft after inspection.",
            }
        lo = sqft * (CLEANUP_PER_SQFT[0] + DRYWALL_PER_SQFT[0])
        hi = sqft * (CLEANUP_PER_SQFT[1] + DRYWALL_PER_SQFT[1])
        return {"low": round(lo), "high": round(hi), "needs_sqft": True,
                "text": f"${lo:,.0f}–${hi:,.0f} for {sqft:,.0f} sq ft (cleanup + drywall)"}
    flat = STANDING_WATER_FLAT if cat == "standing_water" else DEBRIS_FLAT
    return {"low": flat[0], "high": flat[1], "needs_sqft": False, "text": f"${flat[0]:,}–${flat[1]:,} flat"}


def sort_key(issue: dict):
    """Open before closed, then priority, then deeper water, then oldest first."""
    depth_rank = DEPTHS.index(issue["depth"]) if issue.get("depth") in DEPTHS else -1
    return (not issue["open"], issue["priority"], -depth_rank, issue.get("created_at", ""))
