import ast
import pathlib
import re
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "backend" / "d6" / "gateway_v6.py"


def load_gateway_functions(*names: str) -> dict:
    tree = ast.parse(GATEWAY.read_text(encoding="utf-8"))
    selected = []
    dependencies = {
        "_NEGATED_EXECUTION",
        "_EXPLICIT_DEVICE",
        "_EXPLICIT_ACTION",
        "REMOVED_LEGACY_DEVICE_IDS",
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if targets & dependencies:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(GATEWAY), "exec"), namespace)
    return namespace


class GatewaySafetyContractTests(unittest.TestCase):
    def test_d6_startup_brings_up_field_network_before_gateway(self):
        start_script = ROOT / "backend" / "d6" / "run_v6.sh"
        self.assertTrue(start_script.exists())
        source = start_script.read_text(encoding="utf-8")
        self.assertLess(source.index("ifconfig wlan0 up"), source.index("nohup"))
        self.assertIn("gateway_v6.pid", source)

    def test_log_fast_path_does_not_capture_unrelated_deep_analysis(self):
        functions = load_gateway_functions("_is_log_analysis_request", "_requires_deep_analysis")
        is_log = functions["_is_log_analysis_request"]
        is_deep = functions["_requires_deep_analysis"]
        self.assertTrue(is_log("分析七日趋势和当日趋势日志"))
        self.assertTrue(is_log("汇总今日日志统计"))
        self.assertFalse(is_log("分析今日系统最值得改善的智能化能力"))
        self.assertTrue(is_deep("结合历史记录和设备状态综合分析系统改进建议"))

    def test_only_real_alarm_feed_items_require_acknowledgement(self):
        functions = load_gateway_functions("_assistant_item_requires_acknowledgement")
        self.assertIn("_assistant_item_requires_acknowledgement", functions)
        check = functions["_assistant_item_requires_acknowledgement"]
        self.assertTrue(check({"kind": "security_alert", "severity": "warning"}))
        self.assertTrue(check({"kind": "guard_incident", "severity": "danger"}))
        self.assertFalse(check({"kind": "summary", "severity": "warning"}))
        self.assertFalse(check({"kind": "repeated_toggle", "severity": "warning"}))
        self.assertFalse(check({"kind": "device_operation", "severity": "warning"}))
        self.assertFalse(check({"kind": "security_alert", "severity": "info"}))

    def test_only_explicit_affirmative_device_commands_execute_directly(self):
        check = load_gateway_functions("is_explicit_execution_request")["is_explicit_execution_request"]

        self.assertTrue(check("打开客厅主灯"))
        self.assertTrue(check("把客厅空调调到26度"))
        self.assertFalse(check("不要打开空调"))
        self.assertFalse(check("先别执行"))
        self.assertFalse(check("我觉得有点暗"))
        self.assertFalse(check("马上让家里舒服一点"))

    def test_removed_mock_devices_are_filtered_but_real_fan_remains(self):
        visible = load_gateway_functions("_visible_devices")["_visible_devices"]
        devices = [
            {"id": "fan_01", "name": "客厅吊扇"},
            {"id": "exhaust_01", "name": "抽风机"},
            {"id": "fan_02", "name": "换气扇"},
            {"id": "custom_new", "name": "新自定义设备", "custom": True},
        ]

        result = visible(devices)

        self.assertEqual([item["id"] for item in result], ["fan_02", "custom_new"])

    def test_pending_plans_are_scoped_expiring_and_immutable(self):
        source = GATEWAY.read_text(encoding="utf-8")

        self.assertIn("sessionId", source)
        self.assertIn("expiresAt", source)
        self.assertIn("planNonce", source)
        self.assertIn("visible_commands", source)
        self.assertNotIn('_PENDING_INTENT_PLANS["u001"]', source)
        self.assertNotIn('get("u001")', source)

    def test_ai_call_commands_never_hide_inside_device_plans(self):
        source = GATEWAY.read_text(encoding="utf-8")

        self.assertIn("_safe_plan_commands", source)
        self.assertIn('command.get("type") in {"device", "scene"}', source)
        self.assertNotIn("results = [self._execute_ai_command(command) for command", source)

    def test_chat_no_longer_builds_or_cancels_pending_plans(self):
        source = GATEWAY.read_text(encoding="utf-8")
        chat = source.split("def _chat(self, body):", 1)[1].split("def _execute_intent", 1)[0]
        self.assertNotIn("is_plan_cancellation", chat)
        self.assertNotIn("_clear_pending_plan(plan_scope)", chat)
        self.assertNotIn("pending_entry = _put_pending_plan", chat)
        self.assertIn("_execute_commands_concurrently", chat)

    def test_structured_plan_confirmation_does_not_append_fake_chat_reply(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("/api/ai/plan/confirm", source)
        self.assertIn("/api/ai/plan/cancel", source)
        self.assertIn("planDigest", source)
        self.assertIn("idempotencyKey", source)
        self.assertNotIn("确认执行后追加用户消息", source)

    def test_external_digest_is_cached_bounded_and_failure_isolated(self):
        source = GATEWAY.read_text(encoding="utf-8")
        collector = (ROOT / "backend" / "d6" / "external_intelligence.py")
        self.assertTrue(collector.exists())
        text = collector.read_text(encoding="utf-8")
        for token in ("content_hash", "source_url", "published_at", "timeout", "max_items", "stale"):
            self.assertIn(token, text)
        self.assertIn("ExternalIntelligenceCollector", source)
        self.assertIn("_EXTERNAL_DIGEST_INTERVAL = 600", source)
        self.assertIn("_external_cycle_thread", source)
        self.assertIn('"external_digest"', source)

    def test_voice_input_accepts_transcript_aliases_and_rejects_raw_audio_explicitly(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn('body.get("transcript"', source)
        self.assertIn('body.get("voice_text"', source)
        self.assertIn("当前网关不提供音频转写", source)

    def test_external_config_is_persistent_and_invalid_urls_are_rejected(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("/api/ai/external/config", source)
        self.assertIn("update_config", source)
        self.assertIn("trafficUrl must use http or https", (ROOT / "backend" / "d6" / "external_intelligence.py").read_text(encoding="utf-8"))
        self.assertIn("前端只能切换外部信息采集开关", source)

    def test_external_information_isolated_from_state_reports_and_tts(self):
        source = GATEWAY.read_text(encoding="utf-8")
        cycle = source.split("def _run_proactive_cycle_now", 1)[1].split("def _proactive_cycle_thread", 1)[0]
        self.assertNotIn("run_cycle(external_items", cycle)
        self.assertIn("不进入状态上下文", source)
        self.assertIn('if report.get("kind") == "external_digest":', source)
        self.assertIn('category in {"external", "external_digest"}', source)
        external_cycle = source.split("def _run_external_cycle_now", 1)[1].split("def _external_cycle_thread", 1)[0]
        self.assertNotIn("create_report", external_cycle)
        self.assertNotIn("_record_context_event", external_cycle)
        self.assertNotIn("_tts_speak", external_cycle)
        page = (ROOT / "entry" / "src" / "main" / "ets" / "pages" / "ControlPanelPage.ets").read_text(encoding="utf-8")
        self.assertIn("if (item.kind === 'external_digest') return false", page)
        self.assertIn("external_digest", page)

    def test_absence_guard_requires_online_presence_sensor_and_turns_off_only_allowlisted_devices(self):
        guard = (ROOT / "backend" / "d6" / "adaptive_guard.py").read_text(encoding="utf-8")
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("absenceMonitor", guard)
        self.assertIn("presence_sensors", guard)
        self.assertIn("home_absence_device_on", guard)
        self.assertIn('"ac_01", "fan_02"', guard)
        self.assertIn('"devices": devices', gateway)

    def test_voice_control_has_persistent_bridge_lifecycle_and_chinese_audio_text(self):
        source = GATEWAY.read_text(encoding="utf-8")
        bridge = (ROOT / "backend" / "d6" / "voice_bridge_d6.py")
        self.assertTrue(bridge.exists())
        for token in ("_voice_config", "_set_voice_enabled", "_voice_bridge_status",
                      "_ensure_voice_bridge", "voice_01", "voice.disabled"):
            self.assertIn(token, source)
        bridge_source = bridge.read_text(encoding="utf-8")
        for token in ("AA 55", "extract_frames", "termios", "/api/voice/input", "A9_VOICE_SERIAL",
                      "AUTO_PORTS", "run_auto", "自动识别"):
            self.assertIn(token, bridge_source)

    def test_voice_frontend_does_not_expose_serial_path(self):
        settings = (ROOT / "entry" / "src" / "main" / "ets" / "pages" / "SettingsPage.ets").read_text(encoding="utf-8")
        self.assertIn("自动识别", settings)
        self.assertNotIn("D6串口路径", settings)
        self.assertNotIn("保存串口路径", settings)

    def test_tts_and_voice_sequence_remove_english_words(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _zh_voice_text", source)
        self.assertIn("OpenAI", source)
        self.assertIn("深度求索", source)
        self.assertIn("_zh_voice_text(text)", source)

    def test_tts_response_exposes_exact_chinese_speech_text(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn('"speechText": _voice_summary(text)', source)
        self.assertIn('"speechMode": "summary"', source)

    def test_voice_frame_parser_handles_split_frames_and_ignores_noise(self):
        import importlib.util
        bridge_path = ROOT / "backend" / "d6" / "voice_bridge_d6.py"
        spec = importlib.util.spec_from_file_location("voice_bridge_d6", bridge_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        first, tail = module.extract_frames(b"noise\xaa\x55\x00\x11")
        self.assertEqual(first, [])
        second, tail = module.extract_frames(tail + b"\xfb")
        self.assertEqual(second, [bytes.fromhex("AA 55 00 11 FB")])
        self.assertEqual(tail, b"")
        legacy, _ = module.extract_frames(b"\x00$B011#\xff")
        self.assertEqual(legacy, ["$B011#"])

    def test_manual_status_check_reuses_the_ten_minute_cycle(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("/api/ai/status/check", source)
        self.assertIn("_run_proactive_cycle_now", source)
        self.assertIn("run_cycle(force=True)", source)
        self.assertNotIn("run_cycle(external_items=external_items)", source)

    def test_offline_model_switch_and_field_nonce_clock_are_persistent(self):
        source = GATEWAY.read_text(encoding="utf-8")
        for token in ("/api/ai/offline/config", "_offline_model_config", "_set_offline_model_enabled",
                      "192.168.1.11:8080/v1/chat/completions", "_configure_field_nonce_clock",
                      "A9_FIELD_NONCE_SKEW_MS"):
            self.assertIn(token, source)

    def test_fresh_install_user_settings_default_to_enabled(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        guard = (ROOT / "backend" / "d6" / "adaptive_guard.py").read_text(encoding="utf-8")
        self.assertIn('"feedbackAutomation": {"enabled": True', guard)
        self.assertIn('configured.get("enabled", True)', gateway)
        self.assertIn('config.get("enabled", True)', gateway)

    def test_zero_zero_living_environment_is_not_published_as_a_real_reading(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _valid_living_environment", source)
        self.assertIn("温湿度设备返回无效零值", source)

    def test_door_password_is_required_only_for_open(self):
        namespace = load_gateway_functions("_door_password_required_for_action")
        required = namespace["_door_password_required_for_action"]

        self.assertTrue(required("open"))
        self.assertFalse(required("close"))
        self.assertFalse(required("query"))

    def test_door_ui_only_prompts_password_for_unlock_and_close_is_direct(self):
        page = (ROOT / "entry" / "src" / "main" / "ets" / "pages" / "DeviceCenterPage.ets").read_text(encoding="utf-8")
        self.assertIn("开门密码", page)
        self.assertIn("DeviceApi.toggle(device.id, false)", page)
        self.assertNotIn("this.isOnline(device) && this.doorPassword.length > 0 && !this.passwordConsumed, false", page)
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("_close_door_without_password", gateway)
        self.assertIn("_door_password_required_for_action(action)", gateway)

    def test_door_close_bypasses_both_field_controller_password_variants(self):
        tree = ast.parse(GATEWAY.read_text(encoding="utf-8"))
        selected = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_DOOR_CLOSE_LOCK"
                for target in node.targets
            ):
                selected.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name == "_close_door_without_password":
                selected.append(node)

        controller_namespace = {}

        def rejecting_verifier(_config, _password=None):
            raise RuntimeError("close should bypass this verifier")

        controller_namespace["verify_door_password"] = rejecting_verifier
        controller_namespace["verify_door_password_explicit"] = rejecting_verifier
        exec(
            "def living_door(config, action, timeout, password=None):\n"
            "    verify_door_password(config, password)\n"
            "    return {'success': action == 'close', 'state': 'closed'}\n",
            controller_namespace,
        )
        bridge_namespace = {
            "living_door": controller_namespace["living_door"],
            "_CONFIG": {},
            "_TIMEOUT": 1.0,
        }
        exec("def hw_toggle(*args, **kwargs): return {'success': False}", bridge_namespace)
        namespace = {"threading": threading, "hw_toggle": bridge_namespace["hw_toggle"]}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(GATEWAY), "exec"), namespace)

        result = namespace["_close_door_without_password"]()

        self.assertTrue(result["success"])
        self.assertIs(controller_namespace["verify_door_password"], rejecting_verifier)
        self.assertIs(controller_namespace["verify_door_password_explicit"], rejecting_verifier)


if __name__ == "__main__":
    unittest.main()
