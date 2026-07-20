from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ETS = ROOT / "entry" / "src" / "main" / "ets"


class ControlCenterContractTests(unittest.TestCase):
    def test_real_automation_adjustment_uses_post_action_acknowledgement_popup(self):
        source = self.read("pages/ControlPanelPage.ets")
        self.assertIn("item.kind === 'automation_adjustment'", source)
        self.assertIn("'智能调整'", source)
        self.assertIn("item.evidence['triggerReason']", source)
        self.assertIn("item.evidence['deviceSummary']", source)
        self.assertIn("item.evidence['actionSummary']", source)
        self.assertIn("item.evidence['resultSummary']", source)

    def read(self, relative: str) -> str:
        return (ETS / relative).read_text(encoding="utf-8")

    def test_main_shell_has_four_real_sections(self):
        source = self.read("pages/ControlPanelPage.ets")
        for label in ("助手", "设备", "数据管理", "设置"):
            self.assertIn(f"'{label}'", source)
        self.assertIn("DeviceCenterPage", source)
        self.assertIn("SettingsPage", source)

    def test_brand_logo_is_preserved_in_top_bar(self):
        source = self.read("pages/ControlPanelPage.ets")
        self.assertIn("brandMark", source)
        self.assertIn("明日", source)
        self.assertIn("家居", source)

    def test_device_center_calls_real_control_apis_and_manual_door_password(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("DeviceApi.toggle", source)
        self.assertIn("DeviceApi.setAcTemperature", source)
        self.assertIn("DeviceApi.setCurtainPosition", source)
        self.assertIn("DeviceApi.unlockDoor", source)
        self.assertIn("doorPassword", source)

    def test_guard_settings_feedback_and_telemetry_use_backend_endpoints(self):
        api = self.read("api/guardApi.ets")
        settings = self.read("pages/SettingsPage.ets")
        assistant = self.read("api/assistantApi.ets")
        self.assertIn("/api/ai/guard/status", api)
        self.assertIn("/api/ai/guard/config", api)
        self.assertIn("/api/ai/guard/feedback", api)
        self.assertIn("/api/app/telemetry", api)
        self.assertIn("GuardApi.updateConfig", settings)
        self.assertIn("/api/ai/assistant/feedback", assistant)

    def test_settings_default_on_and_use_current_d6_address_without_false_offline_reset(self):
        http = self.read("api/http.ets")
        settings = self.read("pages/SettingsPage.ets")
        guard = self.read("api/guardApi.ets")
        self.assertIn("static readonly BASE: string = 'http://192.168.1.73:8080'", http)
        self.assertLess(http.index("192.168.1.73:8080"), http.index("192.168.1.94:8080"))
        for token in (
            "@State linkageEnabled: boolean = true",
            "@State activeAiEnabled: boolean = true",
            "@State feedbackAutomationEnabled: boolean = true",
            "@State radarEnabled: boolean = true",
            "@State externalEnabled: boolean = true",
            "@State voiceEnabled: boolean = true",
            "@State offlineModelEnabled: boolean = true",
        ):
            self.assertIn(token, settings)
        self.assertIn("available: false, enabled: true, activeAiEnabled: true, feedbackAutomationEnabled: true", guard)
        self.assertIn("static async getRadarEnabled(): Promise<boolean | null>", guard)
        self.assertIn("if (nextRadar !== null) this.radarEnabled = nextRadar", settings)

    def test_removed_atmosphere_light_is_absent_from_active_frontend(self):
        active = "\n".join(path.read_text(encoding="utf-8") for path in ETS.rglob("*.ets"))
        self.assertNotIn("light_05", active)
        self.assertNotIn("氛围灯", active)

    def test_loading_shell_is_full_screen_and_has_no_side_rail(self):
        shell = self.read("pages/ControlPanelPage.ets")
        ability = self.read("entryability/EntryAbility.ets")
        self.assertNotIn("Column().width(3).height('100%')", shell)
        self.assertIn("setWindowLayoutFullScreen(true)", ability)
        self.assertIn("setWindowSystemBarEnable([])", ability)
        module = (ROOT / "entry" / "src" / "main" / "module.json5").read_text(encoding="utf-8")
        self.assertIn('"orientation": "portrait"', module)

    def test_shell_is_portrait_with_extended_square_loading_motion(self):
        shell = self.read("pages/ControlPanelPage.ets")
        core = self.read("components/TacticalMotionCore.ets")
        module = (ROOT / "entry" / "src" / "main" / "module.json5").read_text(encoding="utf-8")
        loading = shell.split("loadingScreen", 1)[1].split("header", 1)[0]
        self.assertIn('"orientation": "portrait"', module)
        self.assertIn("TacticalMotionCore", loading)
        self.assertNotIn("ProgressType.Linear", core)
        self.assertIn("this.later(8000", shell)
        self.assertIn(".height(78)", shell)
        self.assertIn(".width(184)", core)
        self.assertIn(".height(184)", core)

    def test_device_page_is_categorized_and_has_no_sensor_console(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertNotIn("SensorApi", source)
        self.assertNotIn("environmentStrip", source)
        for label in ("门禁与出入口", "温控与空气", "照明与遮阳", "自定义设备"):
            self.assertIn(label, source)

    def test_voice_control_is_visible_and_has_a_persistent_backend_switch(self):
        device = self.read("pages/DeviceCenterPage.ets")
        settings = self.read("pages/SettingsPage.ets")
        chat_api = self.read("api/chatApi.ets")
        self.assertNotIn("'voice_01'", device.split("hiddenDeviceIds", 1)[1].split(";", 1)[0])
        self.assertIn("语音控制", device + settings)
        self.assertIn("voice_01", device)
        self.assertIn("getVoiceConfig", chat_api)
        self.assertIn("setVoiceEnabled", chat_api)

    def test_voice_switch_is_top_level_and_shows_explicit_live_state(self):
        settings = self.read("pages/SettingsPage.ets")
        self.assertIn("voiceSettings()", settings)
        self.assertLess(settings.index("this.voiceSettings()"), settings.index("this.guardSettings()"))
        self.assertIn("title: '语音控制开关'", settings)
        self.assertIn("this.voiceEnabled ? '已开启' : '已关闭'", settings)
        self.assertIn("if (!this.voiceHydrated) return '状态读取中'", settings)

    def test_offline_model_switch_is_visible_and_reconciles_with_backend(self):
        settings = self.read("pages/SettingsPage.ets")
        chat_api = self.read("api/chatApi.ets")
        for token in ("离线模型", "offlineModelEnabled", "getOfflineModelConfig", "setOfflineModelEnabled"):
            self.assertIn(token, settings + chat_api)
        self.assertIn("本地不可达时自动回退在线模型", settings)

    def test_settings_hides_transport_section_and_environment_hides_alarm_stats(self):
        settings = self.read("pages/SettingsPage.ets")
        history = self.read("pages/HistoryPage.ets")
        self.assertNotIn("通知与安全传输", settings)
        self.assertNotIn("protocolGrid", settings)
        self.assertIn("visibleEnvironmentStats", history)
        self.assertIn("'smoke'", history)
        self.assertIn("'heat'", history)

    def test_portrait_settings_uses_column_axis_alignment(self):
        settings = self.read("pages/SettingsPage.ets")
        build = settings.split("build()", 1)[1]
        self.assertIn("Column({ space: 14 })", build)
        self.assertIn(".alignItems(HorizontalAlign.Start)", build)
        self.assertNotIn(".alignItems(VerticalAlign.Top)", build)

    def test_settings_separates_feedback_automation_from_active_ai_and_hides_rating_panel(self):
        settings = self.read("pages/SettingsPage.ets")
        api = self.read("api/guardApi.ets")
        self.assertIn("评分自动触发", settings)
        self.assertIn("feedbackAutomationEnabled", settings)
        self.assertIn("feedbackAutomationEnabled", api)
        build = settings.split("build()", 1)[1]
        self.assertNotIn("feedbackPanel()", build)
        self.assertNotIn("行为评分与长期学习", build)

    def test_settings_switches_use_linked_reactive_components(self):
        settings = self.read("pages/SettingsPage.ets")
        toggle = self.read("components/TacticalToggle.ets")
        self.assertIn("@Link isOn: boolean", toggle)
        self.assertIn("onToggle?: (enabled: boolean) => void", toggle)
        for state in ("$linkageEnabled", "$activeAiEnabled", "$feedbackAutomationEnabled", "$radarEnabled"):
            self.assertIn(state, settings)
        self.assertNotIn("$planConfirmationEnabled", settings)
        self.assertNotIn("settingEnabled(key", settings)
        self.assertNotIn("fontSize(11)", settings)
        self.assertNotIn("fontSize(9)", settings)

    def test_animation_matches_harmon_index_motion_contract(self):
        shell = self.read("pages/ControlPanelPage.ets")
        for token in ("loadingOuterAngle", "loadingInnerAngle", "transitionKind", "transitionVisible",
                      "themeSweep", "TacticalMotion.THEME_ROUTE"):
            self.assertIn(token, shell)

    def test_transition_progress_is_component_reactive_and_theme_has_phrases(self):
        shell = self.read("pages/ControlPanelPage.ets")
        core = self.read("components/TacticalMotionCore.ets")
        self.assertIn("@Prop progress: number", core)
        self.assertIn("motionRail", core)
        self.assertNotIn("Progress({ value: progress", core)
        self.assertIn("resetTransition", shell)
        self.assertIn("transitionAt", shell)
        self.assertIn("transitionGeneration", shell)
        self.assertIn("天光接管，居所进入明昼模式", shell)
        self.assertIn("夜幕落下，系统转入低光守护", shell)
        self.assertIn("ChatApi.speak(this.themePhrase, 'theme')", shell)

    def test_settings_switch_reads_live_guard_mode_and_persists_click(self):
        settings = self.read("pages/SettingsPage.ets")
        self.assertIn("savingKey", settings)
        self.assertIn("if (this.savingKey.length === 0)", settings)
        self.assertIn("rollbackSetting", settings)
        self.assertIn("GuardApi.updateConfig(enabled, activeAi, feedbackAutomationEnabled)", settings)

    def test_assistant_events_are_rendered_as_conversation_bubbles_and_keep_charts(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("HarmonChatBubble", shell)
        self.assertIn("thinkingIndicator", shell)
        self.assertIn("ChatChartPanel", shell)
        self.assertIn("this.showThinking", shell)

    def test_assistant_hides_intelligence_strip_and_settings_owns_manual_check(self):
        assistant = self.read("pages/ControlPanelPage.ets")
        settings = self.read("pages/SettingsPage.ets")
        page = assistant.split("assistantPage()", 1)[1]
        self.assertNotIn("智能态势", assistant)
        self.assertNotIn("intelligenceStrip()", page)
        self.assertIn("立即检测", settings)
        self.assertIn("runStatusCheck", settings)

    def test_settings_exposes_exit_button(self):
        settings = self.read("pages/SettingsPage.ets")
        self.assertIn("退出软件", settings)
        self.assertIn("terminateSelf", settings)

    def test_settings_exposes_conversation_clear_action(self):
        settings = self.read("pages/SettingsPage.ets")
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("清空助手对话", settings)
        self.assertIn("onClearConversation", settings)
        self.assertIn("onClearConversation", shell)
        self.assertIn("hiddenFeedIds", shell)

    def test_git_motion_is_slow_enough_for_readable_route_transition(self):
        theme = self.read("theme/TacticalTheme.ets")
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("ROUTE: number = 2400", theme)
        self.assertIn("THEME_ROUTE: number = 2600", theme)
        self.assertIn("this.loadingOuterAngle = 240", shell)
        self.assertIn("this.loadingInnerAngle = -240", shell)

    def test_assistant_input_uses_icon_controls_and_preserves_speech_action(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("sys.symbol.mic_fill", shell)
        self.assertIn("sys.symbol.paperplane_fill", shell)
        self.assertIn("ChatApi.speak", shell)
        self.assertNotIn("ChatApi.speak(reply)", shell)

    def test_feed_filters_history_and_uses_non_bar_multi_chart_summary(self):
        shell = self.read("pages/ControlPanelPage.ets")
        api = self.read("api/assistantApi.ets")
        self.assertIn("createdTs", api)
        self.assertIn("isConversationFeedItem", shell)
        self.assertIn("if (item.kind === 'summary') return true", shell)
        self.assertIn("type: isTimeline ? 'line' : 'pie'", shell)
        self.assertNotIn("type: 'radar'", shell.split("private feedChartData", 1)[1].split("private async submitAssistantFeedback", 1)[0])
        self.assertNotIn("type: 'bar'", shell.split("private feedChartData", 1)[1].split("private async submitAssistantFeedback", 1)[0])
        self.assertIn("return undefined", shell.split("private feedChartData", 1)[1].split("private async submitAssistantFeedback", 1)[0])

    def test_settings_callback_is_not_a_decorated_function_prop(self):
        settings = self.read("pages/SettingsPage.ets")
        self.assertIn("onClearConversation?: () => void", settings)
        self.assertNotIn("@Prop onClearConversation", settings)

    def test_feed_events_and_chat_messages_share_real_time_order(self):
        shell = self.read("pages/ControlPanelPage.ets")
        for token in ("interface TimelineEntry", "eventTimestamp", "timelineEntries", "createdTs", "触发模式："):
            self.assertIn(token, shell)
        self.assertIn("this.feedOpenedAt - 600", shell)
        self.assertIn("a.kind === 'event' ? -1 : 1", shell)
        self.assertIn("ForEach(this.timelineEntries()", shell)

    def test_manual_device_operations_stay_in_context_not_assistant_feed(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("if (item.kind === 'device_operation') return false", shell)
        self.assertIn("if (item.kind === 'summary') return true", shell)
        self.assertIn("系统分析、风险判断和可执行调整建议", shell)

    def test_system_feed_items_are_auto_spoken_once(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("spokenFeedIds", shell)
        self.assertIn("speakFeedItemOnce", shell)
        self.assertIn("ChatApi.speak(this.assistantEventText(item))", shell)
        self.assertIn("if (item.kind === 'device_operation') return false", shell)

    def test_assistant_feed_is_compact_and_voice_is_rate_limited(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("MAX_VISIBLE_SYSTEM_FEED: number = 3", shell)
        self.assertIn("FEED_SPEECH_COOLDOWN_MS: number = 30000", shell)
        self.assertIn("this.lastFeedSpeechAt", shell)
        self.assertIn("item.severity === 'danger' || item.severity === 'warning'", shell)
        self.assertIn("feedInitialized", shell)
        self.assertIn("newItems", shell)
        self.assertIn("const visible = compact.slice(0, ControlPanelPage.MAX_VISIBLE_SYSTEM_FEED)", shell)
        self.assertIn("stableSummarySeen", shell)

    def test_clear_conversation_clears_local_view_and_backend_context(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("import { AiApi }", shell)
        self.assertIn("AiApi.clearContext()", shell)
        self.assertIn("this.messages = [{ id: 'msg_0'", shell)
        self.assertIn("this.assistantFeed = []", shell)

    def test_automatic_management_is_recorded_without_feedback_gate(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("确定性自动管理 / 设备服务", shell)
        self.assertIn("if (item.kind === 'device_operation') return false", shell)
        self.assertIn("friendlyAction", shell)

    def test_data_management_keeps_live_refresh(self):
        source = self.read("pages/HistoryPage.ets")
        self.assertIn("setInterval", source)
        self.assertIn("refreshLogData", source)

    def test_log_counts_use_database_totals_and_chat_history_feed(self):
        page = self.read("pages/HistoryPage.ets")
        api = self.read("api/logApi.ets")
        self.assertIn("/api/chat/history?limit=", api)
        self.assertIn("total: number", api)
        self.assertIn("private totalLogCount()", page)
        self.assertIn("this.operationFeed.total", page)
        self.assertIn("this.aiConversationFeed.total", page)
        self.assertIn("'数据库日志'", page)

    def test_arknights_device_actions_use_compact_normal_buttons_and_feedback_state(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("TacticalCutCornerButton", source)
        self.assertIn("pressedActionKey", source)
        self.assertIn("lastActionResult", source)
        self.assertIn("buttonHeight: 44", source)

    def test_device_ranges_use_native_diamond_slider_with_release_commit(self):
        self.assertTrue((ETS / "components/TacticalDiamondSlider.ets").exists(),
                        "diamond slider component must exist")
        slider = self.read("components/TacticalDiamondSlider.ets")
        for token in ("Slider({", "SliderChangeMode.Begin", "SliderChangeMode.Moving",
                      "SliderChangeMode.End", "SliderChangeMode.Click", "onPreview", "onCommit",
                      "diamondThumb", ".height(44)"):
            self.assertIn(token, slider)
        self.assertIn("if (mode === SliderChangeMode.End || mode === SliderChangeMode.Click)", slider)

    def test_slider_reenable_does_not_restore_the_stale_pre_command_value(self):
        slider = self.read("components/TacticalDiamondSlider.ets")
        reenable = slider.split("syncEnabledState(): void", 1)[1].split("private clampAndSnap", 1)[0]
        self.assertNotIn("this.previewValue = this.clampAndSnap(this.value)", reenable)
        self.assertIn("this.dragging = false", reenable)

    def test_device_values_are_optimistic_then_reconciled_with_hardware(self):
        source = self.read("pages/DeviceCenterPage.ets")
        for token in ("pendingDeviceValues", "pendingValueDeadlines", "applyOptimisticValue",
                      "mergePendingValue", "scheduleReconciliation"):
            self.assertIn(token, source)
        self.assertIn("expectedValue?: number", source)
        self.assertIn("DeviceApi.toggle(device.id, false), false", source)
        self.assertIn("DeviceApi.setBrightness(device.id, value), value > 0, value", source)
        self.assertIn("DeviceApi.setFanSpeed(device.id, value), value > 0, value", source)

    def test_assistant_charts_omit_empty_and_synthetic_alarm_graphs(self):
        shell = self.read("pages/ControlPanelPage.ets")
        chart = self.read("components/ChatChartPanel.ets")
        feed_block = shell.split("private feedChartData", 1)[1].split("private feedbackDraft", 1)[0]
        self.assertIn("meaningfulChartConfigs", chart)
        self.assertIn("return meaningfulChartConfigs(this.chartData)", chart)
        self.assertNotIn("evidenceCount", feed_block)
        self.assertNotIn("feed_radar_", feed_block)
        self.assertNotIn("feed_line_", feed_block)
        self.assertIn("if (positiveCount < 2)", feed_block)

    def test_real_alarm_feed_uses_persistent_acknowledgement_popup(self):
        shell = self.read("pages/ControlPanelPage.ets")
        for token in ("pendingAcknowledgementId", "acknowledgementOverlay",
                      "我已知晓", "confirmAlertAcknowledgement"):
            self.assertIn(token, shell)
        self.assertIn("item.requiresAcknowledgement === true", shell)
        self.assertIn("AssistantApi.acknowledgeAlert(item.id)", shell)
        self.assertIn("完整记录已保留在助手对话中", shell)

    def test_assistant_feed_and_feedback_are_wired(self):
        api = self.read("api/assistantApi.ets")
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("/api/ai/assistant/feed", api)
        self.assertIn("/api/ai/assistant/feedback", api)
        self.assertIn("submitFeedback", shell)
        self.assertIn("scoreRow", shell)
        self.assertIn("this.assistantFeed = this.assistantFeed.filter", shell)

    def test_feedback_drafts_are_isolated_per_report(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("class FeedbackDraft", shell)
        self.assertIn("@State feedbackDrafts: FeedbackDraft[]", shell)
        self.assertIn("private feedbackDraft(itemId: number)", shell)
        self.assertIn("private updateFeedback(itemId: number", shell)
        self.assertIn("状态汇报\\n时间：", shell)

    def test_external_intelligence_has_a_persistent_settings_switch(self):
        settings = self.read("pages/SettingsPage.ets")
        api = self.read("api/assistantApi.ets")
        self.assertIn("外部信息摘要", settings)
        self.assertIn("externalEnabled", settings)

    def test_today_realtime_chart_id_matches_history_gauge_reader(self):
        gateway = (ROOT / "backend" / "d6" / "gateway_v6.py").read_text(encoding="utf-8")
        history = self.read("pages/HistoryPage.ets")
        self.assertIn('"id": "today_gauge"', gateway)
        self.assertIn("chart.id === 'today_gauge'", history)

    def test_external_digest_shows_chinese_source_name_instead_of_raw_url(self):
        api = (ROOT / "entry" / "src" / "main" / "ets" / "api" / "assistantApi.ets").read_text(encoding="utf-8")
        page = (ROOT / "entry" / "src" / "main" / "ets" / "pages" / "ControlPanelPage.ets").read_text(encoding="utf-8")
        self.assertIn("source_name", api)
        self.assertIn("item.source_name", page)
        self.assertIn("getExternalConfig", api)
        self.assertIn("setExternalEnabled", api)

    def test_loading_transition_has_no_background_grid(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertNotIn("ForEach([0, 1, 2]", shell)

    def test_assistant_uses_human_readable_event_template_not_raw_json(self):
        shell = self.read("pages/ControlPanelPage.ets")
        for label in ("触发模式：", "触发时间：", "触发原因：", "实时证据：", "设备：", "描述：", "具体操作：", "操作结果：", "建议：", "本次评分：", "改进方式："):
            self.assertIn(label, shell)
        self.assertIn("item.evidence['evidenceSummary']", shell)
        self.assertNotIn("厨房检测到报警信号，系统进入安全联动流程。", shell)
        self.assertNotIn("JSON.stringify(operation)", shell)
        self.assertNotIn("item.summary).width", shell)
        self.assertIn("note: string", shell)
        self.assertIn("写下更好的处理方式", shell)
        self.assertIn("A 保持当前", shell)
        self.assertIn("B 减少动作", shell)
        self.assertIn("C 只提醒", shell)
        self.assertIn("D 使用填写方案", shell)
        self.assertIn("item.feedbackEnabled === true", shell)

    def test_guard_incident_is_not_duplicated_beside_its_detailed_automation_receipt(self):
        gateway = (ROOT / "backend" / "d6" / "gateway_v6.py").read_text(encoding="utf-8")
        self.assertIn("_automation_service.outbox.has_source_incident", gateway)
        self.assertIn("list_incidents(limit=200, pending_only=True)", gateway)

    def test_loading_motion_is_slow_and_minimal(self):
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("this.later(8000", shell)
        self.assertIn("loadingProgress", shell)
        self.assertIn("themeSweep", shell)
        self.assertNotIn("switchProgress < (index + 1)", shell)

    def test_device_page_is_compact_and_does_not_use_large_card_padding(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("deviceActionGrid", source)
        self.assertIn(".height(38)", source)
        self.assertNotIn(".padding(12)", source)
        self.assertNotIn("真实设备接口，5 秒刷新。每次操作结果自动写入长期上下文。", source)

    def test_user_facing_device_labels_hide_internal_ids(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("friendlyDeviceName", source)
        self.assertNotIn("Text(device.id)", source)
        self.assertNotIn("等待 D6 后端设备接口", source)

    def test_user_facing_metrics_use_plain_chinese_labels(self):
        history = self.read("pages/HistoryPage.ets")
        charts = self.read("components/ChatChartPanel.ets")
        self.assertNotIn("AI消息", history)
        self.assertNotIn("AI消息", charts)
        self.assertIn("对话", history)
        self.assertIn("对话", charts)
        self.assertIn("#8FD3EE18", charts)
        self.assertIn("趋势", charts)

    def test_invalid_environment_reading_is_not_rendered_as_zero_offline(self):
        history = self.read("pages/HistoryPage.ets")
        self.assertIn("sensor.current.unit === '离线'", history)
        self.assertIn("暂不可用", history)

    def test_settings_subtitles_are_compact(self):
        source = self.read("pages/SettingsPage.ets")
        for label in ("温湿度、厨房、门禁、光敏灯", "读取环境与历史行为", "高分策略自动复用", "人体存在检测"):
            self.assertIn(label, source)
        self.assertNotIn("计划确认后执行", source)
        self.assertNotIn("$planConfirmationEnabled", source)
        self.assertNotIn("允许 AI 主动关联上下文和历史评分", source)

    def test_legacy_plan_fields_remain_compatible_but_ui_never_uses_them(self):
        types = self.read("api/types.ets")
        api = self.read("api/chatApi.ets")
        shell = self.read("pages/ControlPanelPage.ets")
        self.assertIn("planNonce?: string", types)
        self.assertIn("planNonce?: string", api)
        self.assertIn("sendComplete(messages: ChatMessage[], planNonce?: string)", api)
        self.assertIn("planNonce: planNonce", api)
        for token in ("是否一键执行这份计划", "executePlan", "cancelPlan", "message.planNonce"):
            self.assertNotIn(token, shell)

    def test_active_tactical_surfaces_have_readable_type_and_no_legacy_devices(self):
        active_files = (
            "pages/ControlPanelPage.ets", "pages/DeviceCenterPage.ets", "pages/HistoryPage.ets",
            "pages/SettingsPage.ets", "components/HarmonChatBubble.ets",
            "components/ChatChartPanel.ets", "components/TacticalToggle.ets",
            "components/TacticalMotionCore.ets",
        )
        active = "\n".join(self.read(path) for path in active_files)
        for size in range(8, 14):
            self.assertNotIn(f"fontSize({size})", active)
        self.assertNotIn("fan_01", active)
        self.assertNotIn("exhaust_01", active)
        self.assertIn("fan_02", self.read("pages/DeviceCenterPage.ets"))

    def test_line_chart_replays_every_real_point_after_area_fill(self):
        chart = self.read("components/ChatChartPanel.ets")
        self.assertIn("private traceLine", chart)
        self.assertGreaterEqual(chart.count("this.traceLine(values, pointCount"), 2)
        self.assertIn("if (this.validSampleCount() === 0)", chart)

    def test_device_cards_use_one_state_toggle_and_release_commit_sliders(self):
        source = self.read("pages/DeviceCenterPage.ets")
        for token in ("stateToggle", "TacticalDiamondSlider", "commitBrightness", "commitFanSpeed",
                      "commitCurtain", "commitAcTemperature", "min: 16", "max: 30", "step: 1",
                      "min: 0", "max: 100", "step: 10"):
            self.assertIn(token, source)
        self.assertNotIn("stepperButton(", source)
        self.assertNotIn("adjustBrightness", source)
        self.assertNotIn("adjustFanSpeed", source)
        self.assertNotIn("adjustCurtain", source)
        self.assertNotIn("亮度 50%", source)
        self.assertNotIn("亮度 100%", source)
        self.assertNotIn("风速 30%", source)
        self.assertNotIn("风速 100%", source)
        self.assertIn("Row({ space: 5 }) {\n        this.actionButton('送风'", source)

    def test_primary_controls_keep_all_decoration_inside_the_control_frame(self):
        button = self.read("components/TacticalCutCornerButton.ets")
        toggle = self.read("components/TacticalToggle.ets")
        device = self.read("pages/DeviceCenterPage.ets")
        settings = self.read("pages/SettingsPage.ets")
        shell = self.read("pages/ControlPanelPage.ets")
        for token in ("innerRail", "stateMarker", ".borderRadius(0)", "TacticalCutCornerButton"):
            self.assertIn(token, button + device + settings + shell)
        self.assertNotIn("cornerDiamond", button)
        self.assertNotIn("rotate({ angle: 45 })", button + toggle)
        for token in ("toggleProgress", "toggleOrbit", "rotate({ angle: this.toggleProgress", "TacticalMotion.SWITCH"):
            self.assertIn(token, toggle)
        self.assertNotIn("borderRadius(19)", device)

    def test_device_actions_reconcile_optimistic_state_and_ignore_stale_reads(self):
        source = self.read("pages/DeviceCenterPage.ets")
        for token in ("pendingDeviceStates", "loadSequence", "appliedLoadSequence", "mergePendingState",
                      "applyOptimisticState", "expectedState", "if (requestId < this.appliedLoadSequence)"):
            self.assertIn(token, source)

    def test_device_cards_rebuild_when_live_state_changes(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("private deviceRenderKey(device: Device): string", source)
        self.assertIn("(device: Device) => this.deviceRenderKey(device)", source)
        self.assertNotIn("(device: Device) => device.id)", source)
        self.assertIn("return device.id;", source[source.index("private deviceRenderKey"):])
        # 状态变化由稳定 key 下的 @Watch 动效节点接收；列表仍靠 fingerprint 触发数组更新。
        for token in ("device.isOn", "device.primaryValue", "device.status", "device.mode"):
            self.assertIn(token, source[source.index("const fingerprint"):source.index("if (fingerprint")])

    def test_device_toggle_resolves_latest_state_at_click_time(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("private toggleDeviceById(deviceId: string): void", source)
        self.assertIn("this.devices.find((device: Device) => device.id === deviceId)", source)
        self.assertIn("this.setDevicePower(deviceId, !current.isOn)", source)
        self.assertIn("TacticalDeviceToggle", source)
        self.assertIn("onToggle: (next: boolean)", source)
        toggle_builder = source.split("stateToggle(device: Device)", 1)[1].split("deviceActionGrid", 1)[0]
        self.assertNotIn("DeviceApi.toggle(device.id, !device.isOn)", toggle_builder)

    def test_settings_and_device_controls_reconcile_child_motion_from_parent_state(self):
        toggle = self.read("components/TacticalToggle.ets")
        settings = self.read("pages/SettingsPage.ets")
        device = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("@Watch('syncToggleProgress')", toggle)
        self.assertIn("export struct TacticalDeviceToggle", toggle)
        self.assertIn("@Prop @Watch('syncToggleProgress') isOn", toggle)
        self.assertIn("TacticalDeviceToggle", device)
        self.assertIn("syncToggleProgress", toggle)
        self.assertIn("settingsHydrated", settings)
        self.assertIn("settingsLoadError", settings)
        self.assertIn("authoritative", device)

    def test_device_toggle_uses_local_visual_state_for_consecutive_on_then_off(self):
        toggle = self.read("components/TacticalToggle.ets")
        device = self.read("pages/DeviceCenterPage.ets")
        device_toggle = toggle.split("export struct TacticalDeviceToggle", 1)[1].split(
            "export struct TacticalSettingRow", 1
        )[0]
        self.assertIn("@State visualOn: boolean", device_toggle)
        self.assertIn("const next = !this.visualOn", device_toggle)
        self.assertIn("this.visualOn = next", device_toggle)
        self.assertNotIn("const next = !this.isOn", device_toggle)
        self.assertIn("private currentDeviceIsOn(deviceId: string): boolean", device)
        self.assertIn("isOn: this.currentDeviceIsOn(device.id)", device)

    def test_add_device_has_safe_option_and_failure_state_instead_of_render_crash(self):
        source = self.read("pages/AddDevicePage.ets")
        self.assertIn("safeCurrentOption", source)
        self.assertIn("addError", source)
        self.assertIn("try", source)
        self.assertIn("catch", source)
        self.assertNotIn("this.currentOption.label", source)

    def test_utility_buttons_use_centered_content_and_door_has_ack_state(self):
        settings = self.read("pages/SettingsPage.ets")
        device = self.read("pages/DeviceCenterPage.ets")
        self.assertIn(".justifyContent(FlexAlign.Center)", settings)
        self.assertIn("doorActionState", device)
        self.assertIn("passwordConsumed", device)

    def test_theme_speech_is_announced_for_both_committed_directions(self):
        shell = self.read("pages/ControlPanelPage.ets")
        api = self.read("api/chatApi.ets")
        for phrase in ("天光接管，居所进入明昼模式", "夜幕落下，系统转入低光守护"):
            self.assertIn(phrase, shell)
        self.assertIn("themeSpeechCategory", shell)
        self.assertIn("ChatApi.speak(this.themePhrase, 'theme')", shell)
        self.assertIn("category: string = 'default'", api)

    def test_assistant_page_does_not_duplicate_intelligence_settings(self):
        shell = self.read("pages/ControlPanelPage.ets")
        settings = self.read("pages/SettingsPage.ets")
        self.assertNotIn("智能态势", shell)
        self.assertNotIn("intelligenceStrip()", shell)
        self.assertIn("智能与联动", settings)
        self.assertIn("立即检测", settings)

    def test_assistant_has_no_plan_confirmation_panel(self):
        source = self.read("pages/ControlPanelPage.ets")
        self.assertNotIn("是否一键执行这份计划", source)
        self.assertNotIn("是，一键执行", source)
        self.assertNotIn("否，重新方案", source)

    def test_assistant_has_direct_status_check_button_without_typed_confirmation(self):
        source = self.read("pages/SettingsPage.ets")
        api = self.read("api/assistantApi.ets")
        self.assertIn("立即检测", source)
        self.assertIn("runImmediateStatusCheck", source)
        self.assertIn("runStatusCheck", api)

    def test_device_surface_hides_auxiliary_smart_devices_and_exposes_custom_entry(self):
        source = self.read("pages/DeviceCenterPage.ets")
        self.assertIn("hiddenDeviceIds", source)
        self.assertIn("自定义设备", source)
        self.assertIn("AddDevicePage", source)
        self.assertNotIn("'智能设备'", source)

    def test_chat_responses_carry_multiple_live_charts(self):
        source = (ROOT / "backend" / "d6" / "gateway_v6.py").read_text(encoding="utf-8")
        self.assertIn("_chat_chart_data", source)
        self.assertIn('"chartData": self._chat_chart_data', source)

    def test_complex_ai_timeout_covers_primary_and_fallback_latency(self):
        http = self.read("api/http.ets")
        chat = self.read("api/chatApi.ets")
        self.assertIn("READ_TIMEOUT: number = 90000", http)
        self.assertIn("raceTimeout(Http.post('/api/chat/send', body), 95000)", chat)


if __name__ == "__main__":
    unittest.main()
