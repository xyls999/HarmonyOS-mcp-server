import tempfile
import unittest
from pathlib import Path

from backend.d6.automation.rule_expander import RuleExpander


class RuleExpanderTests(unittest.TestCase):
    def test_unlock_requires_repeated_success_and_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            expander = RuleExpander(Path(directory) / "automation.db")
            self.assertFalse(expander.is_enabled("B021"))
            self.assertFalse(expander.observe("B021", samples=2, success_rate=1.0, average_score=10.0))
            self.assertTrue(expander.observe("B021", samples=3, success_rate=0.95, average_score=8.0))
            self.assertTrue(expander.is_enabled("B021"))

    def test_generated_rule_is_validated_and_door_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            expander = RuleExpander(Path(directory) / "automation.db")
            valid = {
                "id": "AI_CUSTOM_01", "tier": "unlockable", "enabledByDefault": False,
                "inputs": ["sensor:humid_01"],
                "actions": [{"deviceId": "ac_01", "action": "dry", "params": {}}],
            }
            self.assertTrue(expander.register_generated(valid))
            invalid = {**valid, "id": "AI_CUSTOM_02", "actions": [{"deviceId": "door_01", "action": "open"}]}
            self.assertFalse(expander.register_generated(invalid))


if __name__ == "__main__":
    unittest.main()
