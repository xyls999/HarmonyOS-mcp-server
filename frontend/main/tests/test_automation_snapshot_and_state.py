import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.d6.automation.rule_state_store import RuleStateStore
from backend.d6.automation.snapshot_builder import build_snapshot


class AutomationSnapshotTests(unittest.TestCase):
    def test_build_snapshot_uses_one_capture_time_and_preserves_fresh_values(self):
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        snapshot = build_snapshot(
            device_status={"light_01": {"power": "on", "observed_at": now.isoformat()}},
            sensor_status={"humid_01": {"value": 82, "observed_at": now.isoformat()}},
            weather={"condition": "晴"},
            now=now,
        )
        self.assertEqual(snapshot["capturedAt"], now.isoformat())
        self.assertEqual(snapshot["devices"]["light_01"]["power"], "on")
        self.assertEqual(snapshot["sensors"]["humid_01"]["value"], 82)
        self.assertEqual(snapshot["freshness"]["humid_01"], "fresh")

    def test_stale_values_are_marked_and_never_replaced_with_zero(self):
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        old = "2026-07-19T11:00:00+00:00"
        snapshot = build_snapshot(
            device_status={},
            sensor_status={"humid_01": {"value": 82, "observed_at": old}},
            weather={},
            now=now,
            sensor_ttl_seconds=300,
        )
        self.assertEqual(snapshot["freshness"]["humid_01"], "stale")
        self.assertNotIn("humid_01", snapshot["sensors"])


class RuleStateStoreTests(unittest.TestCase):
    def test_state_persists_streak_cooldown_and_manual_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.db"
            now = [1000.0]
            store = RuleStateStore(path, clock=lambda: now[0])
            self.assertEqual(store.record_sample("A001", True)["streak"], 1)
            self.assertEqual(store.record_sample("A001", True)["streak"], 2)
            store.start_cooldown("A001", 300)
            store.set_manual_override("ac_01", "off", 600)
            self.assertTrue(store.cooldown_active("A001"))
            self.assertTrue(store.is_protected("ac_01"))

            now[0] += 301
            reopened = RuleStateStore(path, clock=lambda: now[0])
            self.assertFalse(reopened.cooldown_active("A001"))
            self.assertTrue(reopened.is_protected("ac_01"))
            now[0] += 300
            self.assertFalse(reopened.is_protected("ac_01"))


if __name__ == "__main__":
    unittest.main()
