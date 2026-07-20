import pathlib
import importlib.util
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend" / "d6"
BACKEND = BACKEND_DIR / "proactive_intelligence.py"
GATEWAY = BACKEND_DIR / "gateway_v6.py"
GUARD = BACKEND_DIR / "adaptive_guard.py"


class D6IntelligenceContractTests(unittest.TestCase):
    def read(self) -> str:
        return BACKEND.read_text(encoding="utf-8")

    def test_summary_persists_previous_state_and_reports_only_meaningful_changes(self):
        source = self.read()
        self.assertIn("assistant_state_snapshots", source)
        self.assertIn("_state_changes", source)
        self.assertIn("无明显变化", source)
        self.assertIn("温度", source)
        self.assertIn("湿度", source)
        self.assertIn("厨房热敏", source)
        self.assertIn('"heat_01": 20.0', source)
        self.assertIn("adjustmentCount", source)
        self.assertIn("系统未改变设备状态", source)

    def test_summary_uses_human_analysis_and_non_bar_chart_data(self):
        source = self.read()
        self.assertIn("建议", source)
        self.assertIn("line", source)
        self.assertIn("pie", source)
        self.assertIn("radar", source)
        self.assertNotIn('"type": "bar"', source)

    def test_summary_changes_when_sensor_delta_crosses_threshold(self):
        spec = importlib.util.spec_from_file_location("proactive_intelligence", BACKEND)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            engine = module.ProactiveIntelligence(pathlib.Path(directory) / "home.db")
            conn = engine._connect()
            conn.executescript("""
                CREATE TABLE sensor_readings(sensor_id TEXT, value REAL, unit TEXT, created_at TEXT);
                INSERT INTO sensor_readings VALUES ('temp_01', 24.0, '°C', '2026-07-18 12:00:00');
                INSERT INTO sensor_readings VALUES ('humid_01', 48.0, '%RH', '2026-07-18 12:00:00');
            """)
            conn.close()
            first = engine.run_cycle(now=1200)
            self.assertEqual(first[0]["severity"], "info")
            conn = engine._connect()
            conn.execute("INSERT INTO sensor_readings VALUES (?,?,?,?)", ("temp_01", 26.0, "°C", "2026-07-18 12:10:00"))
            conn.close()
            second = engine.run_cycle(now=1800)
            self.assertEqual(second[0]["severity"], "warning")
            self.assertIn("温度", second[0]["summary"])

    def test_tts_policy_has_global_cooldown_and_repeat_deduplication(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("_TTS_COOLDOWN_SECONDS", source)
        self.assertIn("_TTS_REPEAT_SECONDS", source)
        self.assertIn("_TTS_URGENT_COOLDOWN_SECONDS", source)
        self.assertIn("_LAST_TTS_TEXT", source)
        self.assertIn("tts.disabled", source)
        self.assertIn('"played": queued', source)
        self.assertIn("Manual device operations are context-only", source)
        self.assertIn("createdTs", source)
        self.assertIn("createdAt", source)
        self.assertIn("adjustment_count > 0", source)
        self.assertIn("getattr(self, 'command', '?')", source)

    def test_tts_uses_sentence_summary_and_never_says_generic_related_info(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _voice_summary", source)
        self.assertIn("播报摘要", source)
        self.assertIn("天气", source)
        self.assertNotIn('re.sub(r"[A-Za-z][A-Za-z0-9_.:/-]*", "相关信息"', source)
        self.assertIn("_is_meaningless_speech", source)
        self.assertIn('{"0", "1", "true", "false"', source)

    def test_proactive_cycle_is_ten_minutes_and_automation_uses_only_core_allowlist(self):
        proactive = self.read()
        gateway = GATEWAY.read_text(encoding="utf-8")
        service = (BACKEND_DIR / "automation" / "automation_service.py").read_text(encoding="utf-8")
        self.assertIn("window_seconds: int = 600", proactive)
        self.assertIn("now // 600", proactive)
        self.assertIn("十分钟家庭状态汇总", proactive)
        thread = gateway.split("def _proactive_cycle_thread", 1)[1].split("def _context_sync_thread", 1)[0]
        self.assertIn("next_run = time.monotonic() + 600.0", thread)
        self.assertIn("next_run += 600.0", thread)
        self.assertNotIn("next_run += 300.0", thread)
        self.assertIn('CORE_AUTOMATION_RULE_IDS', service)
        self.assertIn('["A006", "A008", "A009", "A010", "A011"]', gateway)
        self.assertIn("只允许十余项已确认核心策略", gateway)

    def test_theme_tts_has_separate_category_for_day_and_night_announcements(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("category", source.split("def _tts_speak", 1)[1].split("def _vs_entry", 1)[0])
        self.assertIn("theme", source)
        self.assertIn("_TTS_THEME_COOLDOWN_SECONDS", source)
        self.assertIn('category == "theme"', source)
        self.assertIn('normalized != previous_text', source)

    def test_device_status_parser_does_not_treat_action_word_as_power_on(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("_reply_state_is_on", source)
        self.assertNotIn('is_on = "ON" in reply.upper()', source)
        self.assertIn("(?:^|,)(?:state|power|action)=", source)

    def test_device_mutations_cache_commanded_state_and_use_per_device_tts_channel(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("_apply_commanded_device_state", source)
        self.assertIn('category=f"device:{device_id}"', source)
        self.assertIn("_TTS_DEVICE_COOLDOWN_SECONDS", source)

    def test_direct_ai_execution_is_persisted_for_future_context(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn('"ai_direct_execution"', source)
        self.assertIn('"commands": safe_commands', source)
        self.assertIn('"execution": batch', source)

    def test_device_and_setting_actions_are_announced_and_context_logged(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("_tts_speak(f\"{device_name}{action_text}", source)
        self.assertIn("_record_context_event(\n            \"device_operation\"", source)
        self.assertIn("announcements.append", source)
        self.assertIn("Adaptive guard configuration updated", source)

    def test_adaptive_guard_processes_live_snapshots(self):
        source = GATEWAY.read_text(encoding="utf-8")
        guard_block = source.split("def _process_adaptive_guard", 1)[1].split("def _publish_device_operation", 1)[0]
        self.assertIn("process_snapshot(_guard_snapshot(extra_kitchen))", guard_block)

    def test_linkage_rules_are_aligned_with_field_light_auto_and_guard_master_switch(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn('"living_light_auto"', source)
        self.assertIn('"auto"', source.split('"living_light_auto"', 1)[1].split('}', 1)[0])
        self.assertIn("LIGHT AUTO", source)
        self.assertIn("_linkage_master_enabled", source)
        self.assertNotIn("if _adaptive_guard is not None:\n        return  # The adaptive guard evaluates", source)

    def test_temperature_and_kitchen_rules_report_effective_guard_state(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("effective_enabled", source)
        self.assertIn("highTemperature", source)
        self.assertIn("kitchenAlarm", source)

    def test_super_context_initialization_does_not_block_http_startup(self):
        source = GATEWAY.read_text(encoding="utf-8")
        main_block = source.split("def main():", 1)[1].split('if __name__ == "__main__":', 1)[0]
        self.assertIn("target=_initialize_super_context_runtime", main_block)
        self.assertNotIn("_initialize_super_context()\n        threading.Thread(target=_context_sync_thread", main_block)
        runtime_block = source.split("def _initialize_super_context_runtime", 1)[1].split("def main():", 1)[0]
        self.assertIn("_initialize_super_context()", runtime_block)
        self.assertIn("target=_context_sync_thread", runtime_block)

    def test_submitted_feedback_removes_report_from_feed_and_rating_only_tracks_adjustments(self):
        source = self.read()
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("id NOT IN (SELECT report_id FROM assistant_feedback)", source)
        self.assertIn("adjustment_count > 0", gateway)
        self.assertIn("incident.get(\"executedActions\")", gateway)

    def test_feedback_accepts_adjustment_then_hides_report(self):
        spec = importlib.util.spec_from_file_location("proactive_intelligence_feedback", BACKEND)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            engine = module.ProactiveIntelligence(pathlib.Path(directory) / "home.db")
            report = engine.create_report(
                "summary", "调整测试", "已调整", {"adjustmentCount": 1},
                [{"device_id": "fan_02", "result": "ok"}],
                {"labels": ["换气扇"], "values": [1]}, created_ts=1000,
            )
            result = engine.submit_feedback(report["id"], 9, "A", "保持")
            self.assertEqual(result["score"], 9)
            self.assertEqual(engine.list_feed(limit=10), [])

    def test_prompt_includes_time_live_history_and_search_context(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _build_runtime_context", gateway)
        self.assertIn("当前时间", gateway)
        self.assertIn("传感器历史", gateway)
        self.assertIn("历史汇报", gateway)
        self.assertIn("检索命中", gateway)
        self.assertIn("近期日志", gateway)

    def test_runtime_retrieval_fuses_static_rag_and_long_term_context(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        optimizer = (ROOT / "backend" / "d6" / "retrieval_optimizer.py").read_text(encoding="utf-8")
        self.assertIn("HybridRetriever", gateway)
        self.assertIn("_hybrid_retriever.retrieve", gateway)
        self.assertIn("retrievalSources", optimizer)
        self.assertIn("long_term_context", optimizer)
        self.assertIn("解析失败", gateway)
        self.assertIn("智能判断约束", gateway)

    def test_feed_exposes_camel_case_timestamps_for_open_harmony(self):
        source = self.read()
        self.assertIn('result["createdAt"]', source)
        self.assertIn('result["createdTs"]', source)

    def test_vague_intent_and_ai_commands_execute_without_confirmation(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        chat_block = gateway.split("def _chat(self, body):", 1)[1].split("def _execute_intent", 1)[0]
        self.assertIn("_prepared_scene_intent", gateway)
        self.assertIn("execute=True", chat_block)
        self.assertIn("_execute_commands_concurrently", chat_block)
        self.assertNotIn("needs_plan =", chat_block)
        self.assertNotIn('response["planNonce"]', chat_block)
        self.assertNotIn("pending_entry = _put_pending_plan", chat_block)
        self.assertIn('"execution": result.get("result")', chat_block)

    def test_ai_system_prompt_requires_direct_execution_not_confirmation_cards(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        prompt_rules = gateway.split("### 规则", 1)[1].split('"""', 1)[0]
        self.assertIn("直接执行", prompt_rules)
        self.assertNotIn("确认执行", prompt_rules)
        self.assertNotIn("不执行的候选计划", prompt_rules)

    def test_sleep_phrase_matches_prepared_scene_and_executes_immediately(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("match_prepared_scene", gateway)
        self.assertIn('"source": "prepared_scene"', gateway)
        self.assertIn("_execute_intent(scene_intent, ai_execution=True)", gateway)

    def test_plan_confirmation_is_forced_off_in_guard_defaults(self):
        guard = GUARD.read_text(encoding="utf-8")
        self.assertIn('"planConfirmation": {"enabled": False}', guard)

    def test_guard_actions_execute_directly_with_bounded_concurrency(self):
        guard = GUARD.read_text(encoding="utf-8")
        execute_plan = guard.split("def _execute_plan", 1)[1].split("def _record_incident", 1)[0]
        self.assertIn("execute_device_commands", execute_plan)
        self.assertNotIn("for action in primary", execute_plan)

    def test_ai_plan_door_uses_configured_password_without_manual_prompt(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("aiExecution", gateway)
        self.assertIn('os.environ.get("A9_AI_DOOR_PASSWORD", "")', gateway)
        self.assertNotIn("_AI_DOOR_PASSWORD = \"", gateway)
        self.assertNotIn("门禁不能从计划卡执行，必须手动输入密码", gateway)

    def test_security_incidents_notify_qq_and_device_operations_use_notification_service(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("security_alert", gateway)
        self.assertIn("device_operation", gateway)
        self.assertIn("_notification_service.send", gateway)

    def test_runtime_context_never_returns_truncated_invalid_json(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("Keep the context valid JSON", gateway)
        self.assertNotIn("return json.dumps(packet, ensure_ascii=False, separators=(\",\", \":\"))[:14000]", gateway)

    def test_clear_context_marks_feed_boundary_without_erasing_learning_logs(self):
        source = self.read()
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("assistant_conversation_state", source)
        self.assertIn("clear_conversation", source)
        self.assertIn("_proactive_intelligence.clear_conversation", gateway)

    def test_runtime_poll_persists_device_state_for_five_minute_diff(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _save_device_snapshots", gateway)
        self.assertIn("_save_device_snapshots()", gateway)
        self.assertIn("created_at", self.read())
        live_block = gateway.split("def _context_live_state", 1)[1].split("def _save_device_snapshots", 1)[0]
        self.assertIn('return {"devices": devices', live_block)

    def test_sqlite_connections_use_wal_and_busy_timeout_for_concurrent_context_writes(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        context = (ROOT / "work" / "d6rag" / "context_engine.py").read_text(encoding="utf-8")
        self.assertIn("PRAGMA busy_timeout=30000", gateway)
        self.assertIn("PRAGMA journal_mode=WAL", gateway)
        self.assertIn("PRAGMA busy_timeout=30000", context)
        self.assertIn("PRAGMA journal_mode=WAL", context)

    def test_log_analysis_has_a_local_fast_path_without_upstream_ai(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        chat_block = gateway.split("def _chat(self, body):", 1)[1].split("def _execute_intent", 1)[0]
        self.assertIn("_is_log_analysis_request(last_text)", chat_block)
        self.assertIn("_build_log_analysis_response", chat_block)
        self.assertLess(
            chat_block.index("_build_log_analysis_response"),
            chat_block.index("automatic_context = build_turn_context"),
        )

    def test_deep_analysis_bypasses_shallow_intent_query_all(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        chat_block = gateway.split("def _chat(self, body):", 1)[1].split("def _execute_intent", 1)[0]
        self.assertIn("def _requires_deep_analysis", gateway)
        self.assertIn("if _intent_engine and not _requires_deep_analysis(last_text):", chat_block)
        self.assertIn("综合分析", gateway)
        self.assertIn("历史记录", gateway)

    def test_ai_context_uses_effective_linkage_state_over_legacy_switches(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        live = gateway.split("def _context_live_state", 1)[1].split("def _save_device_snapshots", 1)[0]
        self.assertIn("effective_enabled", live)
        self.assertIn("highTemperature", live)
        self.assertIn("kitchenAlarm", live)
        self.assertIn("判断联动是否开启时必须以 effective_enabled 为准", gateway)

    def test_security_anomalies_publish_assistant_qq_context_and_buzzer_actions(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _publish_security_anomaly", gateway)
        block = gateway.split("def _publish_security_anomaly", 1)[1].split("def _reply_state_is_on", 1)[0]
        for token in (
            "security_events", "_record_context_event", "_notify_qq_async",
            "create_report", 'hw_toggle("alarm_01", True)',
        ):
            self.assertIn(token, block)
        self.assertIn("record_door_password_failure", gateway)
        self.assertIn("observe_state", gateway)

    def test_safe_kitchen_recovery_does_not_look_like_an_intrusion(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        watch = gateway.split("def _security_state_watch_thread", 1)[1].split("def _save_sensor_readings", 1)[0]
        self.assertIn("kitchen_alarm_active", watch)
        self.assertIn('source="sensor_recovery"', watch)
        self.assertIn('device_id in {"alarm_01", "fan_02"}', watch)

    def test_log_stats_count_events_and_daily_reads_refresh_first(self):
        gateway = GATEWAY.read_text(encoding="utf-8")
        security_block = gateway.split("def _security_stats", 1)[1].split("def _auth_status", 1)[0]
        self.assertIn("COUNT(*) FROM security_events", security_block)
        self.assertIn("GROUP BY severity", security_block)
        daily_route = gateway.split('elif p == "/api/log/daily"', 1)[1].split('elif p == "/api/log/today"', 1)[0]
        self.assertIn("_daily_log_update()", daily_route)

    def test_repeated_toggle_ignores_failed_and_idempotent_requests(self):
        spec = importlib.util.spec_from_file_location("proactive_intelligence", BACKEND)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            engine = module.ProactiveIntelligence(pathlib.Path(directory) / "home.db")
            for index in range(4):
                engine.record_operation("fan_02", "toggle", {"isOn": False}, created_ts=1000 + index)
            engine.record_operation("fan_02", "toggle", {"isOn": True}, result="failed", created_ts=1005)
            reports = engine.run_cycle(now=1010)
            self.assertFalse(any(report["kind"] == "repeated_toggle" for report in reports))

    def test_manual_cycle_can_emit_a_fresh_report_in_the_same_five_minute_bucket(self):
        spec = importlib.util.spec_from_file_location("proactive_intelligence_manual", BACKEND)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            engine = module.ProactiveIntelligence(pathlib.Path(directory) / "home.db")
            first = engine.run_cycle(now=1200)
            self.assertTrue(first)
            manual = engine.run_cycle(now=1210, force=True)
            self.assertTrue(manual)
            self.assertEqual(manual[0]["kind"], "summary")

    def test_empty_state_does_not_generate_a_zero_only_chart(self):
        spec = importlib.util.spec_from_file_location("proactive_intelligence_empty_chart", BACKEND)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            engine = module.ProactiveIntelligence(pathlib.Path(directory) / "home.db")
            self.assertEqual(engine._summary_chart([], [], {}), {})

    def test_alert_acknowledgement_is_durable_and_does_not_delete_dialogue(self):
        spec = importlib.util.spec_from_file_location("proactive_intelligence_ack", BACKEND)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            engine = module.ProactiveIntelligence(pathlib.Path(directory) / "home.db")
            report = engine.create_report(
                "security_alert", "温度报警", "温度过高", {"temperature": 31.2}, [], {},
                severity="danger", created_ts=1000,
            )
            self.assertFalse(engine.is_alert_acknowledged(report["id"]))
            acknowledged = engine.acknowledge_alert(report["id"])
            self.assertTrue(acknowledged["success"])
            self.assertTrue(engine.is_alert_acknowledged(report["id"]))
            self.assertEqual(len(engine.list_feed(limit=10)), 1)

    def test_gateway_exposes_alert_acknowledgement_contract(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn('/api/ai/assistant/acknowledge', source)
        self.assertIn('requiresAcknowledgement', source)
        self.assertIn('acknowledged', source)
        self.assertIn('def _acknowledge_assistant_alert', source)


if __name__ == "__main__":
    unittest.main()
