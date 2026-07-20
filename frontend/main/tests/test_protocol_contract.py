import unittest
from pathlib import Path
import sys


BACKEND = Path(__file__).resolve().parents[1] / "backend" / "d6"
sys.path.insert(0, str(BACKEND))

from protocol_contract import (  # noqa: E402
    AdapterRegistry, Capability, PROTOCOL_PROFILES,
    secure_transport_requirements, validate_private_endpoint,
)


class _DemoAdapter:
    adapter_id = "demo_mqtt_switch"
    protocol = "mqtt"

    def capabilities(self):
        return [Capability("query", "查询"), Capability("toggle", "开关", {"isOn": "bool"})]

    def query(self, device_id):
        return {"success": True, "device_id": device_id, "isOn": False}

    def invoke(self, device_id, action, params):
        return {"success": True, "device_id": device_id, "action": action, "params": params}


class ProtocolContractTests(unittest.TestCase):
    def test_catalog_covers_five_mainstream_protocols(self):
        self.assertTrue({"http", "https", "websocket", "mqtt", "coap"}.issubset(PROTOCOL_PROFILES))
        for name in ("https", "websocket", "mqtt", "coap"):
            self.assertTrue(PROTOCOL_PROFILES[name]["encrypted"])

    def test_new_adapter_registers_without_changing_business_router(self):
        registry = AdapterRegistry()
        registry.register(_DemoAdapter())
        catalog = registry.catalog()
        self.assertEqual(catalog["adapters"][0]["id"], "demo_mqtt_switch")
        result = registry.invoke("demo_mqtt_switch", "switch_01", "toggle", {"isOn": True})
        self.assertTrue(result["success"])

    def test_capability_allowlist_blocks_unknown_action(self):
        registry = AdapterRegistry()
        registry.register(_DemoAdapter())
        result = registry.invoke("demo_mqtt_switch", "switch_01", "format_disk", {})
        self.assertFalse(result["success"])

    def test_remote_plain_http_is_forbidden(self):
        self.assertFalse(secure_transport_requirements("http", remote=True)["allowed"])
        self.assertTrue(secure_transport_requirements("https", remote=True)["allowed"])

    def test_endpoint_validation_rejects_public_or_embedded_credentials(self):
        self.assertEqual(validate_private_endpoint("http://192.168.1.54:80"), "http://192.168.1.54:80")
        with self.assertRaises(ValueError):
            validate_private_endpoint("http://8.8.8.8/device")
        with self.assertRaises(ValueError):
            validate_private_endpoint("http://user:password@192.168.1.54/device")


if __name__ == "__main__":
    unittest.main()
