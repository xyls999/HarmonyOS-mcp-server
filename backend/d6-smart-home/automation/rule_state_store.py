"""Durable automation streak, cooldown and manual-override state."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


class RuleStateStore:
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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_rule_state (
                    rule_id TEXT PRIMARY KEY,
                    streak INTEGER NOT NULL DEFAULT 0,
                    last_match INTEGER NOT NULL DEFAULT 0,
                    cooldown_until REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automation_manual_override (
                    device_id TEXT PRIMARY KEY,
                    desired_state TEXT NOT NULL,
                    protected_until REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def record_sample(self, rule_id: str, matched: bool) -> dict[str, Any]:
        now = float(self.clock())
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT streak FROM automation_rule_state WHERE rule_id=?", (rule_id,)).fetchone()
            streak = int(row["streak"]) + 1 if matched and row else (1 if matched else 0)
            if not matched:
                streak = 0
            connection.execute(
                "INSERT INTO automation_rule_state(rule_id,streak,last_match,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(rule_id) DO UPDATE SET streak=excluded.streak,last_match=excluded.last_match,updated_at=excluded.updated_at",
                (rule_id, streak, int(bool(matched)), now),
            )
        return {"ruleId": rule_id, "streak": streak, "matched": bool(matched)}

    def start_cooldown(self, rule_id: str, seconds: float) -> None:
        now = float(self.clock())
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO automation_rule_state(rule_id,cooldown_until,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(rule_id) DO UPDATE SET cooldown_until=excluded.cooldown_until,updated_at=excluded.updated_at",
                (rule_id, now + max(0.0, float(seconds)), now),
            )

    def cooldown_active(self, rule_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT cooldown_until FROM automation_rule_state WHERE rule_id=?", (rule_id,)).fetchone()
        return bool(row and float(row["cooldown_until"]) > float(self.clock()))

    def set_manual_override(self, device_id: str, desired_state: str, seconds: float) -> None:
        now = float(self.clock())
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO automation_manual_override(device_id,desired_state,protected_until,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET desired_state=excluded.desired_state,protected_until=excluded.protected_until,updated_at=excluded.updated_at",
                (device_id, desired_state, now + max(0.0, float(seconds)), now),
            )

    def is_protected(self, device_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT protected_until FROM automation_manual_override WHERE device_id=?", (device_id,)).fetchone()
        return bool(row and float(row["protected_until"]) > float(self.clock()))
