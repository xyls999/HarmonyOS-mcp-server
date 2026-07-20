#!/usr/bin/env python3
"""Run deterministic trigger matching on the D6 runtime without moving hardware."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from automation.automation_service import AutomationService
from security_anomaly_guard import SecurityAnomalyGuard


def run_rule(name: str, rule_id: str, snapshot: dict, repeats: int = 1) -> dict:
    calls: list[dict] = []
    with tempfile.TemporaryDirectory(dir="/data/A9") as directory:
        service = AutomationService(
            Path(directory) / "matrix.db",
            executor=lambda command: calls.append(command) or {"success": True, "demo": True},
        )
        result = None
        for _ in range(repeats):
            result = service.evaluate(snapshot, enabled_rule_ids=[rule_id])
        assert result is not None
        executed = result.get("executed", [])
        if not executed:
            raise AssertionError(f"{name}: rule did not execute; result={result}")
        receipt = executed[0]
        return {
            "scenario": name,
            "ruleId": receipt["ruleId"],
            "triggerReason": receipt["triggerReason"],
            "devices": receipt["deviceSummary"],
            "action": receipt["actionSummary"],
            "result": receipt["resultSummary"],
            "calls": calls,
        }


def main() -> None:
    base = {
        "capturedAt": "2026-07-20T00:45:00+08:00",
        "time": {"hour": 0, "minute": 45},
        "weather": {},
        "sensors": {},
        "devices": {},
    }
    scenarios = []
    scenarios.append(run_rule("湿度超过75%", "A001", {
        **base, "sensors": {"humid_01": {"value": 79}},
        "devices": {"ac_01": {"is_on": False, "online": True}},
    }))
    scenarios.append(run_rule("温度超过30℃", "A002", {
        **base, "sensors": {"temp_01": {"value": 31}},
        "devices": {"ac_01": {"is_on": False, "online": True}},
    }))
    scenarios.append(run_rule("夜间窗帘保护", "A006", {
        **base, "devices": {"curtain_01": {"is_on": True, "primary_value": 80, "online": True}},
    }))
    scenarios.append(run_rule("凌晨客厅灯关闭", "A008", {
        **base, "devices": {"light_01": {"is_on": True, "online": True}},
    }))
    scenarios.append(run_rule("凌晨卧室灯关闭", "A009", {
        **base, "devices": {"light_03": {"is_on": True, "online": True}},
    }))
    radar_absent = {"present": False, "online": True, "freshness": "fresh"}
    scenarios.append(run_rule("毫米波连续无人关闭空调", "A012", {
        **base, "sensors": {"radar_01": radar_absent},
        "devices": {"ac_01": {"is_on": True, "online": True}},
    }, repeats=3))
    scenarios.append(run_rule("低照度有人启用光敏", "A011", {
        **base,
        "sensors": {"radar_01": {"present": True, "online": True, "freshness": "fresh"}},
        "light_sensor": {"value": 18, "sensorId": "light_s_01"},
        "devices": {"light_01": {"is_on": True, "online": True, "auto_mode": False}},
    }))

    now = [1000.0]
    security = SecurityAnomalyGuard(clock=lambda: now[0])
    security_events = []
    for _ in range(5):
        now[0] += 10
        event = security.record_door_password_failure("d6-smoke-test")
        if event:
            security_events.append(event)
    if [item["evidence"]["attempts"] for item in security_events] != [3, 5]:
        raise AssertionError(f"door password thresholds failed: {security_events}")
    if not security_events[-1].get("activateBuzzer"):
        raise AssertionError("fifth password failure did not request buzzer")

    print(json.dumps({
        "success": True,
        "scenarioCount": len(scenarios) + 1,
        "automation": scenarios,
        "doorPasswordSecurity": {
            "events": [{
                "attempts": item["evidence"]["attempts"],
                "severity": item["severity"],
                "activateBuzzer": item["activateBuzzer"],
                "message": item["message"],
            } for item in security_events],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
