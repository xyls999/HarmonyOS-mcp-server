import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "d6" / "security_anomaly_guard.py"


def load_module():
    if not SOURCE.exists():
        raise AssertionError("security_anomaly_guard.py must exist")
    spec = importlib.util.spec_from_file_location("security_anomaly_guard_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SecurityAnomalyGuardTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.now = 1_000.0
        self.guard = self.module.SecurityAnomalyGuard(clock=lambda: self.now)

    def test_authorized_state_change_is_not_an_incident(self):
        self.assertIsNone(self.guard.observe_state("light_01", False))
        self.guard.authorize_state("light_01", True, source="app")
        self.assertIsNone(self.guard.observe_state("light_01", True))

    def test_single_unknown_device_change_warns_without_buzzer(self):
        self.assertIsNone(self.guard.observe_state("light_01", False))
        event = self.guard.observe_state("light_01", True)
        self.assertEqual(event["ruleId"], "device.uncommanded_state_change")
        self.assertEqual(event["severity"], "High")
        self.assertFalse(event["critical"])
        self.assertFalse(event["activateBuzzer"])
        self.assertEqual(event["evidence"]["before"], False)
        self.assertEqual(event["evidence"]["after"], True)

    def test_unknown_door_open_is_critical_and_activates_buzzer(self):
        self.assertIsNone(self.guard.observe_state("door_01", False))
        event = self.guard.observe_state("door_01", True)
        self.assertEqual(event["ruleId"], "door.uncommanded_open")
        self.assertEqual(event["severity"], "Critical")
        self.assertTrue(event["critical"])
        self.assertTrue(event["activateBuzzer"])

    def test_three_unknown_changes_in_two_minutes_escalate_to_intrusion(self):
        self.assertIsNone(self.guard.observe_state("ac_01", False))
        first = self.guard.observe_state("ac_01", True)
        self.now += 20
        second = self.guard.observe_state("ac_01", False)
        self.now += 20
        third = self.guard.observe_state("ac_01", True)
        self.assertEqual(first["severity"], "High")
        self.assertEqual(second["severity"], "High")
        self.assertEqual(third["ruleId"], "device.repeated_uncommanded_changes")
        self.assertEqual(third["severity"], "Critical")
        self.assertTrue(third["activateBuzzer"])

    def test_door_password_enumeration_warns_at_three_and_alarms_at_five(self):
        events = []
        for index in range(5):
            self.now += 20
            event = self.guard.record_door_password_failure("192.168.1.77")
            if event:
                events.append(event)
        self.assertEqual([event["severity"] for event in events], ["High", "Critical"])
        self.assertEqual(events[0]["evidence"]["attempts"], 3)
        self.assertFalse(events[0]["activateBuzzer"])
        self.assertEqual(events[1]["evidence"]["attempts"], 5)
        self.assertTrue(events[1]["activateBuzzer"])

    def test_five_auth_failures_in_one_minute_are_critical(self):
        event = None
        for _ in range(5):
            self.now += 10
            event = self.guard.record_auth_failure("203.0.113.8", endpoint="/api/devices") or event
        self.assertIsNotNone(event)
        self.assertEqual(event["ruleId"], "auth.repeated_failure")
        self.assertEqual(event["severity"], "Critical")
        self.assertTrue(event["activateBuzzer"])

    def test_critical_password_report_uses_independent_qq_key_and_concrete_results(self):
        self.assertTrue(hasattr(self.module, "format_security_response"))
        response = self.module.format_security_response({
            "ruleId": "door.password_enumeration",
            "severity": "Critical",
            "message": "五分钟内连续五次门禁密码错误，按密码枚举攻击处理",
            "activateBuzzer": True,
            "evidence": {"attempts": 5, "clientId": "127.0.0.1"},
        }, buzzer_success=True, qq_queued=True)
        self.assertEqual(response["notificationEvent"], "security_critical_door_password_enumeration")
        text = "；".join(item["action"] + item["result"] for item in response["operations"])
        self.assertIn("阻止开门", text)
        self.assertIn("蜂鸣器", text)
        self.assertIn("QQ", text)


if __name__ == "__main__":
    unittest.main()
