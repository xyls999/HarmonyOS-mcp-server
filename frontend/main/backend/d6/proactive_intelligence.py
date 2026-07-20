"""Deterministic assistant feed and feedback learning for the A9 gateway.

The module deliberately does not execute arbitrary model output.  It turns
known device operations and sensor facts into reviewable reports, then stores
the owner's feedback for future context injection.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


_CST = timezone(timedelta(hours=8))

_DEVICE_NAMES = {
    "light_01": "客厅主灯", "light_02": "厨房灯", "light_03": "卧室灯", "light_04": "卫生间灯",
    "ac_01": "客厅空调", "fan_02": "换气扇", "curtain_01": "卧室窗帘", "door_01": "客厅门禁",
    "alarm_01": "蜂鸣器",
}


def _now_text() -> str:
    return datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ProactiveIntelligence:
    """Persistent reports sourced from the gateway's SQLite operations log."""

    def __init__(self, db_path: str | Path, *, window_seconds: int = 600, toggle_threshold: int = 4):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.window_seconds = int(window_seconds)
        self.toggle_threshold = int(toggle_threshold)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS device_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, action TEXT,
                params_json TEXT, result TEXT, source TEXT DEFAULT '', scene_id TEXT,
                created_at TEXT DEFAULT '', created_ts REAL
            )""")
            existing = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='device_operations'").fetchone()
            if existing:
                columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(device_operations)").fetchall()}
                if "created_ts" not in columns:
                    conn.execute("ALTER TABLE device_operations ADD COLUMN created_ts REAL")
                conn.execute("UPDATE device_operations SET created_ts=COALESCE(created_ts, strftime('%s', created_at)) WHERE created_ts IS NULL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS assistant_proactive_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    operations_json TEXT NOT NULL DEFAULT '[]',
                    chart_json TEXT NOT NULL DEFAULT '{}',
                    severity TEXT NOT NULL DEFAULT 'info',
                    created_at TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    UNIQUE(kind, title, created_ts)
                );
                CREATE INDEX IF NOT EXISTS idx_assistant_feed_time
                    ON assistant_proactive_reports(id DESC);
                CREATE TABLE IF NOT EXISTS assistant_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER NOT NULL,
                    score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 10),
                    choice TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(report_id) REFERENCES assistant_proactive_reports(id)
                );
                CREATE INDEX IF NOT EXISTS idx_assistant_feedback_report
                    ON assistant_feedback(report_id, id DESC);
                CREATE TABLE IF NOT EXISTS assistant_alert_acknowledgements (
                    event_id INTEGER PRIMARY KEY,
                    acknowledged_at TEXT NOT NULL,
                    acknowledged_ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistant_state_snapshots (
                    bucket REAL PRIMARY KEY,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistant_conversation_state (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    cleared_ts REAL NOT NULL DEFAULT 0,
                    cleared_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TRIGGER IF NOT EXISTS trg_device_operations_created_ts
                AFTER INSERT ON device_operations
                WHEN NEW.created_ts IS NULL
                BEGIN
                    UPDATE device_operations SET created_ts = strftime('%s','now') WHERE id = NEW.id;
                END;
            """)

    def clear_conversation(self, *, cleared_ts: float | None = None) -> None:
        """Hide old assistant reports from the live stream without deleting learning logs."""
        ts = float(time.time() if cleared_ts is None else cleared_ts)
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO assistant_conversation_state(id,cleared_ts,cleared_at) VALUES(1,?,?) "
                "ON CONFLICT(id) DO UPDATE SET cleared_ts=excluded.cleared_ts, cleared_at=excluded.cleared_at",
                (ts, _now_text()),
            )

    def _conversation_clear_ts(self, conn: sqlite3.Connection) -> float:
        try:
            row = conn.execute("SELECT cleared_ts FROM assistant_conversation_state WHERE id=1").fetchone()
            return float(row[0]) if row else 0.0
        except sqlite3.OperationalError:
            return 0.0

    def conversation_clear_ts(self) -> float:
        with closing(self._connect()) as conn:
            return self._conversation_clear_ts(conn)

    def _is_fresh(self, created_at: str, now: float | None) -> bool:
        if now is None or now < 1_000_000_000:
            return True
        try:
            parsed = datetime.strptime(str(created_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CST).timestamp()
            return parsed <= now and now - parsed <= 900
        except (TypeError, ValueError, OverflowError):
            return False

    def _latest_sensor_state(self, conn: sqlite3.Connection, now: float | None = None) -> dict[str, dict[str, Any]]:
        try:
            rows = conn.execute(
                "SELECT sensor_id,value,unit,created_at FROM sensor_readings ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        state: dict[str, dict[str, Any]] = {}
        for row in rows:
            sensor_id = str(row["sensor_id"])
            if sensor_id in state:
                continue
            if not self._is_fresh(str(row["created_at"] or ""), now):
                continue
            value = float(row["value"])
            state[sensor_id] = {
                "value": value,
                "unit": str(row["unit"] or ""),
                "online": value != -999.0,
                "createdAt": str(row["created_at"] or ""),
            }
        return state

    def _latest_device_state(self, conn: sqlite3.Connection, now: float | None = None) -> dict[str, dict[str, Any]]:
        """Read the latest persisted device snapshot when the gateway schema has it."""
        try:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(devices)").fetchall()}
            if "id" not in columns:
                return {}
            selected = [name for name in ("id", "name", "status", "is_on", "primary_value", "updated_at", "last_seen") if name in columns]
            rows = conn.execute(f"SELECT {','.join(selected)} FROM devices ORDER BY id").fetchall()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(zip(selected, row))
            device_id = str(item.get("id", ""))
            if not device_id:
                continue
            if not self._is_fresh(str(item.get("updated_at", item.get("last_seen", "")) or ""), now):
                continue
            status = str(item.get("status", "")).lower()
            is_on = bool(item.get("is_on", False))
            result[f"device:{device_id}"] = {
                "deviceId": device_id, "name": str(item.get("name", device_id)),
                "online": status in {"online", "active", "connected", ""},
                "isOn": is_on, "value": 1.0 if is_on else 0.0,
                "primaryValue": item.get("primary_value"),
                "createdAt": str(item.get("updated_at", item.get("last_seen", "")) or ""),
            }
        return result

    def _previous_snapshot(self, conn: sqlite3.Connection, bucket: float) -> dict[str, dict[str, Any]]:
        row = conn.execute(
            "SELECT state_json FROM assistant_state_snapshots WHERE bucket < ? ORDER BY bucket DESC LIMIT 1",
            (bucket,),
        ).fetchone()
        if not row:
            return {}
        try:
            parsed = json.loads(row["state_json"] or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}

    def _state_changes(self, previous: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        sensor_names = {"temp_01": "客厅温度", "humid_01": "客厅湿度",
                        "smoke_01": "厨房烟雾", "heat_01": "厨房热敏", "air_01": "厨房综合报警"}
        thresholds = {"temp_01": 0.5, "humid_01": 3.0, "smoke_01": 0.5, "heat_01": 20.0, "air_01": 1.0}
        changes: list[dict[str, Any]] = []
        for sensor_id, latest in current.items():
            before = previous.get(sensor_id)
            if not before:
                continue
            if sensor_id.startswith("device:"):
                old_online = bool(before.get("online", False))
                new_online = bool(latest.get("online", False))
                old_on = bool(before.get("isOn", False))
                new_on = bool(latest.get("isOn", False))
                if old_online != new_online:
                    changes.append({"sensorId": sensor_id, "name": latest.get("name", sensor_id[7:]),
                                    "before": 1.0 if old_online else 0.0, "after": 1.0 if new_online else 0.0,
                                    "delta": 1.0 if new_online else -1.0,
                                    "description": "已上线" if new_online else "已离线"})
                elif old_on != new_on:
                    changes.append({"sensorId": sensor_id, "name": latest.get("name", sensor_id[7:]),
                                    "before": 1.0 if old_on else 0.0, "after": 1.0 if new_on else 0.0,
                                    "delta": 1.0 if new_on else -1.0,
                                    "description": "已开启" if new_on else "已关闭"})
                continue
            old_value = float(before.get("value", -999.0))
            new_value = float(latest.get("value", -999.0))
            if (old_value == -999.0) != (new_value == -999.0):
                changes.append({"sensorId": sensor_id, "name": sensor_names.get(sensor_id, sensor_id),
                                "before": old_value, "after": new_value, "delta": None,
                                "description": "已恢复" if new_value != -999.0 else "已离线"})
                continue
            threshold = thresholds.get(sensor_id, 1.0)
            if new_value != -999.0 and abs(new_value - old_value) >= threshold:
                changes.append({"sensorId": sensor_id, "name": sensor_names.get(sensor_id, sensor_id),
                                "before": old_value, "after": new_value, "delta": round(new_value - old_value, 2),
                                "description": f"从 {old_value:g} 变为 {new_value:g}"})
        return changes

    def _summary_chart(self, changes: list[dict[str, Any]], operations: list[dict[str, Any]],
                       current_state: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        labels = [str(change["name"]) for change in changes]
        values = [abs(float(change.get("delta") or 0)) for change in changes]
        if operations:
            labels.append("设备操作")
            values.append(float(len(operations)))
        if not labels:
            state = current_state or {}
            devices = [item for key, item in state.items() if str(key).startswith("device:")]
            labels = ["在线设备", "开启设备", "在线传感器"]
            values = [float(sum(1 for item in devices if item.get("online"))),
                      float(sum(1 for item in devices if item.get("online") and item.get("isOn"))),
                      float(sum(1 for key, item in state.items() if not str(key).startswith("device:") and item.get("value") != -999.0))]
        useful = [(label, value) for label, value in zip(labels, values) if float(value) > 0]
        if len(useful) < 2:
            return {}
        return {"labels": [item[0] for item in useful[:8]],
                "values": [item[1] for item in useful[:8]], "types": ["pie"]}

    def record_operation(self, device_id: str, action: str, params: dict[str, Any] | None,
                         result: str = "ok", *, created_ts: float | None = None) -> None:
        """Test/integration helper; production writes continue using device_operations."""
        with closing(self._connect()) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS device_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, action TEXT,
                params_json TEXT, result TEXT, source TEXT DEFAULT '', scene_id TEXT,
                created_at TEXT DEFAULT '', created_ts REAL
            )""")
            ts = float(time.time() if created_ts is None else created_ts)
            conn.execute(
                "INSERT INTO device_operations(device_id,action,params_json,result,source,created_at,created_ts) VALUES(?,?,?,?,?,?,?)",
                (device_id, action, _json(params or {}), result, "assistant", _now_text(), ts),
            )

    def create_report(self, kind: str, title: str, summary: str, evidence: dict[str, Any],
                      operations: list[dict[str, Any]], chart: dict[str, Any], *,
                      severity: str = "info", created_ts: float | None = None) -> dict[str, Any]:
        ts = float(time.time() if created_ts is None else created_ts)
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO assistant_proactive_reports(kind,title,summary,evidence_json,operations_json,chart_json,severity,created_at,created_ts) VALUES(?,?,?,?,?,?,?,?,?)",
                (kind, title, summary, _json(evidence), _json(operations), _json(chart), severity, _now_text(), ts),
            )
            row = conn.execute(
                "SELECT * FROM assistant_proactive_reports WHERE kind=? AND title=? AND created_ts=?",
                (kind, title, ts),
            ).fetchone()
        return self._row(row)

    def publish_operation(self, device_id: str, action: str, success: bool, *,
                          created_ts: float | None = None) -> dict[str, Any]:
        name = _DEVICE_NAMES.get(str(device_id), str(device_id))
        action_text = str(action or "操作")
        result_text = "成功" if bool(success) else "失败"
        return self.create_report(
            "device_operation", f"设备操作：{name}", f"{name}已{action_text}，操作{result_text}。",
            {"deviceId": str(device_id), "deviceName": name, "action": action_text, "success": bool(success)},
            [{"device_id": str(device_id), "device_name": name, "action": action_text, "result": result_text}],
            {}, severity="info" if success else "warning", created_ts=created_ts,
        )

    def _row(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        result = dict(row)
        for key in ("evidence_json", "operations_json", "chart_json"):
            target = key.removesuffix("_json")
            try:
                result[target] = json.loads(result.pop(key))
            except (TypeError, ValueError):
                result[target] = {} if target != "operations" else []
        result["feedback"] = self.feedback_for(int(result["id"]))
        if "created_at" in result:
            result["createdAt"] = result["created_at"]
        if "created_ts" in result:
            result["createdTs"] = result["created_ts"]
        return result

    def feedback_for(self, report_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT score,choice,note,created_at FROM assistant_feedback WHERE report_id=? ORDER BY id DESC LIMIT 1",
                (int(report_id),),
            ).fetchone()
        return dict(row) if row else None

    def is_alert_acknowledged(self, event_id: int) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM assistant_alert_acknowledgements WHERE event_id=? LIMIT 1",
                (int(event_id),),
            ).fetchone()
        return row is not None

    def acknowledge_alert(self, event_id: int) -> dict[str, Any]:
        event_id = int(event_id)
        if event_id == 0:
            raise ValueError("event id is required")
        now = float(time.time())
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assistant_alert_acknowledgements(event_id,acknowledged_at,acknowledged_ts) "
                "VALUES(?,?,?)", (event_id, _now_text(), now),
            )
        return {"success": True, "eventId": event_id, "acknowledged": True, "acknowledgedTs": now}

    def run_cycle(self, *, now: float | None = None, force: bool = False) -> list[dict[str, Any]]:
        now = float(time.time() if now is None else now)
        with closing(self._connect()) as conn:
            try:
                rows = conn.execute(
                    "SELECT id,device_id,action,params_json,result,source,created_at,COALESCE(created_ts,0) AS created_ts "
                    "FROM device_operations WHERE COALESCE(created_ts,0) BETWEEN ? AND ? ORDER BY created_ts ASC",
                    (now - self.window_seconds, now),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        grouped: dict[str, list[dict[str, Any]]] = {}
        last_toggle_state: dict[str, bool] = {}
        all_operations: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["params"] = json.loads(item.pop("params_json") or "{}")
            except (TypeError, ValueError):
                item["params"] = {}
            all_operations.append(item)
            result_text = str(row["result"] or "").lower()
            if ("offline" in result_text or "unavailable" in result_text or
                    "failed" in result_text or "fail" in result_text or '"success":false' in result_text):
                continue
            action = str(row["action"] or "").lower()
            if action not in {"on", "off", "toggle", "scene_toggle"} and "toggle" not in action:
                continue
            desired = item["params"].get("isOn")
            if not isinstance(desired, bool):
                if action == "on":
                    desired = True
                elif action == "off":
                    desired = False
            device_id = str(row["device_id"])
            if isinstance(desired, bool):
                if last_toggle_state.get(device_id) == desired:
                    continue
                last_toggle_state[device_id] = desired
            grouped.setdefault(device_id, []).append(item)
        reports: list[dict[str, Any]] = []
        # 每十分钟最多生成一条智能汇总；比较当前状态和上一周期，避免重复模板。
        bucket = float(int(now // 600) * 600)
        with closing(self._connect()) as conn:
            summary_exists = conn.execute(
                "SELECT 1 FROM assistant_proactive_reports WHERE kind='summary' AND title='十分钟家庭状态汇总' AND created_ts=? LIMIT 1",
                (bucket,),
            ).fetchone()
            current_state = self._latest_sensor_state(conn, now)
            current_state.update(self._latest_device_state(conn, now))
            previous_state = self._previous_snapshot(conn, bucket)
        changes = self._state_changes(previous_state, current_state)
        suggestions: list[str] = []
        for change in changes:
            if change["sensorId"] == "temp_01":
                suggestions.append("温度变化明显，建议观察空调制冷状态")
            elif change["sensorId"] == "humid_01":
                suggestions.append("湿度变化明显，建议观察除湿或换气状态")
            elif change["sensorId"] in {"smoke_01", "heat_01", "air_01"} and change["after"] != -999.0:
                suggestions.append(f"{change['name']}状态变化，建议确认厨房现场")
            elif change["after"] == -999.0:
                suggestions.append(f"{change['name']}已离线，建议检查供电和网络")
        if any(len(items) >= self.toggle_threshold for items in grouped.values()):
            suggestions.append("检测到设备短时反复切换，建议检查自动化规则")
        if not suggestions:
            suggestions.append("首次采集完成，继续观察下一周期变化" if not previous_state else "当前状态稳定，继续保持现有策略")
        if not previous_state:
            change_text = "已建立首次设备与传感器基线"
        elif changes:
            change_text = "；".join(f"{c['name']}{c['description']}" for c in changes)
        else:
            change_text = "温湿度和设备在线状态均无明显变化"
        automatic_operations = [
            item for item in all_operations
            if str(item.get("source", "")) in {"alarm_linkage", "adaptive_guard", "proactive_intelligence"}
            and str(item.get("result", "")).lower() not in {"failed", "failure", "error", "false"}
        ]
        if automatic_operations:
            operation_text = f"系统完成 {len(automatic_operations)} 次联动调整"
        elif all_operations:
            operation_text = f"记录 {len(all_operations)} 次设备操作，系统未改变设备状态"
        else:
            operation_text = "期间没有新的设备操作"
        summary_text = f"最近 {self.window_seconds // 60} 分钟，{change_text}。{operation_text}。建议：{'；'.join(suggestions)}。"
        adjustment_count = len(automatic_operations)
        if not summary_exists or force:
            reports.append(self.create_report(
                "summary", "十分钟家庭状态汇总", summary_text,
                {"operationCount": len(all_operations), "deviceCount": len(grouped),
                 "windowSeconds": self.window_seconds, "changes": changes,
                 "suggestions": suggestions, "currentState": current_state,
                  "previousState": previous_state, "adjustmentCount": adjustment_count,
                  "adjustments": automatic_operations[-10:]},
                all_operations[-10:], self._summary_chart(changes, all_operations, current_state),
                severity="warning" if changes else "info", created_ts=bucket if not summary_exists else now,
            ))
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assistant_state_snapshots(bucket,state_json,created_at) VALUES(?,?,?)",
                (bucket, _json(current_state), _now_text()),
            )
        for device_id, operations in grouped.items():
            if len(operations) < self.toggle_threshold:
                continue
            title = f"{device_id} 短时反复切换"
            with closing(self._connect()) as conn:
                exists = conn.execute(
                    "SELECT 1 FROM assistant_proactive_reports WHERE kind='repeated_toggle' AND title=? AND created_ts BETWEEN ? AND ? LIMIT 1",
                    (title, now - self.window_seconds, now + 1),
                ).fetchone()
            if exists:
                continue
            report = self.create_report(
                "repeated_toggle", title,
                f"{device_id} 在 {self.window_seconds // 60} 分钟内发生 {len(operations)} 次开关操作，建议检查自动化规则或设备状态。",
                {"deviceId": device_id, "count": len(operations), "windowSeconds": self.window_seconds},
                operations,
                {"labels": [str(item["created_at"])[11:16] for item in operations], "values": [1] * len(operations), "types": ["line", "pie", "radar"]},
                severity="warning", created_ts=now,
            )
            reports.append(report)
            break
        return reports

    def submit_feedback(self, report_id: int, score: int, choice: str = "", note: str = "") -> dict[str, Any]:
        try:
            score = int(score)
        except (TypeError, ValueError):
            raise ValueError("score must be an integer from 1 to 10")
        if not 1 <= score <= 10:
            raise ValueError("score must be an integer from 1 to 10")
        choice = str(choice or "").upper()
        if choice and choice not in {"A", "B", "C", "D"}:
            raise ValueError("choice must be A, B, C or D")
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT kind,evidence_json FROM assistant_proactive_reports WHERE id=?", (int(report_id),)
            ).fetchone()
            if not row:
                raise ValueError("report not found")
            try:
                evidence = json.loads(row["evidence_json"] or "{}")
            except (TypeError, ValueError):
                evidence = {}
            if int(evidence.get("adjustmentCount", 0) or 0) <= 0:
                raise ValueError("只有实际自动调整过设备的事件才需要评分")
            conn.execute(
                "INSERT INTO assistant_feedback(report_id,score,choice,note,created_at) VALUES(?,?,?,?,?)",
                (int(report_id), score, choice, str(note or "")[:1000], _now_text()),
            )
        return {"reportId": int(report_id), "score": score, "choice": choice, "note": str(note or "")[:1000]}

    def list_feed(self, *, since: int = 0, limit: int = 30) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            cleared_ts = self._conversation_clear_ts(conn)
            rows = conn.execute(
                "SELECT * FROM assistant_proactive_reports "
                "WHERE id>? AND created_ts>? AND id NOT IN (SELECT report_id FROM assistant_feedback) "
                "ORDER BY id DESC LIMIT ?",
                (int(since), cleared_ts, max(1, min(int(limit), 100))),
            ).fetchall()
        return [self._row(row) for row in rows]
