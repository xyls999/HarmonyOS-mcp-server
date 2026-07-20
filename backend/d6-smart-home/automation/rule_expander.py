"""Promote unlockable/AI-generated rules only after durable evidence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .rule_schema import load_catalog, validate_rule


class RuleExpander:
    def __init__(self, db_path: str | Path, *, catalog_path: str | Path | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        path = Path(catalog_path) if catalog_path else Path(__file__).with_name("rule_catalog.json")
        self.catalog = load_catalog(path)
        self.rules = {str(rule["id"]): rule for rule in self.catalog}
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _migrate(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS automation_rule_unlock (
                    rule_id TEXT PRIMARY KEY,
                    samples INTEGER NOT NULL DEFAULT 0,
                    success_rate REAL NOT NULL DEFAULT 0,
                    average_score REAL NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    rule_json TEXT NOT NULL,
                    updated_at REAL NOT NULL DEFAULT (unixepoch())
                )"""
            )

    def observe(self, rule_id: str, *, samples: int, success_rate: float, average_score: float) -> bool:
        rule = self.rules.get(str(rule_id))
        if not rule or rule.get("tier") != "unlockable":
            return False
        eligible = int(samples) >= 3 and float(success_rate) >= 0.9 and float(average_score) >= 8.0
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO automation_rule_unlock(rule_id,samples,success_rate,average_score,enabled,rule_json,updated_at) VALUES(?,?,?,?,?,?,unixepoch()) "
                "ON CONFLICT(rule_id) DO UPDATE SET samples=excluded.samples,success_rate=excluded.success_rate,average_score=excluded.average_score,enabled=excluded.enabled,updated_at=excluded.updated_at",
                (str(rule_id), int(samples), float(success_rate), float(average_score), int(eligible), json.dumps(rule, ensure_ascii=False)),
            )
        return eligible

    def register_generated(self, rule: dict[str, Any]) -> bool:
        if not isinstance(rule, dict) or not str(rule.get("id", "")).startswith("AI_"):
            return False
        try:
            errors = validate_rule(rule, {"light_01", "light_02", "light_03", "light_04", "ac_01", "fan_02", "curtain_01", "alarm_01", "door_01"},
                                   {"temp_01", "humid_01", "smoke_01", "heat_01", "radar_01", "air_01"})
        except (TypeError, ValueError):
            return False
        if errors:
            return False
        self.rules[str(rule["id"])] = dict(rule)
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO automation_rule_unlock(rule_id,samples,success_rate,average_score,enabled,rule_json,updated_at) VALUES(?,?,?,?,?,?,unixepoch())",
                (str(rule["id"]), 0, 0.0, 0.0, 0, json.dumps(rule, ensure_ascii=False)),
            )
        return True

    def is_enabled(self, rule_id: str) -> bool:
        rule = self.rules.get(str(rule_id))
        if rule and rule.get("enabledByDefault"):
            return True
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT enabled FROM automation_rule_unlock WHERE rule_id=?", (str(rule_id),)).fetchone()
        return bool(row and row["enabled"])

    def enabled_rule_ids(self) -> list[str]:
        return [rule_id for rule_id in self.rules if self.is_enabled(rule_id)]
