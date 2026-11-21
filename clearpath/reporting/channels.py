"""Where reports go (Person 3). Only channels someone has verified are offered."""
from __future__ import annotations

import json
from pathlib import Path

from .. import config


def load(path: Path | None = None) -> list[dict]:
    p = Path(path or config.CHANNELS_FILE)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("channels", [])


def is_verified(ch: dict) -> bool:
    return bool(ch.get("verified") and (ch.get("url") or ch.get("email") or ch.get("phone"))
                and ch.get("verified_by") and ch.get("verified_on"))


def verified(path: Path | None = None) -> list[dict]:
    return [c for c in load(path) if is_verified(c)]


def contact_line(ch: dict) -> str:
    parts = [ch.get("url"), ch.get("email"), ch.get("phone")]
    return " · ".join(p for p in parts if p)
