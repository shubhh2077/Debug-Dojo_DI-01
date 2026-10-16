"""Small SQLite persistence layer for submissions."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SubmissionStore:
    def __init__(self, path: str | Path = "data/debug_dojo.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY, learner_id TEXT NOT NULL,
                    challenge_id TEXT NOT NULL, code TEXT NOT NULL,
                    created_at TEXT NOT NULL, outcomes TEXT NOT NULL,
                    mistake_tags TEXT NOT NULL, hint_level INTEGER NOT NULL DEFAULT 0,
                    hints_used INTEGER NOT NULL DEFAULT 0
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, learner_id: str, challenge_id: str, code: str,
             outcomes: dict[str, Any], mistake_tags: list[str]) -> str:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM submissions").fetchone()
            submission_id = f"s_{(row[0] + 1):04d}"
            db.execute(
                """INSERT INTO submissions
                (id, learner_id, challenge_id, code, created_at, outcomes, mistake_tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (submission_id, learner_id, challenge_id,
                 code, datetime.now(timezone.utc).isoformat(),
                 json.dumps(outcomes), json.dumps(mistake_tags)),
            )
            return submission_id

    def get(self, submission_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["outcomes"] = json.loads(result["outcomes"])
            result["mistake_tags"] = json.loads(result["mistake_tags"])
            return result
