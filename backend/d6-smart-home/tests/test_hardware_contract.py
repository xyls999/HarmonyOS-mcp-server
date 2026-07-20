import ast
import importlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CONNECT = ROOT / "connect"
for entry in (str(ROOT), str(CONNECT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

controller = importlib.import_module("central_controller")
bridge = importlib.import_module("hardware_bridge")


class HardwareContractTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((CONNECT / "devices.json").read_text(encoding="utf-8"))

    def test_explicit_door_password_does_not_fall_back_to_environment(self):
        helper = getattr(controller, "verify_door_password_explicit", None)
        self.assertIsNotNone(helper, "explicit door-password helper is missing")
        with patch.dict(os.environ, {"A9_DOOR_PASSWORD": "must-not-be-used"}, clear=False):
            with self.assertRaisesRegex(ValueError, "password required for this request"):
                helper(self.config, None)

    def test_living_door_open_close_use_explicit_password_policy(self):
        source = (CONNECT / "central_controller.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "living_door"
        )
        body = ast.get_source_segment(source, function)
        self.assertIn("verify_door_password_explicit(config, password)", body)
        self.assertNotIn("verify_door_password(config, password)", body)

    def test_radar_presence_defaults_enabled_and_is_not_radar_light(self):
        helper = getattr(controller, "get_radar_feature_config", None)
        self.assertIsNotNone(helper, "radar feature helper is missing")
        feature = helper(self.config)
        self.assertTrue(feature["enabled"])
        self.assertEqual(feature["source_device"], "bathroom")
        self.assertEqual(feature["sensor"], "Rd-03 V2")
        self.assertNotIn("radar_light", feature)

    def test_radar_config_persists_explicit_presence_switch(self):
        presence = self.config.get("radar", {}).get("radar_presence")
        self.assertIsInstance(presence, dict, "radar_presence config is missing")
        self.assertIs(presence.get("enabled"), True)

    def test_radar_zone_gaps_remain_unmatched(self):
        self.assertIsNone(controller.radar_zone_for_distance(self.config, 38))
        self.assertIsNone(controller.radar_zone_for_distance(self.config, 57))
        self.assertEqual(
            controller.radar_zone_for_distance(self.config, 20)["name"],
            "kitchen",
        )
        settings = controller.radar_filter_settings(self.config)
        self.assertEqual(settings["sample_window"], 7)
        self.assertEqual(settings["stable_samples"], 5)

    def test_hardware_bridge_does_not_preconsume_rate_limit(self):
        with (
            patch.object(bridge, "_HW_AVAILABLE", True),
            patch.object(
                bridge,
                "_enforce_rate",
                side_effect=AssertionError("bridge must not preconsume rate limit"),
            ),
            patch.object(
                bridge,
                "kitchen_set_light",
                return_value={"brightness": 100},
            ),
        ):
            result = bridge.hw_toggle("light_02", True)
        self.assertTrue(result["success"], result)

    def test_bridge_door_api_rejects_missing_explicit_password(self):
        with (
            patch.object(bridge, "_HW_AVAILABLE", True),
            patch.object(bridge, "door_password_required", return_value=True),
            patch.object(
                bridge,
                "verify_door_password",
                side_effect=ValueError("legacy fallback used"),
            ),
        ):
            verified, error = bridge.verify_door_password_api(None)
        self.assertFalse(verified)
        self.assertIn("required for this request", error)

    def test_removed_atmosphere_light_is_not_a_hardware_alias(self):
        source = (ROOT / "hardware_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("light_05", source)
        self.assertNotIn("客厅氛围灯", source)

    def test_removed_atmosphere_light_is_not_an_intent_or_template(self):
        path = ROOT / "intent_engine.py"
        if not path.exists():
            path = ROOT / "device_source_full" / "intent_engine.py"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("light_05", source)
        self.assertNotIn("客厅氛围灯", source)
        self.assertNotIn("氛围灯", source)

    def test_ac_guard_actions_apply_named_ir_profiles(self):
        with (
            patch.object(bridge, "_HW_AVAILABLE", True),
            patch.object(bridge, "living_text", return_value={"ok": True}) as living,
        ):
            result = bridge.hw_control("ac_01", "cool", {"profile": "COOL_26_AUTO"})
        self.assertTrue(result["success"], result)
        living.assert_called_once_with(bridge._CONFIG, "ac", "preset", bridge._TIMEOUT, "COOL_26_AUTO")

    def test_reference_resolution_does_not_treat_zhe_shi_as_this_device(self):
        path = ROOT / "intent_engine.py"
        if not path.exists():
            path = ROOT / "device_source_full" / "intent_engine.py"
        spec = importlib.util.spec_from_file_location("intent_engine_contract", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        memory = module.ConversationMemory()
        memory.add("user", "打开客厅主灯", {
            "type": "device_toggle", "device_id": "light_01", "isOn": True,
        })
        self.assertIsNone(memory.resolve_reference("这是设备端AI链路健康检查"))
        resolved = memory.resolve_reference("把这个关掉")
        self.assertEqual(resolved["device_id"], "light_01")


if __name__ == "__main__":
    unittest.main()
