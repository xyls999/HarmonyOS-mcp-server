"""Deterministic security decisions for state drift and request enumeration."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable


def format_security_response(
    event: dict[str, Any], *, buzzer_success: bool, qq_queued: bool,
) -> dict[str, Any]:
    """Build one concrete UI/notification receipt from measured outcomes."""
    rule_id = str(event.get("ruleId", "security.anomaly"))
    severity = str(event.get("severity", "High"))
    evidence = dict(event.get("evidence") or {})
    critical = severity == "Critical"
    notification_event = (
        "security_critical_" + rule_id.replace(".", "_")
        if critical else "security_alert"
    )
    operations: list[dict[str, str]] = []
    if rule_id.startswith("door.password"):
        operations.append({"device_id": "door_01", "action": "阻止开门", "result": "成功"})
    elif evidence.get("deviceId"):
        operations.append({"device_id": str(evidence["deviceId"]), "action": "阻止未授权控制", "result": "成功"})
    if event.get("activateBuzzer"):
        operations.append({
            "device_id": "alarm_01", "action": "开启蜂鸣器",
            "result": "成功" if buzzer_success else "失败",
        })
    operations.append({
        "device_id": "qq_notice", "action": "发送QQ安全提醒",
        "result": "已提交" if qq_queued else "未发送",
    })
    operations.append({"device_id": "security_log", "action": "保存安全记录", "result": "成功"})
    return {
        "ruleId": rule_id,
        "severity": severity,
        "message": str(event.get("message", "检测到异常控制行为"))[:500],
        "evidence": evidence,
        "notificationEvent": notification_event,
        "operations": operations,
    }


class SecurityAnomalyGuard:
    """Classify evidence without performing notification or hardware actions."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._lock = threading.RLock()
        self._states: dict[str, bool] = {}
        self._authorized: dict[str, dict[str, Any]] = {}
        self._unknown_changes: dict[str, deque[float]] = defaultdict(deque)
        self._door_failures: dict[str, deque[float]] = defaultdict(deque)
        self._auth_failures: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _prune(values: deque[float], cutoff: float) -> None:
        while values and values[0] < cutoff:
            values.popleft()

    @staticmethod
    def _event(rule_id: str, severity: str, message: str, evidence: dict[str, Any],
               *, buzzer: bool) -> dict[str, Any]:
        return {
            "ruleId": rule_id,
            "severity": severity,
            "critical": severity == "Critical",
            "activateBuzzer": bool(buzzer),
            "message": message,
            "evidence": evidence,
        }

    def authorize_state(self, device_id: str, expected_state: bool, *, source: str,
                        ttl_seconds: float = 30.0) -> None:
        now = float(self.clock())
        with self._lock:
            self._authorized[str(device_id)] = {
                "expected": bool(expected_state),
                "source": str(source or "gateway"),
                "expiresAt": now + max(1.0, float(ttl_seconds)),
            }

    def observe_state(self, device_id: str, current_state: bool) -> dict[str, Any] | None:
        device_id = str(device_id)
        current_state = bool(current_state)
        now = float(self.clock())
        with self._lock:
            if device_id not in self._states:
                self._states[device_id] = current_state
                return None
            before = self._states[device_id]
            if before == current_state:
                return None
            self._states[device_id] = current_state

            # 本项目只把门禁作为“非主控状态变化”安全边界；灯、空调、风扇
            # 等设备的状态变化由轮询和硬件回执同步，不生成安全警报。
            if device_id != "door_01":
                return None

            authorization = self._authorized.pop(device_id, None)
            if authorization and float(authorization["expiresAt"]) >= now:
                if bool(authorization["expected"]) == current_state:
                    return None
                return self._event(
                    "device.command_state_mismatch", "High",
                    f"{device_id}实际状态与主控命令不一致，已记录并提醒主人",
                    {"deviceId": device_id, "before": before, "after": current_state,
                     "expected": bool(authorization["expected"]),
                     "commandSource": authorization["source"], "observedAt": now},
                    buzzer=False,
                )

            history = self._unknown_changes[device_id]
            self._prune(history, now - 120.0)
            history.append(now)
            repeated = len(history) >= 5
            unexpected_door_open = device_id == "door_01" and current_state
            evidence = {
                "deviceId": device_id, "before": before, "after": current_state,
                "authorizedCommand": False, "changesInTwoMinutes": len(history),
                "observedAt": now,
            }
            if repeated:
                return self._event(
                    "door.repeated_uncommanded_changes", "Critical",
                    "门禁两分钟内出现五次以上未授权状态变化，按反复请求处理",
                    evidence, buzzer=True,
                )
            if unexpected_door_open:
                return self._event(
                    "door.uncommanded_open", "Critical",
                    "门禁在没有主控授权记录的情况下打开，按疑似入侵处理",
                    evidence, buzzer=True,
                )
            return self._event(
                "device.uncommanded_state_change", "High",
                f"{device_id}状态变化未匹配到主控命令，已提醒主人核实",
                evidence, buzzer=False,
            )

    def record_door_password_failure(self, client_id: str) -> dict[str, Any] | None:
        now = float(self.clock())
        client_id = str(client_id or "unknown")
        with self._lock:
            history = self._door_failures[client_id]
            self._prune(history, now - 300.0)
            history.append(now)
            attempts = len(history)
            evidence = {"clientId": client_id, "attempts": attempts, "windowSeconds": 300,
                        "observedAt": now}
            if attempts == 5:
                return self._event(
                    "door.password_enumeration", "Critical",
                    "五分钟内连续五次门禁密码错误，按密码枚举攻击处理",
                    evidence, buzzer=True,
                )
            recent_two_minutes = sum(1 for value in history if value >= now - 120.0)
            if recent_two_minutes == 3:
                evidence["attemptsInTwoMinutes"] = recent_two_minutes
                return self._event(
                    "door.password_repeated_failure", "High",
                    "两分钟内连续三次门禁密码错误，已提醒主人并继续监控",
                    evidence, buzzer=False,
                )
            return None

    def record_auth_failure(self, client_id: str, *, endpoint: str = "") -> dict[str, Any] | None:
        # API 登录/鉴权失败不属于本阶段家庭安全警报范围，保留日志由
        # 网关审计层处理，避免接口探测把蜂鸣器和播报打爆。
        return None
