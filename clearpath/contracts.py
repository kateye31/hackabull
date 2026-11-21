"""Hand-off contracts between the three roles. Change these together, not alone.

Person 1 (capture & demo)  --SavedCapture-->      Person 2 (vision & data)
Person 2                   --ComparisonResult-->  Person 1 (shows it) and Person 3 (uses it)
Person 1 (human review)    --ReviewedDetails-->   Person 3 (reporting)
Person 3                   --ReportOutput-->      Person 1 (edit, export)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

PHASES = ("initial", "follow_up")
PHASE_LABELS = {"initial": "Initial", "follow_up": "Follow-up"}

# Inspection lifecycle, in order.
STATUSES = ("captured", "reviewed", "reported", "resolved", "still_blocked", "dismissed")
STATUS_LABELS = {
    "captured": "Captured, needs review",
    "reviewed": "Reviewed, ready to report",
    "reported": "Reported, awaiting fix",
    "resolved": "Resolved",
    "still_blocked": "Follow-up: still blocked",
    "dismissed": "Dismissed (not an obstruction)",
}

# Neighborhood hazards on streets, sidewalks and the public right-of-way.
# Works for both ground photos and before/after aerial imagery (clearpath.satellite).
OBSTRUCTION_TYPES = (
    "Storm debris pile",
    "Fallen tree or limbs",
    "Sand or sediment on road",
    "Flooding or standing water",
    "Illegal dumping or bulk trash",
    "Vehicle, boat or object in right-of-way",
    "Construction or barrier",
    "Damaged road or sidewalk",
    "Damaged roof or structure",
    "Other",
)
SEVERITIES = (
    "Fully blocked: road or sidewalk impassable",
    "Partly blocked: passable with difficulty",
    "Minor: hazard beside the road or sidewalk",
)

VERDICTS = ("obstructed", "uncertain", "clear")


@dataclass
class SavedCapture:
    """Person 1 -> Person 2. One photo, tied to an inspection and a phase."""
    inspection_id: str
    phase: str               # "initial" | "follow_up"
    image_path: Path
    captured_at: str         # ISO 8601, UTC
    capture_id: int | None = None

    def __post_init__(self):
        if self.phase not in PHASES:
            raise ValueError(f"phase must be one of {PHASES}, got {self.phase!r}")
        self.image_path = Path(self.image_path)


@dataclass
class ComparisonResult:
    """Person 2 -> Persons 1 and 3. A capture compared against its clear-path reference."""
    method: str              # "dinov2" | "opencv"
    score: float             # 0 = looks like the clear path, 1 = clearly something new
    changed_fraction: float  # total share of the image flagged as changed, 0-1
    largest_region: float    # share covered by the biggest single changed region (drives the verdict)
    verdict: str             # "obstructed" | "uncertain" | "clear"
    overlay_path: Path       # capture with changed areas highlighted
    aligned: bool            # True if the capture was warped to line up with the reference
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overlay_path"] = str(self.overlay_path)
        return d


@dataclass
class ReviewedDetails:
    """Person 1's human review -> Person 3. Only confirmed details go in a report."""
    obstruction_type: str
    severity: str
    description: str
    location_note: str
    reviewer: str
    confirmed: bool
    reviewed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReportOutput:
    """Person 3 -> Person 1. Plain text people can edit, and printable HTML."""
    text: str
    html: str
    channel_name: str | None = None
    channel_verified: bool = False
