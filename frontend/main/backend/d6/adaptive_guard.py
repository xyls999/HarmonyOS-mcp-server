"""Persistent, feedback-driven guard automation for the A9 gateway."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    from parallel_device_executor import execute_device_commands
except ModuleNotFoundError:
    from backend.d6.parallel_device_executor import execute_device_commands


_CST = timezone(timedelta(hours=8))
_SENSITIVE_KEYS = {"password", "passcode", "token", "secret", "authorization", "api_key", "apikey"}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "activeAiEnabled": True,
    "feedbackAutomation": {"enabled": True, "minSamples": 3, "minAverageScore": 8.0},
    "planConfirmation": {"enabled": False},
    "cooldownSeconds": 600,
    "startupGraceSeconds": 20,
    "highTemperature": {"enabled": True, "on": 30.0, "off": 27.0, "profile": "COOL_26_AUTO", "fallbackProfile": "FAN_26_AUTO"},
    "highHumidity": {"enabled": True, "on": 75.0, "off": 65.0, "profile": "DRY_26_AUTO", "fallbackProfile": "FAN_26_AUTO"},
    "kitchenAlarm": {
        "enabled": True,
        "buzzer": True,
        "exhaust": True,
        "clearOnRecovery": True,
        "confirmSamples": 3,
        "recoverySamples": 5,
    },
    "doorMonitor": {"enabled": True, "ttsOnOpen": True, "ttsOnClose": True, "qqOnOpen": True},
    # 离线读数仍写入日志与上下文，但默认不生成重复警戒事件或语音。
    "offlineMonitor": {"enabled": False},
    # 仅当快照中存在在线且明确返回无人状态的毫米波/存在传感器时启用；
    # 缺少传感器时绝不根据网络离线或环境变量推断“家中无人”。
    "absenceMonitor": {"enabled": True, "minSamples": 3, "cooldownSeconds": 600},
}


def _now_text() -> str:
    return datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).lower())
            result[key] = "<redacted>" if normalized in _SENSITIVE_KEYS else _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"(?i)(bearer\s+|sk-)[A-Za-z0-9_.-]{12,}",
            lambda match: match.group(1) + "<redacted>",
            value,
        )
    return value


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    result = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    result.update(chinese[index:index + 2] for index in range(max(0, len(chinese) - 1)))
    return {item for item in result if item}


class AdaptiveGuard:
    def __init__(
        self,
        db_path: str | Path,
        *,
        executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        speaker: Callable[[str], None] | None = None,
        notifier: Callable[..., Any] | None = None,
        context_recorder: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.executor = executor or (lambda _action: {"success": False, "error": "executor unavailable"})
        self.speaker = speaker or (lambda _text: None)
        self.notifier = notifier or (lambda *_args, **_kwargs: None)
        self.context_recorder = context_recorder or (lambda *_args, **_kwargs: None)
        self.clock = clock
        self._state_lock = threading.RLock()
        self._active_signatures: set[str] = set()
        self._reasserted_signatures: set[str] = set()
        self._started_at = self.clock()
        self._kitchen_alarm_streak = 0
        self._kitchen_clear_streak = 0
        self._kitchen_confirmed = False
        self._absence_streak = 0
        self.migrate()
        self.config = self._load_config()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def migrate(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS adaptive_guard_config (
                    config_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guard_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signature TEXT NOT NULL,
                    rule_key TEXT NOT NULL,
                    room TEXT NOT NULL DEFAULT '',
                    guard_level INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    planned_actions_json TEXT NOT NULL,
                    executed_actions_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    needs_feedback INTEGER NOT NULL DEFAULT 0,
                    feedback_received INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_guard_incident_signature ON guard_incidents(signature, created_ts DESC);
                CREATE INDEX IF NOT EXISTS idx_guard_incident_feedback ON guard_incidents(needs_feedback, feedback_received, id DESC);
                CREATE TABLE IF NOT EXISTS guard_feedback (
                    incident_id INTEGER PRIMARY KEY,
                    score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 10),
                    better_action TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(incident_id) REFERENCES guard_incidents(id)
                );
                CREATE TABLE IF NOT EXISTS guard_learning (
                    signature TEXT PRIMARY KEY,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    average_score REAL NOT NULL DEFAULT 0,
                    guidance TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_telemetry_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    page TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_app_telemetry_time ON app_telemetry_events(id DESC);
            """)
            # Historical builds treated the cooldown expiry as permission to
            # recreate an incident even while its physical condition remained
            # active.  Collapse those rows once, keeping the first occurrence
            # as the canonical continuous abnormal interval.
            duplicate_groups = connection.execute(
                "SELECT signature,MIN(id) AS canonical_id FROM guard_incidents "
                "WHERE status='open' GROUP BY signature HAVING COUNT(*)>1"
            ).fetchall()
            for group in duplicate_groups:
                connection.execute(
                    "UPDATE guard_incidents SET status='superseded',needs_feedback=0,feedback_received=1,"
                    "resolved_at=COALESCE(resolved_at,?) WHERE signature=? AND status='open' AND id<>?",
                    (_now_text(), group["signature"], int(group["canonical_id"])),
                )

    def _load_config(self) -> dict[str, Any]:
        config = json.loads(json.dumps(DEFAULT_CONFIG))
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT config_key,value_json FROM adaptive_guard_config").fetchall()
        for row in rows:
            try:
                value = json.loads(row["value_json"])
            except (TypeError, ValueError):
                continue
            if isinstance(config.get(row["config_key"]), dict) and isinstance(value, dict):
                config[row["config_key"]].update(value)
            else:
                config[row["config_key"]] = value
        return config

    def get_config(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.config))

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(updates, dict):
            raise ValueError("config must be an object")
        allowed = set(DEFAULT_CONFIG)
        previous_enabled = bool(self.config.get("enabled", True))
        previous_kitchen_enabled = bool(self.config.get("kitchenAlarm", {}).get("enabled", True))
        changed = {}
        for key, value in updates.items():
            if key not in allowed:
                continue
            if isinstance(DEFAULT_CONFIG[key], dict):
                if not isinstance(value, dict):
                    raise ValueError(f"{key} must be an object")
                self.config[key].update(value)
            else:
                if key in ("enabled", "activeAiEnabled") and not isinstance(value, bool):
                    raise ValueError(f"{key} must be boolean")
                self.config[key] = value
            changed[key] = self.config[key]
        with closing(self._connect()) as connection:
            for key in changed:
                connection.execute(
                    "INSERT INTO adaptive_guard_config(config_key,value_json,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(config_key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                    (key, _json(changed[key]), _now_text()),
                )
        current_enabled = bool(self.config.get("enabled", True))
        current_kitchen_enabled = bool(self.config.get("kitchenAlarm", {}).get("enabled", True))
        if previous_enabled and not current_enabled:
            self._resolve_signatures_silently(set(self._active_signatures))
            self._reset_kitchen_state()
        elif previous_kitchen_enabled and not current_kitchen_enabled:
            self._resolve_signatures_silently({"kitchen:alarm"})
            self._reset_kitchen_state()
        if current_enabled != previous_enabled:
            self.speaker("联动自动管理已开启" if current_enabled else "联动自动管理已关闭")
        return self.get_config()

    def _reset_kitchen_state(self) -> None:
        self._kitchen_alarm_streak = 0
        self._kitchen_clear_streak = 0
        self._kitchen_confirmed = False

    def _resolve_signatures_silently(self, signatures: set[str]) -> None:
        if not signatures:
            return
        with closing(self._connect()) as connection:
            for signature in signatures:
                connection.execute(
                    "UPDATE guard_incidents SET status='resolved',resolved_at=? "
                    "WHERE signature=? AND status='open'",
                    (_now_text(), signature),
                )
        self._active_signatures.difference_update(signatures)

    def _confirmed_kitchen_alarm(self, raw_alert: bool) -> bool:
        if self.clock() - self._started_at < float(self.config.get("startupGraceSeconds", 20)):
            self._reset_kitchen_state()
            return False
        config = self.config.get("kitchenAlarm", {})
        if raw_alert:
            self._kitchen_alarm_streak += 1
            self._kitchen_clear_streak = 0
            if self._kitchen_alarm_streak >= max(1, int(config.get("confirmSamples", 3))):
                self._kitchen_confirmed = True
        else:
            self._kitchen_clear_streak += 1
            self._kitchen_alarm_streak = 0
            if self._kitchen_clear_streak >= max(1, int(config.get("recoverySamples", 5))):
                self._kitchen_confirmed = False
        return self._kitchen_confirmed

    @staticmethod
    def _sensor_value(sensor: dict[str, Any]) -> float | None:
        value = sensor.get("value")
        if isinstance(value, dict):
            value = value.get("value")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _has_open_signature(self, signature: str) -> bool:
        """Return whether this exact abnormal condition is still unresolved.

        An open incident represents one continuous abnormal interval.  Its age
        must never make it eligible to fire again; only the recovery state
        machine may close it and allow a later rising edge to create a new one.
        """
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id FROM guard_incidents WHERE signature=? AND status='open' ORDER BY id DESC LIMIT 1",
                (signature,),
            ).fetchone()
        return row is not None

    def _execute_plan(self, primary: list[dict[str, Any]], fallback: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        batch = execute_device_commands(primary, self.executor, max_workers=4)
        results = []
        failed = []
        for action, item in zip(primary, batch["results"]):
            response = item.get("result")
            if not isinstance(response, dict):
                response = {"success": False, "error": item.get("error", "设备执行失败")}
            results.append({"action": action, "result": _redact(response)})
            if fallback is not None and not bool(response.get("success")):
                failed.append(dict(fallback))
        if failed:
            fallback_batch = execute_device_commands(failed, self.executor, max_workers=4)
            for action, item in zip(failed, fallback_batch["results"]):
                response = item.get("result")
                if not isinstance(response, dict):
                    response = {"success": False, "error": item.get("error", "保底设备执行失败")}
                results.append({"action": action, "result": _redact(response), "fallback": True})
        return results

    def _record_incident(
        self,
        *,
        signature: str,
        rule_key: str,
        room: str,
        guard_level: int,
        evidence: dict[str, Any],
        actions: list[dict[str, Any]],
        fallback: dict[str, Any] | None = None,
        message: str = "",
        notice: tuple[str, str, str] | None = None,
    ) -> dict[str, Any] | None:
        # SQLite is the durable source of truth.  The in-memory set is only a
        # snapshot/recovery aid and may be stale after a restart or migration;
        # letting it suppress inserts can hide a genuine active alarm.
        if self._has_open_signature(signature):
            return None
        self._active_signatures.add(signature)
        active = bool(self.config.get("enabled", True))
        executed = self._execute_plan(actions, fallback) if active else []
        changed = any(
            bool(item.get("result", {}).get("success"))
            and item.get("result", {}).get("state_changed", True) is not False
            for item in executed
        )
        if active and message:
            self.speaker(message)
        if active and notice:
            self.notifier(notice[0], notice[1], notice[2], {"signature": signature, "guardLevel": guard_level})
        mode = "active" if active else "passive"
        now_text = _now_text()
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "INSERT INTO guard_incidents(signature,rule_key,room,guard_level,mode,evidence_json,"
                "planned_actions_json,executed_actions_json,status,needs_feedback,created_at,created_ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    signature, rule_key, room, max(0, min(10, int(guard_level))), mode,
                    _json(_redact(evidence)), _json(_redact(actions)), _json(executed), "open",
                    1 if changed else 0, now_text, float(self.clock()),
                ),
            )
            incident_id = int(cursor.lastrowid)
        summary = f"Guard incident {incident_id}: {rule_key} level={guard_level} mode={mode}"
        self.context_recorder(
            "guard_incident", summary,
            details={"incidentId": incident_id, "signature": signature, "ruleKey": rule_key, "guardLevel": guard_level, "mode": mode},
            source="adaptive_guard", severity="critical" if guard_level >= 9 else "warning" if guard_level >= 6 else "info",
        )
        return {
            "id": incident_id, "signature": signature, "ruleKey": rule_key, "room": room,
            "guardLevel": guard_level, "mode": mode, "needsFeedback": changed,
            "evidence": _redact(evidence), "plannedActions": actions, "executedActions": executed,
            "createdAt": now_text,
        }

    def _recover_missing(self, active_now: set[str]) -> None:
        resolved = self._active_signatures - active_now
        if not resolved:
            return
        for signature in resolved:
            self._reasserted_signatures.discard(signature)
            if (
                signature == "kitchen:alarm"
                and bool(self.config.get("enabled", True))
                and bool(self.config["kitchenAlarm"].get("enabled", True))
                and bool(self.config["kitchenAlarm"].get("clearOnRecovery", True))
            ):
                self._execute_plan([
                    {"deviceId": "alarm_01", "action": "off", "params": {}},
                    {"deviceId": "fan_02", "action": "off", "params": {}},
                ])
                self.speaker("厨房报警已恢复，警报和换气扇已关闭")
            with closing(self._connect()) as connection:
                connection.execute(
                    "UPDATE guard_incidents SET status='resolved',resolved_at=? "
                    "WHERE id=(SELECT id FROM guard_incidents WHERE signature=? AND status='open' ORDER BY id DESC LIMIT 1)",
                    (_now_text(), signature),
                )
            self.context_recorder(
                "guard_recovery", f"Guard signature recovered: {signature}",
                details={"signature": signature}, source="adaptive_guard", severity="info",
            )
        self._active_signatures = set(active_now)

    def process_snapshot(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate one complete sensor snapshot atomically.

        The gateway has polling and datagram ingress threads. Serializing the
        state transition prevents duplicate incidents and duplicate hardware
        actions when both threads report the same alarm concurrently.
        """
        with self._state_lock:
            return self._process_snapshot_locked(snapshot)

    def _process_snapshot_locked(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        if not bool(self.config.get("enabled", True)):
            self._active_signatures.clear()
            self._reset_kitchen_state()
            self._absence_streak = 0
            return []
        sensors = snapshot.get("sensors", []) if isinstance(snapshot, dict) else []
        devices = snapshot.get("devices", []) if isinstance(snapshot, dict) else []
        incidents = []
        active_now: set[str] = set()
        kitchen_alerts = []
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            sensor_type = str(sensor.get("type", "")).lower()
            room = str(sensor.get("room", ""))
            online = sensor.get("online", True) is not False
            value = self._sensor_value(sensor)
            if not online and self.config["offlineMonitor"].get("enabled", True):
                signature = f"offline:{sensor.get('id', sensor_type)}"
                active_now.add(signature)
                incident = self._record_incident(
                    signature=signature, rule_key="sensor_offline", room=room, guard_level=4,
                    evidence={"sensor": sensor.get("id"), "type": sensor_type, "online": False}, actions=[],
                )
                if incident:
                    incidents.append(incident)
                continue
            if not online or value is None:
                continue
            if sensor_type in ("smoke", "heat", "temperature_alarm") and room == "厨房" and bool(sensor.get("isAlert", False)):
                kitchen_alerts.append({"id": sensor.get("id"), "type": sensor_type, "value": value})
                continue
            if room not in ("客厅", "卧室", "living_room", "bedroom"):
                continue
            if sensor_type in ("temperature", "temp") and self.config["highTemperature"].get("enabled", True):
                threshold = float(self.config["highTemperature"].get("on", 30))
                if value >= threshold:
                    signature = f"temperature:{room}"
                    active_now.add(signature)
                    profile = self.config["highTemperature"].get("profile", "COOL_26_AUTO")
                    fallback_profile = self.config["highTemperature"].get("fallbackProfile", "FAN_26_AUTO")
                    incident = self._record_incident(
                        signature=signature, rule_key="environment_high_temperature", room=room, guard_level=7,
                        evidence={"sensor": sensor.get("id"), "type": sensor_type, "room": room, "value": value, "threshold": threshold},
                        actions=[{"deviceId": "ac_01", "action": "cool", "params": {"profile": profile}}],
                        fallback={"deviceId": "ac_01", "action": "fan", "params": {"profile": fallback_profile}},
                        message=f"{room}温度{value:g}度，已启动空调调节",
                    )
                    if incident:
                        incidents.append(incident)
            if sensor_type in ("humidity", "humid") and self.config["highHumidity"].get("enabled", True):
                threshold = float(self.config["highHumidity"].get("on", 75))
                if value >= threshold:
                    signature = f"humidity:{room}"
                    active_now.add(signature)
                    profile = self.config["highHumidity"].get("profile", "DRY_26_AUTO")
                    fallback_profile = self.config["highHumidity"].get("fallbackProfile", "FAN_26_AUTO")
                    incident = self._record_incident(
                        signature=signature, rule_key="environment_high_humidity", room=room, guard_level=6,
                        evidence={"sensor": sensor.get("id"), "type": sensor_type, "room": room, "value": value, "threshold": threshold},
                        actions=[{"deviceId": "ac_01", "action": "dry", "params": {"profile": profile}}],
                        fallback={"deviceId": "ac_01", "action": "fan", "params": {"profile": fallback_profile}},
                        message=f"{room}湿度{value:g}%，已启动空调调节",
                    )
                    if incident:
                        incidents.append(incident)
        kitchen_enabled = bool(self.config["kitchenAlarm"].get("enabled", True))
        if not kitchen_enabled:
            self._reset_kitchen_state()
        kitchen_confirmed = self._confirmed_kitchen_alarm(bool(kitchen_alerts)) if kitchen_enabled else False
        if kitchen_confirmed:
            signature = "kitchen:alarm"
            active_now.add(signature)
            actions = []
            if self.config["kitchenAlarm"].get("buzzer", True):
                actions.append({"deviceId": "alarm_01", "action": "on", "params": {}})
            if self.config["kitchenAlarm"].get("exhaust", True):
                actions.append({"deviceId": "fan_02", "action": "on", "params": {}})
            incident = self._record_incident(
                signature=signature, rule_key="kitchen_smoke_or_heat_alarm", room="厨房", guard_level=10,
                evidence={"alerts": kitchen_alerts}, actions=actions,
                message="厨房烟雾或温度报警，已启动蜂鸣器和换气扇",
                notice=("kitchen_alarm", "厨房安全报警", "检测到烟雾或温度报警，已执行本地安全联动"),
            )
            if incident:
                incidents.append(incident)
            elif signature not in self._reasserted_signatures:
                # A persisted open incident can survive a gateway restart while
                # its actuator state does not. Reassert only devices that are
                # online and currently reported off, once per process.
                current = {
                    str(device.get("id", "")): device for device in devices
                    if isinstance(device, dict)
                }
                missing = []
                for action in actions:
                    state = current.get(str(action.get("deviceId", "")))
                    if state and state.get("online") is not False and state.get("isOn") is False:
                        missing.append(action)
                if missing:
                    self._execute_plan(missing)
                self._active_signatures.add(signature)
                self._reasserted_signatures.add(signature)
        absence_config = self.config.get("absenceMonitor", {})
        presence_sensors = [sensor for sensor in sensors if isinstance(sensor, dict)
                            and str(sensor.get("type", "")).lower() in {"presence", "radar_presence", "mmwave"}
                            and sensor.get("online") is not False]
        no_person = bool(presence_sensors) and all(
            sensor.get("presence") is False or float(sensor.get("value", 1) or 0) == 0
            for sensor in presence_sensors
        )
        active_devices = [device for device in devices if isinstance(device, dict)
                          and device.get("online") is not False and device.get("isOn") is True
                          and str(device.get("id", "")) in {"ac_01", "fan_02"}
                          # Active kitchen safety ventilation always outranks
                          # absence-based energy saving.
                          and not (str(device.get("id", "")) == "fan_02" and bool(kitchen_alerts))]
        if bool(absence_config.get("enabled", True)) and no_person and active_devices:
            self._absence_streak += 1
            if self._absence_streak >= max(1, int(absence_config.get("minSamples", 3))):
                for device in active_devices:
                    signature = f"absence:{device.get('id')}"
                    active_now.add(signature)
                    incident = self._record_incident(
                        signature=signature, rule_key="home_absence_device_on", room=str(device.get("room", "")),
                        guard_level=6,
                        evidence={"presenceSensorIds": [sensor.get("id") for sensor in presence_sensors],
                                  "presence": False, "deviceId": device.get("id"), "deviceWasOn": True},
                        actions=[{"deviceId": device.get("id"), "action": "off", "params": {}}],
                        message=f"毫米波连续检测无人，{device.get('name', device.get('id'))}仍开启，已自动关闭",
                        notice=("home_absence_device_on", "无人状态设备未关闭", f"检测到无人且{device.get('name', device.get('id'))}仍开启，已自动关闭"),
                    )
                    if incident:
                        incidents.append(incident)
        else:
            self._absence_streak = 0
        self._recover_missing(active_now)
        return incidents

    def record_door_event(self, is_open: bool, event_data: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = self.config["doorMonitor"]
        signature = f"door:{'open' if is_open else 'closed'}:{int(self.clock())}"
        incident = self._record_incident(
            signature=signature, rule_key="door_event_monitor", room="客厅",
            guard_level=7 if is_open else 2,
            evidence={"isOpen": bool(is_open), "eventData": _redact(event_data or {})},
            actions=[],
        )
        if cfg.get("enabled", True):
            if is_open and cfg.get("ttsOnOpen", True):
                self.speaker("门已打开")
            elif not is_open and cfg.get("ttsOnClose", True):
                self.speaker("门已关闭")
            if is_open and cfg.get("qqOnOpen", True):
                self.notifier("door_open", "门禁打开提醒", "检测到客厅门禁已打开", {"incidentId": incident["id"] if incident else None})
        return incident or {
            "id": 0, "signature": signature, "ruleKey": "door_event_monitor", "room": "客厅",
            "guardLevel": 7 if is_open else 2, "mode": "passive", "needsFeedback": False,
        }

    def submit_feedback(self, incident_id: int, score: int, better_action: str = "", notes: str = "") -> dict[str, Any]:
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 10:
            raise ValueError("score must be an integer from 0 to 10")
        better_action = str(better_action).strip()[:2000]
        notes = str(notes).strip()[:2000]
        with closing(self._connect()) as connection:
            incident = connection.execute(
                "SELECT id,signature,rule_key FROM guard_incidents WHERE id=?", (int(incident_id),)
            ).fetchone()
            if not incident:
                raise ValueError("incident not found")
            now = _now_text()
            connection.execute(
                "INSERT INTO guard_feedback(incident_id,score,better_action,notes,created_at,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(incident_id) DO UPDATE SET score=excluded.score,better_action=excluded.better_action,"
                "notes=excluded.notes,updated_at=excluded.updated_at",
                (int(incident_id), score, better_action, notes, now, now),
            )
            connection.execute("UPDATE guard_incidents SET feedback_received=1 WHERE id=?", (int(incident_id),))
            rows = connection.execute(
                "SELECT f.score,f.better_action FROM guard_feedback f JOIN guard_incidents i ON i.id=f.incident_id "
                "WHERE i.signature=? ORDER BY f.updated_at DESC", (incident["signature"],)
            ).fetchall()
            average = sum(int(row["score"]) for row in rows) / len(rows)
            guidance = next((row["better_action"] for row in rows if row["better_action"]), "")
            connection.execute(
                "INSERT INTO guard_learning(signature,sample_count,average_score,guidance,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(signature) DO UPDATE SET sample_count=excluded.sample_count,average_score=excluded.average_score,"
                "guidance=excluded.guidance,updated_at=excluded.updated_at",
                (incident["signature"], len(rows), average, guidance, now),
            )
        self.context_recorder(
            "guard_feedback", f"Guard incident {incident_id} rated {score}/10",
            details={"incidentId": int(incident_id), "score": score, "betterAction": better_action, "ruleKey": incident["rule_key"]},
            source="adaptive_guard", severity="info",
        )
        return {"success": True, "incidentId": int(incident_id), "score": score, "betterAction": better_action}

    def list_incidents(self, *, limit: int = 50, pending_only: bool = False) -> list[dict[str, Any]]:
        limit = max(1, min(200, int(limit)))
        where = "WHERE status='open' AND needs_feedback=1 AND feedback_received=0" if pending_only else ""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT id,signature,rule_key,room,guard_level,mode,evidence_json,planned_actions_json,"
                f"executed_actions_json,status,needs_feedback,feedback_received,created_at,resolved_at "
                f"FROM guard_incidents {where} ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{
            "id": row["id"], "signature": row["signature"], "ruleKey": row["rule_key"],
            "room": row["room"], "guardLevel": row["guard_level"], "mode": row["mode"],
            "evidence": json.loads(row["evidence_json"]), "plannedActions": json.loads(row["planned_actions_json"]),
            "executedActions": json.loads(row["executed_actions_json"]), "status": row["status"],
            "needsFeedback": bool(row["needs_feedback"]), "feedbackReceived": bool(row["feedback_received"]),
            "createdAt": row["created_at"], "resolvedAt": row["resolved_at"],
        } for row in rows]

    def get_learning(self, query: str = "", limit: int = 20) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            learning = connection.execute(
                "SELECT signature,sample_count,average_score,guidance,updated_at FROM guard_learning ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(100, int(limit))),),
            ).fetchall()
            feedback = connection.execute(
                "SELECT i.id,i.signature,i.rule_key,i.room,i.evidence_json,f.score,f.better_action,f.notes,f.updated_at "
                "FROM guard_feedback f JOIN guard_incidents i ON i.id=f.incident_id ORDER BY f.updated_at DESC LIMIT 200"
            ).fetchall()
        query_tokens = _tokens(query)
        scored = []
        for row in feedback:
            haystack = " ".join([
                row["signature"], row["rule_key"], row["room"], row["evidence_json"],
                row["better_action"], row["notes"],
            ])
            overlap = len(query_tokens & _tokens(haystack)) if query_tokens else 0
            scored.append((overlap, int(row["id"]), row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        related = []
        for overlap, _incident_id, row in scored[:max(1, min(20, int(limit)))]:
            if query_tokens and overlap == 0:
                continue
            related.append({
                "incidentId": row["id"], "signature": row["signature"], "ruleKey": row["rule_key"],
                "room": row["room"], "score": row["score"], "betterAction": row["better_action"],
                "notes": row["notes"], "updatedAt": row["updated_at"], "matchScore": overlap,
            })
        return {
            "summaries": [{
                "signature": row["signature"], "sampleCount": row["sample_count"],
                "averageScore": row["average_score"], "guidance": row["guidance"], "updatedAt": row["updated_at"],
            } for row in learning],
            "relatedFeedback": related,
        }

    def build_context(self, query: str = "") -> str:
        status = self.get_status(include_incidents=False)
        learning = self.get_learning(query, limit=8)
        parts = [
            "## 自适应警戒",
            f"模式: {status['mode']}; 当前警戒等级: {status['guardLevel']}/10; 待主人评分: {status['pendingFeedback']}",
        ]
        for item in learning["relatedFeedback"]:
            parts.append(
                f"- 历史反馈 {item['signature']}: {item['score']}/10; 改进: {item['betterAction'] or '无'}; 备注: {item['notes'] or '无'}"
            )
        return "\n".join(parts)

    def record_app_telemetry(self, payload: dict[str, Any]) -> int:
        if not isinstance(payload, dict):
            raise ValueError("telemetry payload must be an object")
        event_type = str(payload.get("eventType", "")).strip()[:80]
        if not event_type:
            raise ValueError("eventType is required")
        allowed = {"page_view", "button_result", "connection_change", "setting_change", "feedback", "error"}
        if event_type not in allowed:
            raise ValueError("eventType is not allowed")
        metadata = _redact(payload.get("metadata", {}))
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "INSERT INTO app_telemetry_events(event_type,page,action,result,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    event_type, str(payload.get("page", ""))[:80], str(payload.get("action", ""))[:120],
                    str(payload.get("result", ""))[:120], _json(metadata), _now_text(),
                ),
            )
            return int(cursor.lastrowid)

    def get_status(self, *, include_incidents: bool = True) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            guard_row = connection.execute(
                "SELECT COALESCE(MAX(guard_level),0) AS level FROM guard_incidents WHERE status='open'"
            ).fetchone()
            pending = connection.execute(
                "SELECT COUNT(*) AS count FROM guard_incidents "
                "WHERE status='open' AND needs_feedback=1 AND feedback_received=0"
            ).fetchone()["count"]
            feedback = connection.execute("SELECT COUNT(*) AS count,COALESCE(AVG(score),0) AS avg FROM guard_feedback").fetchone()
        result = {
            "enabled": bool(self.config.get("enabled", True)),
            "activeAiEnabled": bool(self.config.get("activeAiEnabled", True)),
            "feedbackAutomationEnabled": bool(self.config.get("feedbackAutomation", {}).get("enabled", True)),
            "mode": "active" if self.config.get("enabled", True) else "passive",
            "guardLevel": int(guard_row["level"]),
            "pendingFeedback": int(pending),
            "learning": {"feedbackCount": int(feedback["count"]), "averageScore": float(feedback["avg"])},
            "config": self.get_config(),
            "runtime": {
                "kitchenAlarmStreak": int(self._kitchen_alarm_streak),
                "kitchenClearStreak": int(self._kitchen_clear_streak),
                "kitchenConfirmed": bool(self._kitchen_confirmed),
                "activeSignatures": sorted(self._active_signatures),
                "startedAt": float(self._started_at),
                "now": float(self.clock()),
            },
        }
        if include_incidents:
            result["recentIncidents"] = self.list_incidents(limit=20)
        return result
