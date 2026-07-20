import sys
import types
import unittest

from backend.d6 import hardware_bridge_compat


class HardwareBridgeCompatTests(unittest.TestCase):
    def test_living_light_auto_calls_field_light_auto_command(self):
        calls = []
        fake = types.SimpleNamespace(
            _CONFIG={"field": "d6"},
            _TIMEOUT=3.0,
            living_text=lambda config, service, action, timeout: calls.append((service, action)) or {"reply": "OK,type=LIGHT,mode=AUTO"},
        )
        previous = sys.modules.get("hardware_bridge")
        sys.modules["hardware_bridge"] = fake
        try:
            result = hardware_bridge_compat.set_living_light_auto(True)
        finally:
            if previous is None:
                sys.modules.pop("hardware_bridge", None)
            else:
                sys.modules["hardware_bridge"] = previous
        self.assertTrue(result["success"])
        self.assertEqual(calls, [("light", "auto")])

    def test_disabling_does_not_send_an_unrelated_light_toggle(self):
        result = hardware_bridge_compat.set_living_light_auto(False)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"].get("mode"), "manual")


if __name__ == "__main__":
    unittest.main()
