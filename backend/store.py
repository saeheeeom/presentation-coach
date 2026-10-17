"""SQLite persistence for scripts and practice runs.

Data lives in $PC_DATA_DIR (default ./data): coach.db plus audio/<run_id>.webm.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from .timing import PracticeSession

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    wpm REAL NOT NULL,
    time_limit_s REAL,
    segments TEXT NOT NULL,          -- JSON list of {text, word_count, target_seconds}
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    script_id INTEGER NOT NULL REFERENCES scripts(id),
    started_at REAL NOT NULL,
    state TEXT NOT NULL,
    total_seconds REAL,
    durations TEXT,                  -- JSON list, null for undelivered segments
    attempts TEXT,                   -- JSON list of Attempt
    audio_path TEXT
);
"""


class Store:
    def __init__(self, data_dir: str | os.PathLike | None = None):
        self.data_dir = Path(data_dir or os.environ.get("PC_DATA_DIR", "data"))
        self.audio_dir = self.data_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.data_dir / "coach.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    # --- scripts ---------------------------------------------------------
    def create_script(self, title: str, wpm: float, time_limit_s: float | None, segments: list[dict]) -> int:
        cur = self.db.execute(
            "INSERT INTO scripts (title, wpm, time_limit_s, segments, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, wpm, time_limit_s, json.dumps(segments), time.time()),
        )
        self.db.commit()
        return cur.lastrowid

    def get_script(self, script_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        if row is None:
            return None
        return {**dict(row), "segments": json.loads(row["segments"])}

    def list_scripts(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT s.id, s.title, s.created_at, COUNT(r.id) AS runs "
            "FROM scripts s LEFT JOIN runs r ON r.script_id = s.id "
            "GROUP BY s.id ORDER BY s.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- runs ------------------------------------------------------------
    def create_run(self, script_id: int) -> int:
        cur = self.db.execute(
            "INSERT INTO runs (script_id, started_at, state) VALUES (?, ?, 'idle')",
            (script_id, time.time()),
        )
        self.db.commit()
        return cur.lastrowid

    def save_run(self, run_id: int, session: PracticeSession, now: float) -> None:
        self.db.execute(
            "UPDATE runs SET state = ?, total_seconds = ?, durations = ?, attempts = ? WHERE id = ?",
            (
                session.state,
                round(session.elapsed(now), 3),
                json.dumps(session.durations),
                json.dumps([asdict(a) for a in session.attempts]),
                run_id,
            ),
        )
        self.db.commit()

    def set_audio(self, run_id: int, path: Path) -> None:
        self.db.execute("UPDATE runs SET audio_path = ? WHERE id = ?", (str(path), run_id))
        self.db.commit()

    def list_runs(self, script_id: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM runs WHERE script_id = ? ORDER BY started_at", (script_id,)
        ).fetchall()
        return [
            {
                **dict(r),
                "durations": json.loads(r["durations"] or "[]"),
                "attempts": json.loads(r["attempts"] or "[]"),
            }
            for r in rows
        ]
