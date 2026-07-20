import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

try:
    from context_engine import ContextEngine
    from super_mcp import SuperMCP
except ImportError:
    ContextEngine = None
    SuperMCP = None


class SuperMCPContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.assertIsNotNone(ContextEngine)
        self.assertIsNotNone(SuperMCP, "super_mcp module is missing")
        self.engine = ContextEngine(root / "db.sqlite", root, root / "project_context.json")
        self.engine.upsert_entity(
            "device", "radar_01", name="毫米波雷达", aliases=["radar"],
            capabilities={"enabled": True}, state={"online": True},
        )
        self.calls = []

        def handler(**arguments):
            self.calls.append(arguments)
            return {"ok": True, "arguments": arguments}

        self.mcp = SuperMCP(
            self.engine,
            tool_handlers={
                "list_devices": lambda **_: [{"id": "radar_01"}],
                "door_control": handler,
                "toggle_device": handler,
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, method, params=None, request_id=1, auth=None):
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        return self.mcp.dispatch(message, auth=auth)

    def call(self, name, arguments=None, auth=None):
        return self.request(
            "tools/call", {"name": name, "arguments": arguments or {}}, auth=auth
        )

    def test_initialize_declares_tools_and_resources(self):
        result = self.request(
            "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}
        )
        self.assertEqual(result["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("tools", result["result"]["capabilities"])
        self.assertIn("resources", result["result"]["capabilities"])

    def test_notification_has_no_response_and_ping_works(self):
        notification = {
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
        }
        self.assertIsNone(self.mcp.dispatch(notification))
        self.assertEqual(self.request("ping")["result"], {})

    def test_tools_list_contains_context_dynamic_and_door_tools(self):
        result = self.request("tools/list")
        tools = {item["name"]: item for item in result["result"]["tools"]}
        for name in ("search_context", "list_devices", "register_device", "invoke_capability", "door_control"):
            self.assertIn(name, tools)
        self.assertTrue(tools["search_context"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["door_control"]["annotations"]["destructiveHint"])
        self.assertIn("人工", tools["door_control"]["description"])
        for name in ("get_guard_status", "get_pending_guard_feedback", "submit_guard_feedback", "set_guard_config"):
            self.assertIn(name, tools)
        self.assertTrue(tools["get_guard_status"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["submit_guard_feedback"]["annotations"]["readOnlyHint"])

    def test_guard_feedback_score_is_limited_to_zero_through_ten(self):
        result = self.call("submit_guard_feedback", {
            "incident_id": 1, "score": 11, "better_action": "test"
        })
        self.assertEqual(result["error"]["code"], -32602)

    def test_tools_call_returns_structured_content(self):
        result = self.call("search_context", {"query": "radar"})
        self.assertFalse(result["result"]["isError"])
        self.assertIn("structuredContent", result["result"])
        self.assertIn("radar_01", json.dumps(result, ensure_ascii=False))

    def test_resources_list_read_and_template_list(self):
        resources = self.request("resources/list")["result"]["resources"]
        self.assertIn("a9://devices", {item["uri"] for item in resources})
        read = self.request("resources/read", {"uri": "a9://devices"})
        content = read["result"]["contents"][0]
        self.assertEqual(content["mimeType"], "application/json")
        self.assertIn("radar_01", content["text"])
        templates = self.request("resources/templates/list")
        self.assertEqual(
            templates["result"]["resourceTemplates"][0]["uriTemplate"],
            "a9://context/search/{query}",
        )

    def test_unknown_method_uses_json_rpc_error(self):
        result = self.request("unknown", request_id=3)
        self.assertEqual(result["error"]["code"], -32601)

    def test_invalid_tool_arguments_use_invalid_params(self):
        result = self.call("search_context", {})
        self.assertEqual(result["error"]["code"], -32602)

    def test_handler_failure_is_tool_error_not_protocol_error(self):
        mcp = SuperMCP(
            self.engine,
            tool_handlers={"list_devices": lambda **_: (_ for _ in ()).throw(RuntimeError("offline"))},
        )
        result = mcp.dispatch(
            {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "list_devices", "arguments": {}}}
        )
        self.assertTrue(result["result"]["isError"])
        self.assertNotIn("traceback", json.dumps(result).lower())

    def test_business_failure_payload_sets_tool_is_error(self):
        mcp = SuperMCP(
            self.engine,
            tool_handlers={
                "list_devices": lambda **_: {
                    "success": False, "error": "backend unavailable"
                }
            },
        )
        result = mcp.dispatch(
            {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "list_devices", "arguments": {}}}
        )
        self.assertTrue(result["result"]["isError"])

    def test_door_open_requires_password_and_never_audits_value(self):
        denied = self.call("door_control", {"action": "open"})
        self.assertTrue(denied["result"]["isError"])
        self.assertEqual(self.calls, [])
        allowed = self.call(
            "door_control", {"action": "open", "password": "one-call-secret"}
        )
        self.assertFalse(allowed["result"]["isError"])
        with closing(self.engine._connect()) as conn:
            persisted = "\n".join(
                str(value)
                for row in conn.execute("SELECT summary,details_json FROM ai_context_events")
                for value in row
            )
        self.assertNotIn("one-call-secret", persisted)
        self.assertIn("passwordProvided", persisted)

    def test_write_tool_requires_write_scope_for_http_auth(self):
        denied = self.call(
            "toggle_device", {"device_id": "radar_01", "is_on": True},
            auth={"scopes": ["read"]},
        )
        self.assertTrue(denied["result"]["isError"])
        allowed = self.call(
            "toggle_device", {"device_id": "radar_01", "is_on": True},
            auth={"scopes": ["write"]},
        )
        self.assertFalse(allowed["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
