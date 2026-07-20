"""Durable popup queue for routine automation and urgent alarms."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


class PopupOutbox:
    def __init__(self, path: str | Path, *, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _migrate(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS automation_popup_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    popup_kind TEXT NOT NULL,
                    rule_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    urgent INTEGER NOT NULL DEFAULT 0,
                    requires_ack INTEGER NOT NULL DEFAULT 0,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    acknowledged_at REAL,
                    feedback_score INTEGER,
                    feedback_choice TEXT NOT NULL DEFAULT '',
                    feedback_note TEXT NOT NULL DEFAULT '',
                    feedback_at REAL,
                    source_incident_id INTEGER
                )"""
            )
            for statement in (
                "ALTER TABLE automation_popup_outbox ADD COLUMN feedback_score INTEGER",
                "ALTER TABLE automation_popup_outbox ADD COLUMN feedback_choice TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE automation_popup_outbox ADD COLUMN feedback_note TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE automation_popup_outbox ADD COLUMN feedback_at REAL",
                "ALTER TABLE automation_popup_outbox ADD COLUMN source_incident_id INTEGER",
            ):
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError:
                    pass
            connection.execute("CREATE INDEX IF NOT EXISTS idx_automation_popup_pending ON automation_popup_outbox(acknowledged,urgent,created_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_automation_popup_source_incident ON automation_popup_outbox(source_incident_id)")
            # Backfill installations that already persisted detailed receipts
            # before source_incident_id became a first-class dedupe key.
            rows = connection.execute(
                "SELECT id,payload_json FROM automation_popup_outbox WHERE source_incident_id IS NULL"
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                    source_id = payload.get("sourceIncidentId") if isinstance(payload, dict) else None
                    if source_id is not None:
                        connection.execute(
                            "UPDATE automation_popup_outbox SET source_incident_id=? WHERE id=?",
                            (int(source_id), int(row["id"])),
                        )
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue

    def has_source_incident(self, incident_id: int) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id FROM automation_popup_outbox WHERE source_incident_id=? LIMIT 1",
                (int(incident_id),),
            ).fetchone()
        return row is not None

    def discard_source_incidents(self, incident_ids: list[int]) -> int:
        values = sorted({int(item) for item in incident_ids if item is not None})
        if not values:
            return 0
        placeholders = ",".join("?" for _ in values)
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                f"UPDATE automation_popup_outbox SET acknowledged=1,acknowledged_at=? "
                f"WHERE acknowledged=0 AND source_incident_id IN ({placeholders})",
                (float(self.clock()), *values),
            )
        return int(cursor.rowcount)

    def enqueue(self, popup_kind: str, payload: dict[str, Any], *, urgent: bool = False, requires_ack: bool | None = None) -> int | None:
        if not isinstance(payload, dict) or not payload.get("actions"):
            return None
        rule_id = str(payload.get("ruleId", ""))
        ack = bool(urgent) if requires_ack is None else bool(requires_ack)
        source_incident_id = payload.get("sourceIncidentId")
        try:
            source_incident_id = int(source_incident_id) if source_incident_id is not None else None
        except (TypeError, ValueError):
            source_incident_id = None
        now = float(self.clock())
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        with closing(self._connect()) as connection:
            if source_incident_id is not None:
                existing_source = connection.execute(
                    "SELECT id FROM automation_popup_outbox WHERE source_incident_id=? LIMIT 1",
                    (source_incident_id,),
                ).fetchone()
                if existing_source:
                    return None
            if rule_id:
                if urgent:
                    # Alarms require acknowledgement, not a score.  Once the
                    # owner has acknowledged one occurrence a later real alarm
                    # must never be suppressed by the historical row.
                    existing = connection.execute(
                        "SELECT id FROM automation_popup_outbox WHERE rule_id=? AND urgent=1 AND acknowledged=0",
                        (rule_id,),
                    ).fetchone()
                else:
                    existing = connection.execute(
                        "SELECT id FROM automation_popup_outbox WHERE rule_id=? AND urgent=0 "
                        "AND (acknowledged=0 OR feedback_score IS NULL)",
                        (rule_id,),
                    ).fetchone()
                if existing:
                    return None
            cursor = connection.execute(
                "INSERT INTO automation_popup_outbox(popup_kind,rule_id,payload_json,urgent,requires_ack,created_at,source_incident_id) VALUES(?,?,?,?,?,?,?)",
                (str(popup_kind), rule_id, serialized, int(urgent), int(ack), now, source_incident_id),
            )
            return int(cursor.lastrowid)

    def pending(self, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM automation_popup_outbox WHERE acknowledged=0 OR (requires_ack=1 AND urgent=0 AND feedback_score IS NULL) ORDER BY urgent DESC,created_at ASC,id ASC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        result = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                payload = {}
            result.append({
                "id": int(row["id"]),
                "kind": row["popup_kind"],
                "ruleId": row["rule_id"],
                "payload": payload,
                "urgent": bool(row["urgent"]),
                "requiresAcknowledgement": bool(row["requires_ack"]),
                "acknowledged": bool(row["acknowledged"]),
                "feedback": ({"score": int(row["feedback_score"]), "choice": row["feedback_choice"], "note": row["feedback_note"]}
                             if row["feedback_score"] is not None else None),
                "createdAt": float(row["created_at"]),
            })
        return result

    def acknowledge(self, popup_id: int) -> bool:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE automation_popup_outbox SET acknowledged=1,acknowledged_at=? WHERE id=? AND acknowledged=0",
                (float(self.clock()), int(popup_id)),
            )
        return cursor.rowcount > 0

    def submit_feedback(self, popup_id: int, score: int, choice: str = "", note: str = "") -> dict[str, Any]:
        value = int(score)
        if value < 0 or value > 10:
            raise ValueError("评分必须在0到10之间")
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE automation_popup_outbox SET feedback_score=?,feedback_choice=?,feedback_note=?,feedback_at=? WHERE id=?",
                (value, str(choice)[:40], str(note)[:500], float(self.clock()), int(popup_id)),
            )
        if cursor.rowcount <= 0:
            raise ValueError("弹窗事件不存在")
        return {"popupId": int(popup_id), "score": value, "choice": str(choice)[:40], "note": str(note)[:500]}
