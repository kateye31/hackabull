"""SQLite storage for issues. One table; aerial detections and resident reports share it."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,          -- aerial | resident
    category      TEXT NOT NULL,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    depth         TEXT,                   -- ankle | knee | waist | above_tire
    moving        INTEGER,                -- 1 moving, 0 still, NULL unknown
    blocks_road   INTEGER DEFAULT 0,
    note          TEXT,
    photo         TEXT,                   -- uploads/<file>
    area_m2       REAL,
    footprint_m2  REAL,
    affected_sqft REAL,
    status        TEXT NOT NULL DEFAULT 'New',
    scene         TEXT,
    crops         TEXT,                   -- json {"before": path, "after": path}
    history       TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""

COLUMNS = ["id", "source", "category", "lat", "lon", "depth", "moving", "blocks_road", "note", "photo",
           "area_m2", "footprint_m2", "affected_sqft", "status", "scene", "crops", "history",
           "created_at", "updated_at"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.conn() as c:
            c.executescript(SCHEMA)

    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["crops"] = json.loads(d["crops"]) if d["crops"] else None
        d["history"] = json.loads(d["history"] or "[]")
        d["blocks_road"] = bool(d["blocks_road"])
        d["moving"] = None if d["moving"] is None else bool(d["moving"])
        return d

    def all(self) -> list[dict]:
        with self.conn() as c:
            return [self._row(r) for r in c.execute("SELECT * FROM issues")]

    def get(self, iid: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM issues WHERE id = ?", (iid,)).fetchone()
            return self._row(r) if r else None

    def insert(self, issue: dict):
        t = now()
        row = {k: None for k in COLUMNS}
        row.update({"status": "New", "history": [], "created_at": t, "updated_at": t})
        row.update({k: v for k, v in issue.items() if k in row})
        row["history"] = json.dumps(row["history"] or [{"at": t, "status": "New"}])
        row["crops"] = json.dumps(row["crops"]) if row["crops"] else None
        with self.conn() as c:
            c.execute(f"INSERT INTO issues ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})",
                      [row[k] for k in COLUMNS])

    def upsert_detection(self, issue: dict, scene: str, detected_at: str):
        """Insert an aerial issue; if it already exists keep the crew's status and notes."""
        existing = self.get(issue["id"])
        if existing:
            with self.conn() as c:
                c.execute("UPDATE issues SET lat=?, lon=?, area_m2=?, crops=? WHERE id=?",
                          (issue["lat"], issue["lon"], issue.get("area_m2"),
                           json.dumps(issue.get("crops")), issue["id"]))
            return False
        self.insert({**issue, "scene": scene, "created_at": detected_at, "updated_at": detected_at})
        return True

    def update(self, iid: str, fields: dict) -> dict | None:
        cur = self.get(iid)
        if not cur:
            return None
        t = now()
        sets, vals = [], []
        for k in ("status", "affected_sqft", "note"):
            if k in fields:
                sets.append(f"{k} = ?")
                vals.append(fields[k])
        if "status" in fields and fields["status"] != cur["status"]:
            hist = cur["history"] + [{"at": t, "status": fields["status"]}]
            sets.append("history = ?")
            vals.append(json.dumps(hist))
        sets.append("updated_at = ?")
        vals.append(t)
        with self.conn() as c:
            c.execute(f"UPDATE issues SET {', '.join(sets)} WHERE id = ?", (*vals, iid))
        return self.get(iid)

    def next_resident_id(self) -> str:
        with self.conn() as c:
            n = c.execute("SELECT COUNT(*) FROM issues WHERE source = 'resident'").fetchone()[0]
        return f"R-{n + 1:04d}"

    def reset(self):
        with self.conn() as c:
            c.execute("DELETE FROM issues")
