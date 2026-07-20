from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALLOWED_TIERS = {"core", "unlockable"}
ALLOWED_DOOR_ACTIONS = {"query", "record"}


def load_catalog(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError("automation catalog must be an array")
    validate_catalog(value)
    return value


def validate_rule(rule: dict[str, Any], devices: set[str], sensors: set[str]) -> list[str]:
    errors: list[str] = []
    rule_id = str(rule.get("id", ""))
    if not rule_id:
        errors.append("rule id is required")
    if rule.get("tier") not in ALLOWED_TIERS:
        errors.append(f"{rule_id}: invalid tier")
    if not isinstance(rule.get("actions", []), list):
        errors.append(f"{rule_id}: actions must be a list")
    for action in rule.get("actions", []):
        if not isinstance(action, dict):
            errors.append(f"{rule_id}: action must be an object")
            continue
        device_id = str(action.get("deviceId", ""))
        action_name = str(action.get("action", ""))
        if device_id and device_id not in devices:
            errors.append(f"{rule_id}: unknown device {device_id}")
        if device_id == "door_01" and action_name not in ALLOWED_DOOR_ACTIONS:
            errors.append(f"{rule_id}: automatic door action is forbidden")
    for input_name in rule.get("inputs", []):
        token = str(input_name).split(":", 1)[-1]
        if str(input_name).startswith("sensor:") and token not in sensors:
            errors.append(f"{rule_id}: unknown sensor {token}")
    return errors


def validate_catalog(rules: list[dict[str, Any]], devices: set[str] | None = None,
                     sensors: set[str] | None = None) -> None:
    devices = devices or {"light_01", "light_02", "light_03", "light_04", "ac_01", "fan_02", "curtain_01", "alarm_01", "door_01"}
    sensors = sensors or {"temp_01", "humid_01", "smoke_01", "heat_01", "air_01", "radar_01"}
    ids: set[str] = set()
    errors: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            errors.append("rule must be an object")
            continue
        rule_id = str(rule.get("id", ""))
        if rule_id in ids:
            errors.append(f"duplicate rule id {rule_id}")
        ids.add(rule_id)
        errors.extend(validate_rule(rule, devices, sensors))
    if len(rules) != 100:
        errors.append(f"catalog must contain 100 rules, got {len(rules)}")
    if sum(rule.get("tier") == "core" for rule in rules if isinstance(rule, dict)) != 20:
        errors.append("catalog must contain 20 core rules")
    if sum(rule.get("tier") == "unlockable" for rule in rules if isinstance(rule, dict)) != 80:
        errors.append("catalog must contain 80 unlockable rules")
    if errors:
        raise ValueError("; ".join(errors))
