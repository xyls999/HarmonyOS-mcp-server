import json
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

try:
    from adaptive_guard import AdaptiveGuard
except ImportError:
    AdaptiveGuard = None


class AdaptiveGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "guard.sqlite"
        self.actions = []
        self.spoken = []
        self.notices = []
        self.context_events = []
        self.fail_actions = set()

        def execute(action):
            self.actions.append(dict(action))
            return {"success": action.get("action") not in self.fail_actions}

        self.assertIsNotNone(AdaptiveGuard)
        self.guard = AdaptiveGuard(
            self.db_path,
            executor=execute,
            speaker=self.spoken.append,
            notifier=lambda kind, title, message, extra=None: self.notices.append(
                {"kind": kind, "title": title, "message": message, "extra": extra or {}}
            ),
            context_recorder=lambda *args, **kwargs: self.context_events.append((args, kwargs)),
            clock=lambda: 1_000_000.0,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def sensor(self, sensor_id, sensor_type, room, value, *, alert=False, online=True):
        return {
            "id": sensor_id, "type": sensor_type, "room": room,
            "value": value, "isAlert": alert, "online": online,
        }

    def test_migration_creates_incident_feedback_learning_and_telemetry_tables(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            names = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertTrue({
            "guard_incidents", "guard_feedback", "guard_learning",
            "app_telemetry_events", "adaptive_guard_config",
        }.issubset(names))

    def test_high_temperature_cools_then_falls_back_to_fan(self):
        self.fail_actions.add("cool")
        result = self.guard.process_snapshot({
            "sensors": [self.sensor("temp_01", "temperature", "客厅", 31.5)]
        })
        self.assertEqual([item["action"] for item in self.actions], ["cool", "fan"])
        self.assertEqual(result[0]["ruleKey"], "environment_high_temperature")
        self.assertTrue(result[0]["needsFeedback"])
        self.assertEqual(result[0]["guardLevel"], 7)

    def test_high_humidity_uses_dry_then_fan_fallback(self):
        self.fail_actions.add("dry")
        self.guard.process_snapshot({
            "sensors": [self.sensor("bed_humid", "humidity", "卧室", 82)]
        })
        self.assertEqual([item["action"] for item in self.actions], ["dry", "fan"])
        self.assertEqual(self.actions[0]["deviceId"], "ac_01")

    def test_kitchen_alarm_runs_buzzer_exhaust_tts_and_qq(self):
        incidents = self.guard.process_snapshot({
            "sensors": [
                self.sensor("smoke_01", "smoke", "厨房", 1, alert=True),
                self.sensor("heat_01", "heat", "厨房", 1, alert=True),
            ]
        })
        self.assertEqual(
            [(item["deviceId"], item["action"]) for item in self.actions],
            [("alarm_01", "on"), ("fan_02", "on")],
        )
        self.assertTrue(any("厨房" in text for text in self.spoken))
        self.assertEqual(self.notices[0]["kind"], "kitchen_alarm")
        self.assertEqual(incidents[0]["guardLevel"], 10)

    def test_door_open_and_close_are_recorded_and_broadcast_but_never_actuated(self):
        opened = self.guard.record_door_event(True, {"state": "open"})
        closed = self.guard.record_door_event(False, {"state": "closed"})
        self.assertEqual(self.actions, [])
        self.assertTrue(any("门已打开" in text for text in self.spoken))
        self.assertTrue(any("门已关闭" in text for text in self.spoken))
        self.assertEqual([notice["kind"] for notice in self.notices], ["door_open"])
        self.assertEqual(opened["ruleKey"], "door_event_monitor")
        self.assertEqual(closed["ruleKey"], "door_event_monitor")

    def test_disabled_guard_collects_passively_without_hardware_action(self):
        self.guard.update_config({"enabled": False})
        result = self.guard.process_snapshot({
            "sensors": [self.sensor("temp_01", "temperature", "客厅", 35)]
        })
        self.assertEqual(self.actions, [])
        self.assertEqual(result[0]["mode"], "passive")
        self.assertFalse(result[0]["needsFeedback"])

    def test_feedback_is_validated_upserted_and_injected_into_related_context(self):
        incident = self.guard.process_snapshot({
            "sensors": [self.sensor("temp_01", "temperature", "客厅", 33)]
        })[0]
        with self.assertRaises(ValueError):
            self.guard.submit_feedback(incident["id"], 11, "")
        first = self.guard.submit_feedback(incident["id"], 3, "先送风，持续升温后再制冷")
        second = self.guard.submit_feedback(incident["id"], 8, "优先制冷，但温度恢复后及时提醒")
        self.assertEqual(first["incidentId"], second["incidentId"])
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM guard_feedback WHERE incident_id=?", (incident["id"],)
            ).fetchone()[0]
        self.assertEqual(count, 1)
        context = self.guard.build_context("客厅温度太高怎么办")
        self.assertIn("8/10", context)
        self.assertIn("优先制冷", context)

    def test_same_active_signature_is_deduplicated_by_cooldown(self):
        snapshot = {"sensors": [self.sensor("temp_01", "temperature", "客厅", 31)]}
        first = self.guard.process_snapshot(snapshot)
        second = self.guard.process_snapshot(snapshot)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(self.actions), 1)

    def test_concurrent_snapshots_create_only_one_incident_and_action(self):
        original_recent = self.guard._recent_signature

        def synchronized_recent(signature):
            time.sleep(0.08)
            return original_recent(signature)

        self.guard._recent_signature = synchronized_recent
        snapshot = {"sensors": [self.sensor("temp_01", "temperature", "客厅", 31)]}
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.guard.process_snapshot(snapshot))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        self.assertEqual(len(self.actions), 1)
        self.assertEqual(sum(len(items) for items in results), 1)

    def test_app_telemetry_is_allowlisted_and_recursively_redacted(self):
        event_id = self.guard.record_app_telemetry({
            "eventType": "button_result",
            "page": "device",
            "action": "ac.cool",
            "result": "ok",
            "metadata": {"deviceId": "ac_01", "password": "NEVER_STORE", "token": "SECRET"},
        })
        self.assertGreater(event_id, 0)
        raw = self.db_path.read_bytes()
        self.assertNotIn(b"NEVER_STORE", raw)
        self.assertNotIn(b"SECRET", raw)

    def test_status_reports_pending_feedback_learning_and_guard_level(self):
        self.guard.process_snapshot({
            "sensors": [self.sensor("smoke_01", "smoke", "厨房", 1, alert=True)]
        })
        status = self.guard.get_status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["mode"], "active")
        self.assertEqual(status["guardLevel"], 10)
        self.assertEqual(status["pendingFeedback"], 1)
        self.assertIn("learning", status)


if __name__ == "__main__":
    unittest.main()
