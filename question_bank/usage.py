"""Isolated best-effort gameplay usage telemetry."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from question_bank.contracts import stable_hash


class UsageSink:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "question_usage.sqlite3"
        self._db = sqlite3.connect(self.path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS usage_events(
                event_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                question_id TEXT NOT NULL, event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._db.commit()

    def append(
        self, *, idempotency_key: str, question_id: str, event_type: str, payload: dict
    ) -> str:
        event_id = f"usage-{stable_hash([idempotency_key, question_id, event_type, payload])[:24]}"
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO usage_events VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, idempotency_key, question_id, event_type, json.dumps(payload, sort_keys=True)),
            )
        row = self._db.execute(
            "SELECT event_id FROM usage_events WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return str(row[0])

    def close(self) -> None:
        self._db.close()
