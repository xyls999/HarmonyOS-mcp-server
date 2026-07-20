import unittest
from datetime import datetime, timezone

from backend.d6.automation.snapshot_builder import build_snapshot


class SnapshotBuilderRuntimeTelemetryTests(unittest.TestCase):
    def test_maps_live_mmwave_and_lux_telemetry_into_rule_inputs(self):
        now = datetime(2026, 7, 20, 0, 45, tzinfo=timezone.utc)
        snapshot = build_snapshot(
            {},
            {
                "radar_01": {
                    "online": True,
                    "radar_target_present": 0,
                    "radar_distance_cm": 0,
                    "observed_at": now,
                },
                "light_s_01": {"online": True, "value": 18, "observed_at": now},
            },
            {},
            now=now,
        )

        self.assertIs(snapshot["sensors"]["radar_01"]["present"], False)
        self.assertEqual(snapshot["light_sensor"]["value"], 18)
        self.assertEqual(snapshot["light_sensor"]["sensorId"], "light_s_01")

    def test_offline_mmwave_never_becomes_a_false_absence_signal(self):
        now = datetime(2026, 7, 20, 0, 45, tzinfo=timezone.utc)
        snapshot = build_snapshot(
            {},
            {"radar_01": {"online": False, "radar_target_present": 0, "observed_at": now}},
            {},
            now=now,
        )

        self.assertIsNone(snapshot["sensors"]["radar_01"].get("present"))


if __name__ == "__main__":
    unittest.main()
