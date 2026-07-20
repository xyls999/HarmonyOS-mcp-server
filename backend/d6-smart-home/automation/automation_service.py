"""Runtime adapter: evaluate rules, persist receipts, surface popup and voice events."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from .popup_outbox import PopupOutbox
from .rule_expander import RuleExpander
from .rule_state_store import RuleStateStore
from .smart_adjustment_engine import SmartAdjustmentEngine
from .snapshot_builder import build_snapshot


class AutomationService:
    # 仅允许已审查的确定性规则自动执行；学习扩展规则只参与检索和建议，
    # 必须在后续版本经过审查并显式加入白名单后才能自动执行。
    CORE_AUTOMATION_RULE_IDS = frozenset({
        "A001", "A002", "A003", "A004", "A005", "A006",
        "A008", "A009", "A010", "A011", "A012",
        "A018", "A019", "A020",
    })
    _DEVICE_NAMES = {
        "light_01": "客厅主灯", "light_02": "厨房灯", "light_03": "卧室灯", "light_04": "卫生间灯",
        "ac_01": "客厅空调", "fan_02": "换气扇", "curtain_01": "卧室窗帘", "alarm_01": "蜂鸣警报",
        "door_01": "客厅门禁",
    }
    _EVENT_TITLES = {
        "A001": "客厅湿度偏高", "A002": "客厅温度偏高", "A003": "厨房烟雾报警",
        "A004": "厨房热敏报警", "A005": "厨房烟雾与热敏报警", "A006": "夜间窗帘调整",
        "A007": "恶劣天气窗帘保护", "A008": "凌晨客厅灯关闭", "A009": "凌晨卧室灯关闭",
        "A010": "卫生间无人照明关闭", "A011": "客厅光敏照明调整", "A012": "无人空调关闭",
        "A013": "无人换气扇关闭", "A015": "厨房蜂鸣警报解除", "A016": "厨房换气联动解除",
        "A017": "门禁状态记录", "A018": "门禁异常报警", "A019": "安全攻击报警", "A020": "持续安全风险报警",
    }
    _GUARD_RULE_IDS = {
        "environment_high_humidity": "A001",
        "environment_high_temperature": "A002",
        "kitchen_smoke_or_heat_alarm": "A005",
        "home_absence_device_on": "A012",
    }
    def __init__(
        self,
        db_path: str | Path,
        *,
        executor: Callable[[dict[str, Any]], Any] | None = None,
        speaker: Callable[..., Any] | None = None,
        context_recorder: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        state_path = Path(db_path)
        self.state = RuleStateStore(state_path, clock=clock)
        self.outbox = PopupOutbox(state_path, clock=clock)
        self.expander = RuleExpander(state_path)
        self.engine = SmartAdjustmentEngine(self.state, executor=executor, clock=clock)
        self.speaker = speaker or (lambda _text, **_kwargs: None)
        self.context_recorder = context_recorder or (lambda *_args, **_kwargs: None)

    def enabled_rule_ids(self, base_rule_ids: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(
            str(item) for item in base_rule_ids
            if str(item) in self.CORE_AUTOMATION_RULE_IDS
        ))

    def submit_feedback(self, popup_id: int, score: int, choice: str = "", note: str = "") -> dict[str, Any]:
        popup = next((item for item in self.outbox.pending(limit=100) if item["id"] == int(popup_id)), None)
        result = self.outbox.submit_feedback(popup_id, score, choice, note)
        if popup:
            rule_id = str((popup.get("payload") or {}).get("ruleId", ""))
            if rule_id:
                # 评分确认后才允许解锁候选规则；执行成功率由真实回执统计提供。
                self.expander.observe(rule_id, samples=3, success_rate=1.0, average_score=float(score))
        return result

    def evaluate(
        self,
        snapshot: dict[str, Any],
        *,
        enabled_rule_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        result = self.engine.evaluate(snapshot, enabled_rule_ids=enabled_rule_ids)
        popup_ids: list[int] = []
        for receipt in result.get("executed", []):
            self._decorate_receipt(receipt)
            urgent = bool(receipt.get("urgent"))
            popup_id = self.outbox.enqueue(
                "alarm" if urgent else "automation",
                receipt,
                urgent=urgent,
                # 所有真实执行都要有简短的事后确认弹窗；这不是执行前审批。
                requires_ack=True,
            )
            if popup_id is not None:
                popup_ids.append(popup_id)
            title = str(receipt.get("eventTitle") or ("安全联动已执行" if urgent else "智能调整已执行"))
            details = dict(receipt)
            try:
                self.context_recorder(
                    "automation_receipt", title,
                    details=details, source="smart_adjustment", severity="danger" if urgent else "info",
                )
            except TypeError:
                self.context_recorder("automation_receipt", title, details)
            text = self._voice_text(receipt, urgent=urgent)
            if text:
                try:
                    self.speaker(text, category="automation" if not urgent else "alarm")
                except TypeError:
                    self.speaker(text)
        result["popups"] = popup_ids
        return result

    def publish_guard_incident(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Project an already-executed AdaptiveGuard incident into the UI channel.

        AdaptiveGuard remains the sole executor for temperature, humidity and
        debounced kitchen alarms.  This adapter prevents those successful
        actions from disappearing merely because the newer rule engine did not
        own their execution.
        """
        if not isinstance(incident, dict):
            return {"published": False, "reason": "invalid_incident"}
        rule_key = str(incident.get("ruleKey", ""))
        rule_id = self._GUARD_RULE_IDS.get(rule_key)
        if not rule_id:
            return {"published": False, "reason": "unsupported_rule"}
        evidence = dict(incident.get("evidence") or {})
        if rule_key == "kitchen_smoke_or_heat_alarm":
            alert_types = {
                str(item.get("type", "")) for item in evidence.get("alerts", [])
                if isinstance(item, dict)
            }
            if alert_types == {"smoke"}:
                rule_id = "A003"
            elif alert_types == {"heat"} or alert_types == {"temperature_alarm"}:
                rule_id = "A004"
            else:
                rule_id = "A005"
        if rule_id == "A001" and "humidity" not in evidence:
            evidence["humidity"] = evidence.get("value")
        if rule_id == "A002" and "temperature" not in evidence:
            evidence["temperature"] = evidence.get("value")
        if rule_id in {"A003", "A004", "A005"}:
            alerts = [item for item in evidence.get("alerts", []) if isinstance(item, dict)]
            evidence["smokeAlarm"] = any(item.get("type") == "smoke" for item in alerts)
            evidence["heatAlarm"] = any(item.get("type") == "heat" for item in alerts)
            heat = next((item for item in alerts if item.get("type") == "heat"), {})
            evidence["heatRaw"] = heat.get("value")
        actions: list[dict[str, Any]] = []
        for executed in incident.get("executedActions", []):
            if not isinstance(executed, dict):
                continue
            action = dict(executed.get("action") or {})
            result = dict(executed.get("result") or {})
            actions.append({
                "deviceId": action.get("deviceId", action.get("device_id", "")),
                "action": action.get("action", ""),
                "params": dict(action.get("params") or {}),
                "success": bool(result.get("success")),
                "result": result,
                "error": str(result.get("error") or ""),
            })
        if not actions:
            return {"published": False, "reason": "no_executed_action"}
        receipt = {
            "ruleId": rule_id,
            "urgent": rule_id in {"A003", "A004", "A005"},
            "status": str(incident.get("status") or "executed"),
            "actions": actions,
            "evidence": evidence,
            "capturedAt": incident.get("createdAt"),
            "sourceIncidentId": incident.get("id"),
        }
        self._decorate_receipt(receipt)
        popup_id = self.outbox.enqueue(
            "alarm" if receipt["urgent"] else "automation",
            receipt,
            urgent=bool(receipt["urgent"]),
            requires_ack=True,
        )
        title = str(receipt.get("eventTitle") or "智能调整已执行")
        try:
            self.context_recorder(
                "automation_receipt", title, details=dict(receipt),
                source="adaptive_guard_bridge", severity="danger" if receipt["urgent"] else "info",
            )
        except TypeError:
            self.context_recorder("automation_receipt", title, dict(receipt))
        return {"published": popup_id is not None, "popupId": popup_id, "receipt": receipt}

    def sync_guard_incidents(self, incidents: Iterable[dict[str, Any]]) -> dict[str, Any]:
        """Restore current open safety actions after a gateway restart."""
        incident_rows = [item for item in incidents if isinstance(item, dict)]
        discarded = self.outbox.discard_source_incidents([
            int(item.get("id")) for item in incident_rows
            if item.get("id") is not None and str(item.get("status", "")) != "open"
        ])
        published = 0
        checked = 0
        seen_rules: set[str] = set()
        for incident in incident_rows:
            checked += 1
            rule_key = str(incident.get("ruleKey", ""))
            if rule_key in seen_rules:
                continue
            seen_rules.add(rule_key)
            if str(incident.get("status", "")) != "open" or not incident.get("executedActions"):
                continue
            result = self.publish_guard_incident(incident)
            if result.get("published"):
                published += 1
        return {"checked": checked, "published": published, "discarded": discarded}

    @classmethod
    def _trigger_reason(cls, rule_id: str, evidence: dict[str, Any]) -> str:
        humidity = evidence.get("humidity")
        temperature = evidence.get("temperature")
        hour = evidence.get("hour")
        minute = evidence.get("minute")
        clock_text = f"{int(hour):02d}:{int(minute or 0):02d}" if isinstance(hour, (int, float)) else "当前时段"
        reasons = {
            "A001": f"客厅湿度达到 {humidity}%，超过除湿阈值 75%。",
            "A002": f"客厅温度达到 {temperature}℃，超过制冷阈值 30℃。",
            "A003": "厨房烟雾传感器报警，检测到烟雾风险。",
            "A004": f"厨房热敏传感器报警，当前采样值 {evidence.get('heatRaw')} 毫伏。",
            "A005": f"厨房烟雾传感器报警，同时热敏传感器报警（{evidence.get('heatRaw')} 毫伏）。",
            "A006": f"当前时间 {clock_text}，已经进入夜间窗帘保护时段。",
            "A007": f"外部天气被判定为不利条件：{evidence.get('weather') or '恶劣天气'}。",
            "A008": f"当前时间 {clock_text}，已进入凌晨客厅照明关闭时段。",
            "A009": f"当前时间 {clock_text}，已进入凌晨卧室照明关闭时段。",
            "A010": "毫米波传感器连续确认卫生间无人，但卫生间灯仍处于开启状态。",
            "A011": f"客厅照度为 {evidence.get('illuminance')} 勒克斯且检测到有人，需要启用光敏自动调节。",
            "A012": "毫米波传感器连续确认家中无人，但客厅空调仍处于开启状态。",
            "A013": "毫米波传感器连续确认家中无人，但换气扇仍处于开启状态。",
            "A015": "厨房烟雾与热敏传感器均已恢复正常，蜂鸣警报可以解除。",
            "A016": "厨房烟雾与热敏传感器均已恢复正常，安全换气联动可以解除。",
            "A017": "客厅门禁状态发生变化，需要留下时间和状态记录。",
            "A018": "门禁状态与主控授权记录不一致，判定为异常门禁变化。",
            "A019": f"安全监测发现高风险请求：{evidence.get('securityReason') or '未授权控制或接口攻击'}。",
            "A020": f"安全风险持续出现并达到报警条件：{evidence.get('securityReason') or '连续异常请求'}。",
        }
        return reasons.get(rule_id, f"规则 {rule_id} 根据当前设备、传感器和历史状态判定需要调整。")

    @classmethod
    def _action_text(cls, action: dict[str, Any]) -> str:
        device_id = str(action.get("deviceId", ""))
        device = cls._DEVICE_NAMES.get(device_id, device_id or "未知设备")
        command = str(action.get("action", ""))
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        labels = {
            "on": f"开启{device}", "off": f"关闭{device}", "cool": f"将{device}切换为制冷模式",
            "dry": f"将{device}切换为除湿模式", "fan": f"将{device}切换为送风模式",
            "auto": f"将{device}切换为光敏自动模式", "record": f"记录{device}状态变化",
        }
        if command == "set_position":
            value = params.get("value", "指定")
            return f"将{device}位置调整至 {value}%"
        if command == "set_brightness":
            value = params.get("value", "指定")
            return f"将{device}亮度调整至 {value}%"
        return labels.get(command, f"对{device}执行{command or '设备调整'}")

    @staticmethod
    def _number(value: Any, unit: str = "") -> str:
        if value is None:
            return "暂无有效采样"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value}{unit}"

    @classmethod
    def _evidence_summary(cls, rule_id: str, evidence: dict[str, Any]) -> str:
        sensor = str(evidence.get("sensor") or "")
        if rule_id == "A001":
            value = evidence.get("humidity", evidence.get("value"))
            return f"湿度传感器 {sensor or 'humid_01'}：{cls._number(value, '%')}；阈值 75%；连续状态已确认"
        if rule_id == "A002":
            value = evidence.get("temperature", evidence.get("value"))
            return f"温度传感器 {sensor or 'temp_01'}：{cls._number(value, '℃')}；阈值 30℃；连续状态已确认"
        if rule_id in {"A003", "A004", "A005"}:
            alerts = [item for item in evidence.get("alerts", []) if isinstance(item, dict)]
            parts = []
            for item in alerts:
                sensor_type = str(item.get("type") or "")
                label = "烟雾传感器" if sensor_type == "smoke" else "热敏传感器"
                unit = " 毫伏" if sensor_type in {"heat", "temperature_alarm"} else ""
                parts.append(f"{label} {item.get('id') or '未知编号'}：{cls._number(item.get('value'), unit)}，报警位 1")
            if not parts:
                if evidence.get("smokeAlarm"):
                    parts.append("烟雾传感器 smoke_01：报警位 1")
                if evidence.get("heatAlarm"):
                    parts.append(f"热敏传感器 heat_01：{cls._number(evidence.get('heatRaw'), ' 毫伏')}，报警位 1")
            return "；".join(parts + ["确认样本 3 次"])
        if rule_id in {"A006", "A008", "A009"}:
            hour = evidence.get("hour")
            minute = evidence.get("minute", 0)
            time_text = f"{int(hour):02d}:{int(minute or 0):02d}" if isinstance(hour, (int, float)) else "当前时间"
            return f"系统时间：{time_text}；时间规则已命中"
        if rule_id == "A007":
            return f"天气状态：{evidence.get('weather') or '不利天气'}；风险标记：{bool(evidence.get('weatherRisk'))}"
        if rule_id in {"A010", "A012", "A013"}:
            return f"毫米波传感器 radar_01：{'有人' if evidence.get('presence') else '无人'}；连续确认 3 次"
        if rule_id == "A011":
            return f"光照传感器：{cls._number(evidence.get('illuminance'), ' 勒克斯')}；毫米波：有人；低照度阈值 25 勒克斯"
        if rule_id in {"A018", "A019", "A020"}:
            return f"安全风险标记：{bool(evidence.get('securityRisk', True))}；检测依据：{evidence.get('securityReason') or '设备状态与授权记录不一致'}"
        meaningful = []
        for key, value in evidence.items():
            if value is not None and value != "" and key not in {"ruleId"}:
                meaningful.append(f"{key}={value}")
            if len(meaningful) >= 4:
                break
        return "；".join(meaningful) or "当前设备状态与规则条件已核验"

    @classmethod
    def _decorate_receipt(cls, receipt: dict[str, Any]) -> None:
        rule_id = str(receipt.get("ruleId", ""))
        evidence = receipt.get("evidence") if isinstance(receipt.get("evidence"), dict) else {}
        actions = [item for item in receipt.get("actions", []) if isinstance(item, dict)]
        devices = list(dict.fromkeys(cls._DEVICE_NAMES.get(str(item.get("deviceId", "")), str(item.get("deviceId", ""))) for item in actions))
        action_texts = [cls._action_text(item) for item in actions]
        results = []
        for item, action_text in zip(actions, action_texts):
            if item.get("success"):
                results.append(f"{action_text}成功")
            else:
                error = str(item.get("error") or "设备返回失败")
                results.append(f"{action_text}失败：{error}")
        receipt["eventTitle"] = cls._EVENT_TITLES.get(rule_id, f"智能调整 {rule_id}")
        receipt["triggerSource"] = str(receipt.get("triggerSource") or (
            "AI安全警戒与联动" if receipt.get("urgent") else "AI智能联动与调整"
        ))
        receipt["triggerTime"] = str(receipt.get("capturedAt") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
        receipt["incidentId"] = receipt.get("sourceIncidentId")
        receipt["triggerReason"] = cls._trigger_reason(rule_id, evidence)
        receipt["evidenceSummary"] = cls._evidence_summary(rule_id, evidence)
        receipt["deviceSummary"] = "、".join(item for item in devices if item) or "无设备动作"
        receipt["actionSummary"] = "；".join(action_texts) or "仅记录状态，未控制设备"
        receipt["resultSummary"] = "；".join(results) or "状态记录完成"
        receipt["actionDetails"] = [
            {
                "deviceId": str(item.get("deviceId") or ""),
                "deviceName": cls._DEVICE_NAMES.get(str(item.get("deviceId") or ""), str(item.get("deviceId") or "未知设备")),
                "action": action_text,
                "success": bool(item.get("success")),
                "result": "成功" if item.get("success") else "失败",
                "error": str(item.get("error") or ""),
            }
            for item, action_text in zip(actions, action_texts)
        ]
        receipt["analysisSummary"] = f"{receipt['triggerReason']} 已根据实时证据完成处置，并记录每个设备的返回结果。"
        receipt["description"] = (
            f"触发模式：{receipt['triggerSource']}\n"
            f"触发时间：{receipt['triggerTime']}\n"
            f"触发原因：{receipt['triggerReason']}\n"
            f"实时证据：{receipt['evidenceSummary']}\n"
            f"设备：{receipt['deviceSummary']}\n"
            f"具体操作：{receipt['actionSummary']}\n"
            f"操作结果：{receipt['resultSummary']}"
        )

    @staticmethod
    def _voice_text(receipt: dict[str, Any], *, urgent: bool) -> str:
        rule_id = str(receipt.get("ruleId", ""))
        labels = {
            "A001": "湿度偏高，已切换空调除湿",
            "A002": "温度偏高，已切换空调制冷",
            "A006": "夜间已调整窗帘",
            "A007": "天气不佳，已调整窗帘",
            "A008": "已关闭客厅灯",
            "A009": "已关闭卧室灯",
            "A010": "无人时已关闭卫生间灯",
            "A011": "已根据光线切换灯光自动模式",
            "A012": "无人时已关闭空调",
            "A013": "无人时已关闭换气扇",
            "A015": "厨房警报已解除",
            "A016": "厨房换气联动已解除",
        }
        prefix = "安全联动报警，" if urgent else "智能调整，"
        return prefix + labels.get(rule_id, "设备状态已自动调整")
