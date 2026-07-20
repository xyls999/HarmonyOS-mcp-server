import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "d6" / "adaptive_guard.py"
SPEC = importlib.util.spec_from_file_location("adaptive_guard_under_test", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeClock:
    def __init__(self, value: float = 1000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def kitchen_snapshot(alert: bool) -> dict:
    return {
        "sensors": [
            {
                "id": "smoke_01",
                "type": "smoke",
                "room": "厨房",
                "value": int(alert),
                "isAlert": alert,
                "online": True,
            },
            {
                "id": "heat_01",
                "type": "heat",
                "room": "厨房",
                "value": 1630,
                "isAlert": False,
                "online": True,
            },
        ]
    }


def absence_snapshot() -> dict:
    return {
        "sensors": [{"id": "radar_01", "type": "presence", "room": "客厅",
                     "value": 0, "isAlert": False, "presence": False, "online": True}],
        "devices": [{"id": "ac_01", "type": "ac", "room": "客厅", "isOn": True, "online": True}],
    }


class AdaptiveGuardStateMachineTests(unittest.TestCase):
    def test_default_guard_suppresses_offline_noise_and_uses_ten_minute_cooldown(self):
        self.assertEqual(MODULE.DEFAULT_CONFIG["cooldownSeconds"], 600)
        self.assertFalse(MODULE.DEFAULT_CONFIG["offlineMonitor"]["enabled"])

    def make_guard(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        clock = FakeClock()
        actions = []
        speech = []
        notices = []
        context = []
        guard = MODULE.AdaptiveGuard(
            pathlib.Path(directory.name) / "home.db",
            executor=lambda action: actions.append(action)
            or {"success": True, "state_changed": True},
            speaker=speech.append,
            notifier=lambda *args, **kwargs: notices.append((args, kwargs)),
            context_recorder=lambda *args, **kwargs: context.append((args, kwargs)),
            clock=clock,
        )
        guard._started_at = clock() - 30
        return guard, clock, actions, speech, notices, context

    def test_disabled_guard_is_completely_silent_for_alarm_and_recovery(self):
        guard, clock, actions, speech, notices, context = self.make_guard()
        guard.update_config({"enabled": False})
        speech.clear()

        for alert in (True, True, True, False, False, False, False, False):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(kitchen_snapshot(alert)), [])

        self.assertEqual(actions, [])
        self.assertEqual(speech, [])
        self.assertEqual(notices, [])
        self.assertEqual(context, [])
        self.assertEqual(guard.list_incidents(limit=10), [])

    def test_disabled_kitchen_rule_is_silent_while_guard_remains_enabled(self):
        guard, clock, actions, speech, notices, context = self.make_guard()
        guard.update_config({"kitchenAlarm": {"enabled": False}})

        for _ in range(4):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(kitchen_snapshot(True)), [])

        self.assertEqual(actions, [])
        self.assertEqual(speech, [])
        self.assertEqual(notices, [])
        self.assertEqual(context, [])
        self.assertEqual(guard.list_incidents(limit=10), [])

    def test_alarm_requires_three_samples_and_recovery_requires_five(self):
        guard, clock, actions, speech, _, _ = self.make_guard()

        for _ in range(2):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(kitchen_snapshot(True)), [])

        clock.advance(1)
        self.assertEqual(len(guard.process_snapshot(kitchen_snapshot(True))), 1)
        self.assertEqual(len(actions), 2)
        self.assertEqual(len(speech), 1)

        for _ in range(4):
            clock.advance(1)
            guard.process_snapshot(kitchen_snapshot(False))

        self.assertEqual(len(actions), 2)
        self.assertEqual(len(speech), 1)

        clock.advance(1)
        guard.process_snapshot(kitchen_snapshot(False))
        self.assertEqual(len(actions), 4)
        self.assertEqual(len(speech), 2)
        runtime = guard.get_status(include_incidents=False)["runtime"]
        self.assertIn("kitchenAlarmStreak", runtime)
        self.assertIn("kitchenClearStreak", runtime)
        self.assertIn("kitchenConfirmed", runtime)
        self.assertIn("activeSignatures", runtime)

    def test_plan_confirmation_persists_across_restart(self):
        guard, _, _, _, _, _ = self.make_guard()
        guard.update_config({"planConfirmation": {"enabled": False}})

        restored = MODULE.AdaptiveGuard(guard.db_path)

        self.assertFalse(restored.get_config()["planConfirmation"]["enabled"])

    def test_absence_monitor_requires_trusted_presence_sensor_and_turns_off_ac(self):
        guard, clock, actions, speech, _, _ = self.make_guard()
        guard.update_config({"absenceMonitor": {"enabled": True, "minSamples": 3}})
        for _ in range(2):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(absence_snapshot()), [])
        clock.advance(1)
        incidents = guard.process_snapshot(absence_snapshot())
        self.assertEqual(len(incidents), 1)
        self.assertEqual(actions[-1]["deviceId"], "ac_01")
        self.assertEqual(actions[-1]["action"], "off")
        self.assertIn("无人", speech[-1])

    def test_kitchen_alarm_prevents_absence_monitor_from_turning_off_exhaust(self):
        guard, clock, actions, _, _, _ = self.make_guard()
        guard.update_config({"absenceMonitor": {"enabled": True, "minSamples": 3}})
        snapshot = kitchen_snapshot(True)
        snapshot["sensors"].append({
            "id": "radar_01", "type": "mmwave", "room": "卫生间",
            "value": 0, "presence": False, "online": True,
        })
        snapshot["devices"] = [
            {"id": "fan_02", "name": "换气扇", "type": "fan", "room": "卫生间",
             "isOn": True, "online": True},
        ]
        for _ in range(3):
            clock.advance(1)
            guard.process_snapshot(snapshot)

        fan_actions = [item["action"] for item in actions if item["deviceId"] == "fan_02"]
        self.assertIn("on", fan_actions)
        self.assertNotIn("off", fan_actions)

    def test_restart_reasserts_missing_kitchen_safety_actuators_for_open_alarm(self):
        guard, clock, _, _, _, _ = self.make_guard()
        for _ in range(3):
            clock.advance(1)
            guard.process_snapshot(kitchen_snapshot(True))

        actions = []
        restored = MODULE.AdaptiveGuard(
            guard.db_path,
            executor=lambda action: actions.append(action) or {"success": True, "state_changed": True},
            clock=clock,
        )
        restored._started_at = clock() - 30
        active = kitchen_snapshot(True)
        active["devices"] = [
            {"id": "alarm_01", "name": "蜂鸣警报", "isOn": False, "online": True},
            {"id": "fan_02", "name": "换气扇", "isOn": False, "online": True},
        ]
        for _ in range(3):
            clock.advance(1)
            restored.process_snapshot(active)

        self.assertEqual(
            {(item["deviceId"], item["action"]) for item in actions},
            {("alarm_01", "on"), ("fan_02", "on")},
        )

    def test_unresolved_alarm_is_not_recreated_after_cooldown_or_restart(self):
        guard, clock, _, speech, notices, _ = self.make_guard()
        for _ in range(3):
            clock.advance(1)
            guard.process_snapshot(kitchen_snapshot(True))
        first = guard.list_incidents(limit=10)
        self.assertEqual(len(first), 1)

        # The physical alarm never recovered.  A process restart after the old
        # five-minute suppression window must not turn it into a new incident.
        clock.advance(601)
        restored_speech = []
        restored_notices = []
        restored = MODULE.AdaptiveGuard(
            guard.db_path,
            executor=lambda _action: {"success": True, "state_changed": False},
            speaker=restored_speech.append,
            notifier=lambda *args, **kwargs: restored_notices.append((args, kwargs)),
            clock=clock,
        )
        restored._started_at = clock() - 30
        for _ in range(3):
            clock.advance(1)
            self.assertEqual(restored.process_snapshot(kitchen_snapshot(True)), [])

        incidents = restored.list_incidents(limit=10)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["id"], first[0]["id"])
        self.assertEqual(incidents[0]["status"], "open")
        self.assertEqual(restored_speech, [])
        self.assertEqual(restored_notices, [])

    def test_migration_supersedes_historical_duplicate_open_incidents(self):
        guard, clock, _, _, _, _ = self.make_guard()
        for _ in range(3):
            clock.advance(1)
            guard.process_snapshot(kitchen_snapshot(True))
        connection = guard._connect()
        try:
            connection.execute(
                "INSERT INTO guard_incidents(signature,rule_key,room,guard_level,mode,evidence_json,"
                "planned_actions_json,executed_actions_json,status,needs_feedback,created_at,created_ts) "
                "SELECT signature,rule_key,room,guard_level,mode,evidence_json,planned_actions_json,"
                "executed_actions_json,'open',needs_feedback,created_at,created_ts+600 "
                "FROM guard_incidents WHERE signature='kitchen:alarm' LIMIT 1"
            )
        finally:
            connection.close()

        restored = MODULE.AdaptiveGuard(guard.db_path, clock=clock)
        incidents = restored.list_incidents(limit=10)
        self.assertEqual(len([item for item in incidents if item["status"] == "open"]), 1)
        self.assertEqual(len([item for item in incidents if item["status"] == "superseded"]), 1)
        duplicate = next(item for item in incidents if item["status"] == "superseded")
        self.assertFalse(duplicate["needsFeedback"])

    def test_stale_in_memory_signature_cannot_hide_a_real_alarm_without_an_open_row(self):
        guard, clock, _, _, _, _ = self.make_guard()
        guard._active_signatures.add("kitchen:alarm")
        for _ in range(2):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(kitchen_snapshot(True)), [])
        clock.advance(1)
        incidents = guard.process_snapshot(kitchen_snapshot(True))
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["signature"], "kitchen:alarm")
        self.assertEqual(len([item for item in guard.list_incidents(limit=10) if item["status"] == "open"]), 1)


if __name__ == "__main__":
    unittest.main()
