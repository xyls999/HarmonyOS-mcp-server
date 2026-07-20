import tempfile
import unittest
from pathlib import Path

from backend.d6.automation.automation_service import AutomationService
from backend.d6.automation.popup_outbox import PopupOutbox


class AutomationServiceTests(unittest.TestCase):
    def test_acknowledged_urgent_alarm_does_not_block_the_next_real_alarm(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = PopupOutbox(Path(directory) / "automation.db")
            payload = {"ruleId": "A005", "actions": [{"deviceId": "alarm_01", "action": "on"}]}
            first = outbox.enqueue("alarm", payload, urgent=True, requires_ack=True)
            self.assertIsNotNone(first)
            self.assertTrue(outbox.acknowledge(first))
            second = outbox.enqueue("alarm", payload, urgent=True, requires_ack=True)
            self.assertIsNotNone(second)

    def test_same_source_incident_is_never_requeued_but_a_new_incident_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = PopupOutbox(Path(directory) / "automation.db")
            first_payload = {
                "ruleId": "A004", "sourceIncidentId": 41,
                "actions": [{"deviceId": "alarm_01", "action": "on"}],
            }
            first = outbox.enqueue("alarm", first_payload, urgent=True, requires_ack=True)
            self.assertIsNotNone(first)
            self.assertTrue(outbox.acknowledge(first))
            self.assertIsNone(outbox.enqueue("alarm", first_payload, urgent=True, requires_ack=True))
            self.assertTrue(outbox.has_source_incident(41))

            next_payload = dict(first_payload)
            next_payload["sourceIncidentId"] = 42
            self.assertIsNotNone(outbox.enqueue("alarm", next_payload, urgent=True, requires_ack=True))
            self.assertEqual(outbox.discard_source_incidents([41]), 0)
            self.assertEqual(outbox.discard_source_incidents([42]), 1)
            self.assertFalse(any(item["payload"].get("sourceIncidentId") == 42 for item in outbox.pending()))

    def test_enabled_runtime_set_does_not_duplicate_existing_safety_guard_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AutomationService(Path(directory) / "automation.db")
            enabled = service.enabled_rule_ids(["A006"])
            self.assertEqual(enabled, ["A006"])

    def test_learned_expansion_rules_remain_advisory_and_cannot_auto_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AutomationService(Path(directory) / "automation.db")
            self.assertTrue(service.expander.observe("B021", samples=5, success_rate=1.0, average_score=10.0))
            enabled = service.enabled_rule_ids(["A006", "B021", "A013", "A011"])
            self.assertEqual(enabled, ["A006", "A011"])

    def test_service_emits_popup_context_event_and_chinese_voice_for_executed_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            spoken, events, calls = [], [], []
            service = AutomationService(
                Path(directory) / "automation.db",
                executor=lambda command: calls.append(command) or {"success": True},
                speaker=lambda text, category="default": spoken.append((text, category)),
                context_recorder=lambda *args, **kwargs: events.append((args, kwargs)),
            )
            result = service.evaluate(
                {"sensors": {"humid_01": {"value": 82}}, "devices": {"ac_01": {"power": "off"}}, "capturedAt": "2026-07-19T12:00:00+00:00"},
                enabled_rule_ids=["A001"],
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(result["popups"]), 1)
            self.assertTrue(service.outbox.pending()[0]["requiresAcknowledgement"])
            self.assertTrue(events)
            self.assertTrue(spoken)
            self.assertEqual(spoken[0][1], "automation")
            receipt = result["executed"][0]
            self.assertEqual(receipt["eventTitle"], "客厅湿度偏高")
            self.assertIn("82%", receipt["triggerReason"])
            self.assertEqual(receipt["deviceSummary"], "客厅空调")
            self.assertIn("除湿", receipt["actionSummary"])
            self.assertIn("成功", receipt["resultSummary"])

    def test_alarm_receipt_names_sensor_devices_and_actual_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AutomationService(
                Path(directory) / "automation.db",
                executor=lambda command: {"success": True},
            )
            result = service.evaluate(
                {
                    "sensors": {
                        "smoke_01": {"value": 1, "is_alert": True},
                        "heat_01": {"value": 1680, "is_alert": True},
                    },
                    "devices": {"alarm_01": {"is_on": False}, "fan_02": {"is_on": False}},
                    "capturedAt": "2026-07-20T08:00:00+08:00",
                },
                enabled_rule_ids=["A005"],
            )
            receipt = result["executed"][0]
            self.assertEqual(receipt["eventTitle"], "厨房烟雾与热敏报警")
            self.assertIn("烟雾传感器报警", receipt["triggerReason"])
            self.assertIn("热敏传感器报警", receipt["triggerReason"])
            self.assertEqual(receipt["deviceSummary"], "蜂鸣警报、换气扇")
            self.assertIn("开启蜂鸣警报", receipt["actionSummary"])
            self.assertIn("开启换气扇", receipt["actionSummary"])

    def test_adaptive_guard_incident_is_bridged_to_the_same_popup_and_context_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []
            service = AutomationService(
                Path(directory) / "automation.db",
                context_recorder=lambda *args, **kwargs: events.append((args, kwargs)),
            )
            self.assertTrue(hasattr(service, "publish_guard_incident"))
            result = service.publish_guard_incident({
                "id": 41,
                "ruleKey": "environment_high_humidity",
                "evidence": {"sensor": "humid_01", "value": 79.0, "threshold": 75.0},
                "plannedActions": [{"deviceId": "ac_01", "action": "dry", "params": {"profile": "DRY_26_AUTO"}}],
                "executedActions": [{
                    "action": {"deviceId": "ac_01", "action": "dry", "params": {"profile": "DRY_26_AUTO"}},
                    "result": {"success": True},
                }],
                "status": "open",
                "needsFeedback": True,
                "createdAt": "2026-07-20 08:15:00",
            })
            self.assertTrue(result["published"])
            popup = service.outbox.pending()[0]
            self.assertEqual(popup["payload"]["ruleId"], "A001")
            self.assertIn("79", popup["payload"]["triggerReason"])
            self.assertIn("除湿", popup["payload"]["actionSummary"])
            self.assertEqual(popup["payload"]["triggerSource"], "AI智能联动与调整")
            self.assertEqual(popup["payload"]["triggerTime"], popup["payload"]["capturedAt"])
            self.assertIn("湿度传感器 humid_01", popup["payload"]["evidenceSummary"])
            self.assertIn("79%", popup["payload"]["evidenceSummary"])
            self.assertIn("阈值 75%", popup["payload"]["evidenceSummary"])
            self.assertEqual(popup["payload"]["incidentId"], 41)
            self.assertEqual(len(popup["payload"]["actionDetails"]), 1)
            self.assertEqual(popup["payload"]["actionDetails"][0]["result"], "成功")
            self.assertTrue(events)

    def test_startup_sync_restores_latest_open_guard_incident_to_popup_outbox(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AutomationService(Path(directory) / "automation.db")
            self.assertTrue(hasattr(service, "sync_guard_incidents"))
            result = service.sync_guard_incidents([{
                "id": 88,
                "ruleKey": "kitchen_smoke_or_heat_alarm",
                "evidence": {"alerts": [{"id": "heat_01", "type": "heat", "value": 21}]},
                "executedActions": [{
                    "action": {"deviceId": "alarm_01", "action": "on", "params": {}},
                    "result": {"success": True},
                }],
                "status": "open",
                "needsFeedback": True,
            }])
            self.assertEqual(result["published"], 1)
            self.assertEqual(service.outbox.pending()[0]["payload"]["sourceIncidentId"], 88)
            payload = service.outbox.pending()[0]["payload"]
            self.assertEqual(payload["ruleId"], "A004")
            self.assertIn("热敏传感器报警", payload["triggerReason"])
            self.assertNotIn("烟雾传感器报警", payload["triggerReason"])
            self.assertEqual(payload["triggerSource"], "AI安全警戒与联动")
            self.assertIn("热敏传感器 heat_01", payload["evidenceSummary"])
            self.assertIn("21 毫伏", payload["evidenceSummary"])
            self.assertIn("确认样本 3 次", payload["evidenceSummary"])
            for label in ("触发模式：", "触发时间：", "触发原因：", "实时证据：", "设备：", "具体操作：", "操作结果："):
                self.assertIn(label, payload["description"])
            popup_id = service.outbox.pending()[0]["id"]
            self.assertTrue(service.outbox.acknowledge(popup_id))
            self.assertEqual(service.sync_guard_incidents([{
                "id": 88,
                "ruleKey": "kitchen_smoke_or_heat_alarm",
                "evidence": {"alerts": [{"id": "heat_01", "type": "heat", "value": 21}]},
                "executedActions": [{
                    "action": {"deviceId": "alarm_01", "action": "on", "params": {}},
                    "result": {"success": True},
                }],
                "status": "open",
                "needsFeedback": True,
            }])["published"], 0)


if __name__ == "__main__":
    unittest.main()
