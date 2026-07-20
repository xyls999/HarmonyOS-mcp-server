import ast
import json
import tempfile
import unittest
from pathlib import Path

try:
    from gateway_context_runtime import build_turn_context, merge_context_summaries
except ImportError:
    build_turn_context = None
    merge_context_summaries = None


ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "gateway_v6.py"


class FakeContextEngine:
    def __init__(self):
        self.calls = []

    def build_prompt_context(self, query, *, is_first_turn, live_state=None):
        self.calls.append((query, is_first_turn, live_state))
        if is_first_turn and query == "你好":
            return ""
        return f"SUPER:{query}:{live_state['devices'][0]['id']}"


class GatewayContextContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GATEWAY.read_text(encoding="utf-8")
        ast.parse(cls.source)

    def test_gateway_declares_context_and_mcp_routes(self):
        for route in (
            "/api/ai/context/manifest",
            "/api/ai/context/stats",
            "/api/ai/context/search",
            "/api/ai/context/rebuild",
            "/api/ai/context/events",
            "/api/ai/radar/config",
        ):
            self.assertIn(route, self.source)
        self.assertIn('p == "/mcp"', self.source)
        self.assertIn("build_turn_context", self.source)
        self.assertNotIn('"/api/health"', self.source)

    def test_mcp_http_contract_has_size_origin_auth_and_get_405(self):
        self.assertIn("MAX_MCP_BODY_BYTES", self.source)
        self.assertIn("_validate_mcp_origin", self.source)
        self.assertIn("MCP-Protocol-Version", self.source)
        self.assertIn("Method Not Allowed", self.source)
        self.assertIn("_require_mcp_auth", self.source)

    def test_http_server_limits_threads_and_times_out_stalled_connections(self):
        self.assertIn("BoundedThreadingHTTPServer", self.source)
        self.assertIn("A9_HTTP_MAX_WORKERS", self.source)
        self.assertIn("A9_HTTP_CONNECTION_TIMEOUT", self.source)

    def test_context_events_and_radar_http_routes_share_safe_handlers(self):
        self.assertIn("self._get_recent_context_logs(limit, severity)", self.source)
        self.assertIn("self._j(200, self._get_radar_config())", self.source)
        self.assertIn('isinstance(body.get("enabled"), bool)', self.source)
        self.assertIn('self._set_radar_enabled(body["enabled"])', self.source)

    def test_substantive_turn_builds_and_merges_super_context(self):
        self.assertIsNotNone(build_turn_context)
        fake = FakeContextEngine()
        automatic = build_turn_context(
            fake,
            "毫米波状态",
            messages=[{"role": "user", "content": "毫米波状态"}],
            body={"isFirstTurn": True},
            live_state={"devices": [{"id": "radar_01"}]},
        )
        merged = merge_context_summaries("SHORT MEMORY", automatic)
        self.assertIn("SHORT MEMORY", merged)
        self.assertIn("SUPER:毫米波状态:radar_01", merged)
        self.assertEqual(fake.calls[0][1], True)

    def test_first_turn_pure_greeting_passes_no_large_context(self):
        fake = FakeContextEngine()
        automatic = build_turn_context(
            fake,
            "你好",
            messages=[{"role": "user", "content": "你好"}],
            body={"isFirstTurn": True},
            live_state={"devices": [{"id": "radar_01"}]},
        )
        self.assertEqual(automatic, "")
        self.assertEqual(merge_context_summaries("", automatic), "")

    def test_gateway_source_calls_chat_with_merged_context(self):
        self.assertIn("automatic_context = build_turn_context(", self.source)
        self.assertIn("merge_context_summaries(context_summary, automatic_context)", self.source)
        self.assertIn("redact_sensitive(msgs)", self.source)
        self.assertIn("chat(safe_msgs, context_summary=context_summary)", self.source)

    def test_gateway_routes_text_and_multimodal_ai_with_codex_fallback(self):
        self.assertIn("ProviderRouter", self.source)
        self.assertIn("extract_text_content", self.source)
        self.assertIn('"codex": {', self.source)
        self.assertIn('os.environ.get("CODEX_API_KEY", "")', self.source)
        self.assertIn('os.environ.get("CODEX_API_URL", "")', self.source)
        self.assertIn('"wireApi": "responses"', self.source)
        self.assertIn("_ai_router.complete", self.source)

    def test_gateway_exposes_adaptive_guard_feedback_and_telemetry_contract(self):
        self.assertIn("AdaptiveGuard", self.source)
        self.assertIn("NotificationService", self.source)
        for route in (
            "/api/ai/guard/status", "/api/ai/guard/config",
            "/api/ai/guard/incidents", "/api/ai/guard/feedback",
            "/api/ai/guard/learning", "/api/app/telemetry",
        ):
            self.assertIn(route, self.source)
        self.assertIn("_adaptive_guard.build_context(last_msg)", self.source)
        self.assertIn("_adaptive_guard.process_snapshot", self.source)

    def test_live_log_chart_route_is_exposed_for_frontend_data_management(self):
        self.assertIn('p == "/api/log/chart"', self.source)
        self.assertIn("self._get_log_chart(", self.source)

    def test_atmosphere_light_is_removed_from_backend_contract(self):
        tree = ast.parse(self.source)
        assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "DEVICE_DEFS" for target in node.targets)
        )
        device_defs = ast.literal_eval(assignment.value)
        self.assertNotIn("light_05", {item["id"] for item in device_defs})
        self.assertNotIn("客厅氛围灯", {item["name"] for item in device_defs})

    def test_guard_does_not_weaken_manual_door_password_policy(self):
        self.assertIn('if action in ("open", "close") and not password:', self.source)
        self.assertIn("record_door_event", self.source)

    def test_door_query_does_not_translate_to_close(self):
        self.assertIn('if action == "query":', self.source)
        self.assertIn('return hw_living_status("door")', self.source)

    def test_protocol_knowledge_is_json_serializable(self):
        tree = ast.parse(self.source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_build_protocol_knowledge"
        )
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(GATEWAY), "exec"), namespace)
        json.dumps(namespace["_build_protocol_knowledge"](), ensure_ascii=False)

    def test_sensor_api_merges_database_registered_sensors(self):
        self.assertIn("existing_sensor_ids", self.source)
        self.assertIn(
            'SELECT id,name,type,sensor_group,room,icon,current_value,unit,threshold_min,threshold_max,protocol,is_alert',
            self.source,
        )

    def test_custom_capability_executor_whitelist_matches_spec(self):
        for executor in (
            "device_toggle", "device_control", "scene_activate",
            "safe_internal_api", "read_only_query",
        ):
            self.assertIn(f'"{executor}"', self.source)
        self.assertNotIn('"internal_write"', self.source)

    def test_custom_capability_invocation_has_safe_dispatch_and_door_block(self):
        self.assertIn("def _invoke_capability", self.source)
        self.assertIn('target_device_id == "door_01"', self.source)
        self.assertIn("read_only_targets", self.source)
        self.assertIn("safe_internal_targets", self.source)


if __name__ == "__main__":
    unittest.main()
