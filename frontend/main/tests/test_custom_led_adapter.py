import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys


BACKEND = Path(__file__).resolve().parents[1] / "backend" / "d6"
sys.path.insert(0, str(BACKEND))
from custom_led_adapter import CustomLedAdapter  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    state = {"esp_ip": "127.0.0.1", "led_enabled": False, "led_color": "red"}
    status_available = True

    def log_message(self, *_args):
        return

    def _send(self, value):
        raw = json.dumps(value).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/state":
            self._send(self.state)
        elif self.path == "/api/status":
            if not self.status_available:
                self.send_error(503)
                return
            self._send({"ok": True, "ip": "127.0.0.1", "led_enabled": self.state["led_enabled"],
                        "led_color": self.state["led_color"]})
        elif self.path.startswith("/api/led"):
            from urllib.parse import parse_qs, urlsplit
            query = parse_qs(urlsplit(self.path).query)
            if "led" in query:
                self.state["led_enabled"] = query["led"][0] == "1"
            if "color" in query:
                self.state["led_color"] = query["color"][0]
            self._send({"ok": True, **self.state})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/config":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        self.state.update(json.loads(self.rfile.read(size).decode("utf-8")))
        self._send({"ok": True, **self.state})


class CustomLedAdapterTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        _Handler.state = {"esp_ip": "127.0.0.1", "led_port": self.server.server_port,
                          "led_enabled": False, "led_color": "red"}
        _Handler.status_available = True
        self.tmp = tempfile.TemporaryDirectory()
        self.adapter = CustomLedAdapter(Path(self.tmp.name) / "devices.json",
                                        f"http://127.0.0.1:{self.server.server_port}")

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.tmp.cleanup()

    def test_discover_and_control_real_http(self):
        result = self.adapter.discover("玄关灯带", "玄关")
        self.assertTrue(result["success"])
        self.assertEqual(result["discovery"]["scanned_hosts"], 1)
        device = result["device"]
        self.assertEqual(device["transport"], "http")
        self.assertTrue(self.adapter.register_pending(device["id"])["success"])
        changed = self.adapter.control(device["id"], "on", {"color": "blue"})
        self.assertTrue(changed["success"])
        self.assertTrue(changed["device"]["isOn"])
        self.assertEqual(changed["device"]["mode"], "blue")

    def test_rejects_public_discovery_url_and_bad_color(self):
        with self.assertRaises(ValueError):
            CustomLedAdapter(Path(self.tmp.name) / "bad.json", "http://8.8.8.8:8080")
        result = self.adapter.discover()
        device_id = result["device"]["id"]
        bad = self.adapter.control(device_id, "set_color", {"color": "purple"})
        self.assertFalse(bad["success"])

    def test_rejects_unadvertised_scan_type_instead_of_faking_capabilities(self):
        with self.assertRaises(RuntimeError):
            self.adapter.discover(device_type="fan")

    def test_scan_waits_for_explicit_registration(self):
        result = self.adapter.discover(device_type="light", persist=False)
        device_id = result["device"]["id"]
        self.assertEqual(self.adapter.list_devices(), [])
        self.assertTrue(self.adapter.register_pending(device_id)["success"])
        self.assertEqual(len(self.adapter.list_devices()), 1)

    def test_offline_device_is_not_reported_or_registered(self):
        _Handler.status_available = False

        with self.assertRaisesRegex(RuntimeError, "设备未联网或状态接口不可达"):
            self.adapter.discover(device_type="light", persist=False)

        self.assertEqual(self.adapter.list_devices(), [])

    def test_legacy_simulator_records_are_not_executable(self):
        descriptor = {
            "id": "legacy", "name": "旧记录", "type": "custom", "room": "测试",
            "transport": "simulator-http", "endpoint": "http://127.0.0.1",
            "isOn": False, "mode": "red",
        }
        self.adapter._registry["legacy"] = descriptor

        status = self.adapter.status("legacy")
        result = self.adapter.control("legacy", "on", {"color": "blue"})

        self.assertFalse(status["success"])
        self.assertFalse(result["success"])
        self.assertIn("真实设备", status["error"])


if __name__ == "__main__":
    unittest.main()
