"""Deterministic, bounded evaluator for the smart-adjustment rule catalog."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from .rule_state_store import RuleStateStore
    from .rule_schema import load_catalog
except ImportError:  # pragma: no cover
    from rule_state_store import RuleStateStore
    from rule_schema import load_catalog

try:
    from parallel_device_executor import execute_device_commands
except ModuleNotFoundError:  # pragma: no cover
    from backend.d6.parallel_device_executor import execute_device_commands


_PRIORITY = {"A003": 100, "A004": 100, "A005": 100, "A018": 95, "A019": 95, "A020": 95, "A002": 80, "A001": 75}


class SmartAdjustmentEngine:
    def __init__(
        self,
        state_store: RuleStateStore,
        *,
        executor: Callable[[dict[str, Any]], Any] | None = None,
        catalog_path: str | Path | None = None,
        clock: Callable[[], float] = time.time,
        cooldown_seconds: float = 300.0,
    ):
        self.state_store = state_store
        self.executor = executor or (lambda _command: {"success": False, "error": "executor unavailable"})
        self.clock = clock
        self.cooldown_seconds = cooldown_seconds
        path = Path(catalog_path) if catalog_path else Path(__file__).with_name("rule_catalog.json")
        self.catalog = load_catalog(path)
        self._by_id = {str(rule["id"]): rule for rule in self.catalog}

    @staticmethod
    def _value(snapshot: dict[str, Any], sensor: str, field: str = "value") -> Any:
        item = snapshot.get("sensors", {}).get(sensor, {})
        return item.get(field) if isinstance(item, dict) else None

    @staticmethod
    def _hour(snapshot: dict[str, Any]) -> int | None:
        value = snapshot.get("time", {}).get("hour")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        captured = snapshot.get("capturedAt")
        if isinstance(captured, str):
            try:
                return datetime.fromisoformat(captured.replace("Z", "+00:00")).hour
            except ValueError:
                return None
        return None

    @staticmethod
    def _alert(snapshot: dict[str, Any], sensor: str) -> bool:
        item = snapshot.get("sensors", {}).get(sensor, {})
        if not isinstance(item, dict):
            return False
        for key in ("is_alert", "isAlert", "alarm"):
            if key in item:
                return bool(item[key])
        value = item.get("value")
        return value is True or value == 1 or (isinstance(value, str) and value.lower() in {"alarm", "alert", "报警"})

    def _matches(self, rule_id: str, snapshot: dict[str, Any]) -> bool:
        humidity = self._value(snapshot, "humid_01")
        temperature = self._value(snapshot, "temp_01")
        smoke = self._alert(snapshot, "smoke_01")
        heat = self._alert(snapshot, "heat_01")
        radar = snapshot.get("sensors", {}).get("radar_01", {})
        radar_live = bool(
            isinstance(radar, dict)
            and radar.get("online") is True
            and radar.get("freshness", "fresh") != "stale"
        )
        present = radar.get("present") if radar_live else None
        hour = self._hour(snapshot)
        weather_bad = bool(snapshot.get("weather", {}).get("bad"))
        if rule_id == "A001": return isinstance(humidity, (int, float)) and humidity >= 75
        if rule_id == "A002": return isinstance(temperature, (int, float)) and temperature >= 30
        if rule_id == "A003": return smoke
        if rule_id == "A004": return heat
        if rule_id == "A005": return smoke and heat
        if rule_id == "A006": return hour is not None and (hour >= 22 or hour < 6) and "curtain_01" in snapshot.get("devices", {})
        if rule_id == "A007": return weather_bad
        if rule_id in {"A008", "A009"}: return hour == 0
        if rule_id == "A010": return present is False
        if rule_id == "A011": return snapshot.get("light_sensor", {}).get("value", 100) < 25 and present is True
        if rule_id == "A012": return present is False
        if rule_id == "A013": return present is False and not smoke and not heat
        if rule_id in {"A015", "A016"}: return not smoke and not heat
        if rule_id in {"A018", "A019", "A020"}: return bool(snapshot.get("security", {}).get("risk"))
        return False

    def _enabled(self, enabled_rule_ids: Iterable[str] | None) -> list[str]:
        if enabled_rule_ids is None:
            return [str(rule["id"]) for rule in self.catalog if rule.get("enabledByDefault")]
        return [str(rule_id) for rule_id in enabled_rule_ids if str(rule_id) in self._by_id]

    def _rule_evidence(self, rule_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        time_state = snapshot.get("time", {}) if isinstance(snapshot.get("time"), dict) else {}
        weather = snapshot.get("weather", {}) if isinstance(snapshot.get("weather"), dict) else {}
        security = snapshot.get("security", {}) if isinstance(snapshot.get("security"), dict) else {}
        light_state = snapshot.get("light_sensor", {}) if isinstance(snapshot.get("light_sensor"), dict) else {}
        return {
            "humidity": self._value(snapshot, "humid_01"),
            "temperature": self._value(snapshot, "temp_01"),
            "smokeAlarm": self._alert(snapshot, "smoke_01"),
            "heatAlarm": self._alert(snapshot, "heat_01"),
            "heatRaw": self._value(snapshot, "heat_01"),
            "presence": self._value(snapshot, "radar_01", "present"),
            "illuminance": light_state.get("value"),
            "hour": time_state.get("hour", self._hour(snapshot)),
            "minute": time_state.get("minute"),
            "weather": weather.get("condition", weather.get("summary", "")),
            "weatherRisk": weather.get("risk", weather.get("bad", False)),
            "securityRisk": security.get("risk", False),
            "securityReason": security.get("reason", ""),
            "ruleId": rule_id,
        }

    @staticmethod
    def _is_noop(action: dict[str, Any], snapshot: dict[str, Any]) -> bool:
        device_id = str(action.get("deviceId", ""))
        command = str(action.get("action", ""))
        state = snapshot.get("devices", {}).get(device_id)
        if not isinstance(state, dict) or not state.get("online", True):
            return False
        if command in {"on", "off"}:
            current = state.get("is_on", state.get("power"))
            if isinstance(current, str):
                current = current.lower() in {"on", "open", "true", "1"}
            return isinstance(current, bool) and current == (command == "on")
        if command == "set_position":
            desired = (action.get("params") or {}).get("value")
            current = state.get("primary_value", state.get("position"))
            return isinstance(current, (int, float)) and isinstance(desired, (int, float)) and abs(float(current) - float(desired)) < 1
        if command == "auto":
            return state.get("auto_mode") is True
        return False

    def evaluate(self, snapshot: dict[str, Any], *, enabled_rule_ids: Iterable[str] | None = None) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be an object")
        matched: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for rule_id in self._enabled(enabled_rule_ids):
            rule = self._by_id[rule_id]
            did_match = self._matches(rule_id, snapshot)
            sample = self.state_store.record_sample(rule_id, did_match)
            if not did_match:
                continue
            # Absence is safety-sensitive and noisy around radar boundaries.
            # Three consecutive live samples are required before any shutdown.
            if rule_id in {"A010", "A012", "A013"} and int(sample.get("streak", 0)) < 3:
                skipped.append({"ruleId": rule_id, "reason": "awaiting_confirmation", "streak": sample.get("streak", 0)})
                continue
            actions = [dict(action) for action in rule.get("actions", []) if isinstance(action, dict)]
            if not actions:
                continue
            if self.state_store.cooldown_active(rule_id):
                skipped.append({"ruleId": rule_id, "reason": "cooldown"})
                continue
            filtered: list[dict[str, Any]] = []
            for action in actions:
                device_id = str(action.get("deviceId", ""))
                action_name = str(action.get("action", ""))
                if device_id == "door_01" and action_name not in {"query", "record"}:
                    skipped.append({"ruleId": rule_id, "reason": "door_automation_forbidden"})
                    continue
                if self.state_store.is_protected(device_id):
                    skipped.append({"ruleId": rule_id, "deviceId": device_id, "reason": "manual_override"})
                    continue
                if self._is_noop(action, snapshot):
                    skipped.append({"ruleId": rule_id, "deviceId": device_id, "reason": "no_change"})
                    continue
                filtered.append({"device_id": device_id, "action": action_name, "params": dict(action.get("params", {})), "rule_id": rule_id})
            if filtered:
                matched.append({"rule": rule, "actions": filtered, "urgent": rule_id in {"A003", "A004", "A005", "A018", "A019", "A020"}})

        winners: list[dict[str, Any]] = []
        claimed: set[str] = set()
        for item in sorted(matched, key=lambda value: (-_PRIORITY.get(str(value["rule"]["id"]), 50), str(value["rule"]["id"]))):
            actions = [action for action in item["actions"] if action["device_id"] not in claimed]
            if not actions:
                skipped.append({"ruleId": item["rule"]["id"], "reason": "conflict"})
                continue
            claimed.update(action["device_id"] for action in actions)
            item["actions"] = actions
            winners.append(item)

        executed: list[dict[str, Any]] = []
        for item in winners:
            batch = execute_device_commands(item["actions"], self.executor, max_workers=4)
            rule_id = str(item["rule"]["id"])
            self.state_store.start_cooldown(rule_id, self.cooldown_seconds)
            executed.append({
                "ruleId": rule_id,
                "title": item["rule"].get("title", rule_id),
                "urgent": bool(item["urgent"]),
                "status": "executed" if batch.get("success") else "partial_failure",
                "actions": batch.get("results", []),
                "evidence": self._rule_evidence(rule_id, snapshot),
                "capturedAt": snapshot.get("capturedAt"),
            })
        return {"capturedAt": snapshot.get("capturedAt"), "executed": executed, "skipped": skipped}
