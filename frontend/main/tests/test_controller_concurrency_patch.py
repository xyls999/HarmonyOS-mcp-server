import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from backend.d6.controller_concurrency_patch import install_controller_concurrency


class ControllerConcurrencyPatchTests(unittest.TestCase):
    def test_parallel_rate_limit_updates_do_not_collide_or_lose_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / ".central_controller_state.json"
            controller = self._fake_controller(state_path)
            self.assertTrue(install_controller_concurrency(controller))

            action_keys = [f"device.{index}" for index in range(32)]
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda key: controller.enforce_rate_limit({}, key), action_keys))

            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(set(saved["last_control_ms"]), set(action_keys))
            self.assertEqual(list(state_path.parent.glob("*.tmp.*")), [])

    @staticmethod
    def _fake_controller(state_path: Path):
        controller = SimpleNamespace()
        controller.state_file_path = lambda _config: state_path

        def load_state(_config):
            if not state_path.exists():
                return {}
            return json.loads(state_path.read_text(encoding="utf-8"))

        def unsafe_save(_config, state):
            temporary = state_path.with_suffix(state_path.suffix + ".tmp")
            temporary.write_text(json.dumps(state), encoding="utf-8")
            time.sleep(0.001)
            temporary.replace(state_path)

        def enforce_rate_limit(config, action_key):
            state = controller.load_state(config)
            state.setdefault("last_control_ms", {})[action_key] = int(time.time() * 1000)
            time.sleep(0.001)
            controller.save_state(config, state)

        controller.load_state = load_state
        controller.save_state = unsafe_save
        controller.enforce_rate_limit = enforce_rate_limit
        return controller


if __name__ == "__main__":
    unittest.main()
