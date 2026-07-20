import tempfile
import unittest
from pathlib import Path

from backend.d6.automation.rule_state_store import RuleStateStore
from backend.d6.automation.smart_adjustment_engine import SmartAdjustmentEngine


def snapshot(*, humidity=80, temperature=25, hour=14, radar=True, smoke=0, heat=0, bad_weather=False):
    sensors = {
        "humid_01": {"value": humidity},
        "temp_01": {"value": temperature},
        "smoke_01": {"value": smoke},
        "heat_01": {"value": heat},
        "radar_01": {"present": radar},
    }
    return {
        "capturedAt": "2026-07-19T14:00:00+00:00",
        "devices": {
            "ac_01": {"power": "off"},
            "alarm_01": {"power": "off"},
            "fan_02": {"power": "off"},
            "light_01": {"power": "on"},
        },
        "sensors": sensors,
        "weather": {"bad": bad_weather},
        "time": {"hour": hour},
    }


class SmartAdjustmentEngineTests(unittest.TestCase):
    def test_high_humidity_executes_dry_and_returns_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
            )
            result = engine.evaluate(snapshot(humidity=82), enabled_rule_ids=["A001"])
            self.assertEqual([item["device_id"] for item in calls], ["ac_01"])
            self.assertEqual(result["executed"][0]["ruleId"], "A001")
            self.assertEqual(result["executed"][0]["actions"][0]["result"]["success"], True)
            self.assertEqual(result["executed"][0]["status"], "executed")

    def test_manual_override_and_cooldown_block_repeat_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            clock = [1000.0]
            state = RuleStateStore(Path(directory) / "state.db", clock=lambda: clock[0])
            state.set_manual_override("ac_01", "off", 600)
            engine = SmartAdjustmentEngine(state, executor=lambda command: calls.append(command) or {"success": True}, clock=lambda: clock[0])
            blocked = engine.evaluate(snapshot(humidity=82), enabled_rule_ids=["A001"])
            self.assertEqual(blocked["executed"], [])
            self.assertEqual(blocked["skipped"][0]["reason"], "manual_override")
            state.set_manual_override("ac_01", "off", 0)
            clock[0] += 1
            first = engine.evaluate(snapshot(humidity=82), enabled_rule_ids=["A001"])
            self.assertEqual(len(first["executed"]), 1)
            second = engine.evaluate(snapshot(humidity=82), enabled_rule_ids=["A001"])
            self.assertEqual(second["executed"], [])
            self.assertEqual(second["skipped"][0]["reason"], "cooldown")

    def test_conflicting_actions_have_one_stable_winner_per_device(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
            )
            result = engine.evaluate(snapshot(humidity=82, temperature=32), enabled_rule_ids=["A001", "A002"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["device_id"], "ac_01")
            self.assertEqual(result["executed"][0]["ruleId"], "A002")

    def test_smoke_alarm_is_urgent_and_door_is_never_automatically_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
            )
            result = engine.evaluate(snapshot(smoke=1, heat=1), enabled_rule_ids=["A005", "A017"])
            self.assertTrue(result["executed"][0]["urgent"])
            self.assertTrue(all(command["device_id"] != "door_01" for command in calls))

    def test_idempotent_off_action_is_skipped_without_execution_or_popup_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            current = snapshot(hour=0)
            current["devices"]["light_01"] = {"is_on": False, "primary_value": 0}
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
            )
            result = engine.evaluate(current, enabled_rule_ids=["A008"])
            self.assertEqual(calls, [])
            self.assertEqual(result["executed"], [])
            self.assertEqual(result["skipped"][0]["reason"], "no_change")

    def test_heat_raw_millivolts_are_not_mistaken_for_an_alarm(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            current = snapshot(heat=1577)
            current["sensors"]["heat_01"]["is_alert"] = False
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
            )
            result = engine.evaluate(current, enabled_rule_ids=["A004"])
            self.assertEqual(calls, [])
            self.assertEqual(result["executed"], [])

    def test_absence_actions_require_three_consecutive_live_mmwave_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
                cooldown_seconds=0,
            )
            current = snapshot(radar=False)
            current["sensors"]["radar_01"].update({"online": True, "freshness": "fresh"})
            current["devices"]["ac_01"] = {"is_on": True, "online": True}

            first = engine.evaluate(current, enabled_rule_ids=["A012"])
            second = engine.evaluate(current, enabled_rule_ids=["A012"])
            third = engine.evaluate(current, enabled_rule_ids=["A012"])

            self.assertEqual(first["executed"], [])
            self.assertEqual(second["executed"], [])
            self.assertEqual(third["executed"][0]["ruleId"], "A012")
            self.assertEqual(len(calls), 1)

    def test_offline_mmwave_never_triggers_absence_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
                cooldown_seconds=0,
            )
            current = snapshot(radar=False)
            current["sensors"]["radar_01"].update({"online": False, "freshness": "fresh"})
            current["devices"]["ac_01"] = {"is_on": True, "online": True}

            for _ in range(5):
                result = engine.evaluate(current, enabled_rule_ids=["A012"])

            self.assertEqual(result["executed"], [])
            self.assertEqual(calls, [])

    def test_midnight_bedroom_rule_controls_bedroom_light_not_kitchen_light(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
            )
            current = snapshot(hour=0)
            current["devices"]["light_03"] = {"is_on": True, "online": True}
            current["devices"]["light_02"] = {"is_on": True, "online": True}

            result = engine.evaluate(current, enabled_rule_ids=["A009"])

            self.assertEqual(result["executed"][0]["ruleId"], "A009")
            self.assertEqual([item["device_id"] for item in calls], ["light_03"])

    def test_absence_rule_never_turns_off_exhaust_during_kitchen_alarm(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            engine = SmartAdjustmentEngine(
                RuleStateStore(Path(directory) / "state.db"),
                executor=lambda command: calls.append(command) or {"success": True},
                cooldown_seconds=0,
            )
            current = snapshot(radar=False, heat=21)
            current["sensors"]["radar_01"].update({"online": True, "freshness": "fresh"})
            current["sensors"]["heat_01"]["is_alert"] = True
            current["devices"]["fan_02"] = {"is_on": True, "online": True}

            for _ in range(4):
                result = engine.evaluate(current, enabled_rule_ids=["A013"])

            self.assertEqual(result["executed"], [])
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
