"""SQLite storage (Person 2).

locations    a spot on campus and its clear-path reference photo
inspections  one problem at one location. Copies the reference path at creation,
             so the initial and follow-up captures are always compared against the
             SAME clear-path reference, even if the location's photo is replaced later.
captures     photos, each with a phase (initial | follow_up)
comparisons  vision result per capture
observations Gemini output per capture
reviews      human-confirmed details per inspection (latest wins)
reports      editable report text + exported HTML path per inspection
events       status history
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .contracts import STATUSES, ComparisonResult, ReviewedDetails, SavedCapture

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    reference_path TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY, location_id INTEGER NOT NULL REFERENCES locations(id),
    reference_path TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY, inspection_id TEXT NOT NULL REFERENCES inspections(id),
    phase TEXT NOT NULL CHECK (phase IN ('initial','follow_up')),
    image_path TEXT NOT NULL, captured_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comparisons (
    capture_id INTEGER PRIMARY KEY REFERENCES captures(id), result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations (
    capture_id INTEGER PRIMARY KEY REFERENCES captures(id), result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY, inspection_id TEXT NOT NULL REFERENCES inspections(id),
    details TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
    inspection_id TEXT PRIMARY KEY REFERENCES inspections(id), text TEXT NOT NULL,
    html_path TEXT, channel TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, inspection_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT, at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _c(self):
        with closing(sqlite3.connect(self.path)) as c, c:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            yield c

    # ---------- locations ----------
    def add_location(self, name: str, reference_path: Path, description: str = "") -> int:
        with self._c() as c:
            cur = c.execute("INSERT INTO locations (name, description, reference_path, created_at) VALUES (?,?,?,?)",
                            (name.strip(), description.strip(), str(reference_path), now()))
            return cur.lastrowid

    def locations(self) -> list[dict]:
        with self._c() as c:
            return [dict(r) for r in c.execute("SELECT * FROM locations ORDER BY name")]

    def location(self, location_id: int) -> dict | None:
        with self._c() as c:
            r = c.execute("SELECT * FROM locations WHERE id=?", (location_id,)).fetchone()
            return dict(r) if r else None

    # ---------- inspections ----------
    def new_inspection(self, location_id: int) -> str:
        with self._c() as c:
            c.execute("BEGIN IMMEDIATE")
            loc = c.execute("SELECT reference_path FROM locations WHERE id=?", (location_id,)).fetchone()
            if not loc:
                raise KeyError(f"no location {location_id}")
            n = c.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
            iid = f"INS-{n + 1:04d}"
            t = now()
            c.execute("INSERT INTO inspections VALUES (?,?,?,?,?,?)",
                      (iid, location_id, loc["reference_path"], "captured", t, t))
            c.execute("INSERT INTO events (inspection_id, status, note, at) VALUES (?,?,?,?)",
                      (iid, "captured", "inspection opened", t))
        return iid

    def set_status(self, inspection_id: str, status: str, note: str = ""):
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        t = now()
        with self._c() as c:
            c.execute("UPDATE inspections SET status=?, updated_at=? WHERE id=?", (status, t, inspection_id))
            c.execute("INSERT INTO events (inspection_id, status, note, at) VALUES (?,?,?,?)",
                      (inspection_id, status, note, t))

    def inspections(self) -> list[dict]:
        with self._c() as c:
            q = """SELECT i.*, l.name AS location_name FROM inspections i
                   JOIN locations l ON l.id = i.location_id ORDER BY i.updated_at DESC"""
            return [dict(r) for r in c.execute(q)]

    # ---------- captures + results ----------
    def add_capture(self, cap: SavedCapture) -> SavedCapture:
        with self._c() as c:
            cur = c.execute("INSERT INTO captures (inspection_id, phase, image_path, captured_at) VALUES (?,?,?,?)",
                            (cap.inspection_id, cap.phase, str(cap.image_path), cap.captured_at))
            cap.capture_id = cur.lastrowid
            c.execute("UPDATE inspections SET updated_at=? WHERE id=?", (now(), cap.inspection_id))
        return cap

    def save_comparison(self, capture_id: int, result: ComparisonResult):
        with self._c() as c:
            c.execute("INSERT OR REPLACE INTO comparisons VALUES (?,?,?)",
                      (capture_id, json.dumps(result.to_dict()), now()))

    def save_observation(self, capture_id: int, obs: dict):
        with self._c() as c:
            c.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?)", (capture_id, json.dumps(obs), now()))

    def save_review(self, inspection_id: str, details: ReviewedDetails):
        with self._c() as c:
            c.execute("INSERT INTO reviews (inspection_id, details, created_at) VALUES (?,?,?)",
                      (inspection_id, json.dumps(details.to_dict()), now()))

    def save_report(self, inspection_id: str, text: str, html_path: Path | None = None, channel: str | None = None):
        with self._c() as c:
            c.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?)",
                      (inspection_id, text, str(html_path) if html_path else None, channel, now()))

    # ---------- everything about one inspection ----------
    def bundle(self, inspection_id: str) -> dict | None:
        with self._c() as c:
            ins = c.execute("SELECT * FROM inspections WHERE id=?", (inspection_id,)).fetchone()
            if not ins:
                return None
            ins = dict(ins)
            loc = dict(c.execute("SELECT * FROM locations WHERE id=?", (ins["location_id"],)).fetchone())
            caps = {}
            for r in c.execute("SELECT * FROM captures WHERE inspection_id=? ORDER BY id", (inspection_id,)):
                cap = dict(r)
                comp = c.execute("SELECT result FROM comparisons WHERE capture_id=?", (cap["id"],)).fetchone()
                obs = c.execute("SELECT result FROM observations WHERE capture_id=?", (cap["id"],)).fetchone()
                cap["comparison"] = json.loads(comp[0]) if comp else None
                cap["observation"] = json.loads(obs[0]) if obs else None
                caps[cap["phase"]] = cap  # latest capture per phase wins
            rev = c.execute("SELECT details FROM reviews WHERE inspection_id=? ORDER BY id DESC LIMIT 1",
                            (inspection_id,)).fetchone()
            rep = c.execute("SELECT * FROM reports WHERE inspection_id=?", (inspection_id,)).fetchone()
            ev = [dict(r) for r in c.execute("SELECT status, note, at FROM events WHERE inspection_id=? ORDER BY id",
                                             (inspection_id,))]
        return {
            "inspection": ins,
            "location": loc,
            "reference_path": ins["reference_path"],
            "initial": caps.get("initial"),
            "follow_up": caps.get("follow_up"),
            "review": json.loads(rev[0]) if rev else None,
            "report": dict(rep) if rep else None,
            "events": ev,
        }
