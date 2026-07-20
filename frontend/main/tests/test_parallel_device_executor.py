import importlib.util
import pathlib
import tempfile
import threading
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "backend" / "d6" / "parallel_device_executor.py"
SCENES = ROOT / "backend" / "d6" / "scenes" / "scene_config.py"


class ParallelDeviceExecutorTests(unittest.TestCase):
    def load(self, path: pathlib.Path, name: str):
        self.assertTrue(path.exists(), f"missing production module: {path}")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_commands_execute_concurrently_keep_order_and_isolate_failure(self):
        module = self.load(EXECUTOR, "parallel_device_executor_under_test")
        lock = threading.Lock()
        active = 0
        max_active = 0

        def execute(command):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04)
            with lock:
                active -= 1
            if command["device_id"] == "light_02":
                raise RuntimeError("simulated device failure")
            return {"success": True, "device": command["device_id"]}

        commands = [
            {"type": "device", "device_id": "light_01", "action": "on", "params": {}},
            {"type": "device", "device_id": "light_02", "action": "off", "params": {}},
            {"type": "device", "device_id": "fan_02", "action": "off", "params": {}},
        ]
        result = module.execute_device_commands(commands, execute, max_workers=3)
        self.assertGreaterEqual(max_active, 2)
        self.assertEqual([item["deviceId"] for item in result["results"]],
                         ["light_01", "light_02", "fan_02"])
        self.assertEqual(result["successCount"], 2)
        self.assertEqual(result["failureCount"], 1)
        self.assertFalse(result["success"])

    def test_prepared_scenes_only_reference_real_controllable_devices(self):
        module = self.load(SCENES, "scene_config_under_test")
        allowed = {"light_01", "light_02", "light_03", "light_04", "ac_01", "fan_02", "curtain_01", "door_01"}
        forbidden = {"light_05", "fan_01", "exhaust_01", "nfc_01"}
        self.assertGreaterEqual(len(module.SCENE_COMMANDS), 6)
        for commands in module.SCENE_COMMANDS.values():
            self.assertTrue(commands)
            for command in commands:
                self.assertIn(command["device_id"], allowed)
                self.assertNotIn(command["device_id"], forbidden)
        for phrase in ("我回来了", "我要出门", "晚安睡觉", "准备看电影", "开始吃饭", "早安起床"):
            self.assertIsNotNone(module.match_prepared_scene(phrase), phrase)

    def test_adaptive_guard_executes_multiple_safety_actions_concurrently(self):
        from backend.d6.adaptive_guard import AdaptiveGuard

        lock = threading.Lock()
        active = 0
        max_active = 0

        def execute(action):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04)
            with lock:
                active -= 1
            return {"success": True, "deviceId": action["deviceId"]}

        with tempfile.TemporaryDirectory() as directory:
            guard = AdaptiveGuard(pathlib.Path(directory) / "guard.db", executor=execute)
            result = guard._execute_plan([
                {"deviceId": "alarm_01", "action": "on", "params": {}},
                {"deviceId": "fan_02", "action": "on", "params": {}},
            ])

        self.assertEqual(len(result), 2)
        self.assertGreaterEqual(max_active, 2)
        self.assertTrue(all(item["result"]["success"] for item in result))
