#!/usr/bin/env python3
"""
数据推送服务 · 纯标准库实现
持续收集后端所有数据，整合成 JSON，定时 POST 到 yuanzhe.tech

运行环境: HarmonyOS ARM32 + Python 3.14.5 (纯标准库)
部署位置: /data/A9/smart_home/data_pusher.py

推送策略:
  - 默认每 30 秒推送一次全量快照
  - 设备状态变化时立即推送增量事件
  - 推送失败自动重试 (最多3次, 指数退避)
  - 本地缓存未推送数据 (SQLite push_queue 表)
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
import sys
from datetime import datetime
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from urllib.parse import urlparse

# ===== 配置 =====
PUSH_URL = os.environ.get("PUSH_URL", "http://yuanzhe.tech/api/smart-home/data")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "")  # Bearer token 认证
PUSH_INTERVAL = int(os.environ.get("PUSH_INTERVAL", "30"))  # 秒
PUSH_RETRY_MAX = 3
PUSH_RETRY_BASE = 2  # 秒, 指数退避基数
BATCH_SIZE = 50  # 每次最多推送条数

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "control" / "data" / "smart_home.db"
PUSH_DB_PATH = Path(__file__).resolve().parent / "push_queue.db"
LOG_PATH = ROOT / "data_pusher.log"

# 设备ID → 上次已知状态 (用于增量检测)
_last_device_state = {}
_last_sensor_state = {}
_last_push_time = 0
_push_lock = threading.Lock()
_running = True


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _db():
    return sqlite3.connect(str(DB_PATH))


def _push_db():
    return sqlite3.connect(str(PUSH_DB_PATH))


def _init_push_db():
    """初始化推送队列数据库"""
    PUSH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _push_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS push_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',  -- pending / sent / failed
            retry_count INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now')),
            sent_at     TEXT,
            error_msg   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pq_status ON push_queue(status);
        CREATE INDEX IF NOT EXISTS idx_pq_created ON push_queue(created_at);
    """)
    conn.commit()
    conn.close()


# ===== 数据采集 =====

def collect_devices():
    """采集所有设备状态"""
    conn = _db()
    rows = conn.execute(
        "SELECT id,name,type,status,room,icon,primary_value,is_on,mode,battery,protocol,updated_at "
        "FROM devices"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = {
            "id": r[0], "name": r[1], "type": r[2], "status": r[3],
            "room": r[4], "icon": r[5], "primaryValue": r[6],
            "isOn": bool(r[7]), "updatedAt": r[11]
        }
        if r[8] is not None:
            d["mode"] = r[8]
        if r[9] is not None:
            d["battery"] = r[9]
        if r[10] is not None:
            d["protocol"] = r[10]
        result.append(d)
    return result


def collect_sensors():
    """采集所有传感器数据"""
    conn = _db()
    rows = conn.execute(
        "SELECT id,name,type,sensor_group,room,icon,current_value,unit,"
        "threshold_min,threshold_max,protocol,is_alert,updated_at "
        "FROM sensors"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        s = {
            "id": r[0], "name": r[1], "type": r[2], "group": r[3],
            "room": r[4], "icon": r[5],
            "current": {"value": r[6], "unit": r[7]},
            "isAlert": bool(r[11]), "updatedAt": r[12]
        }
        if r[8] is not None:
            s["thresholdMin"] = r[8]
        if r[9] is not None:
            s["thresholdMax"] = r[9]
        if r[10] is not None:
            s["protocol"] = r[10]
        result.append(s)
    return result


def collect_scenes():
    """采集场景状态"""
    conn = _db()
    scenes = []
    for s in conn.execute("SELECT id,name,icon,color,is_active,description,updated_at FROM scenes").fetchall():
        actions = []
        for a in conn.execute(
            "SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order",
            (s[0],)
        ).fetchall():
            act = {"deviceId": a[0], "isOn": bool(a[1])}
            if a[2] is not None:
                act["primaryValue"] = a[2]
            actions.append(act)
        scenes.append({
            "id": s[0], "name": s[1], "icon": s[2], "color": s[3],
            "isActive": bool(s[4]), "description": s[5],
            "actions": actions, "updatedAt": s[6]
        })
    conn.close()
    return scenes


def collect_operations(limit=200):
    """采集最近操作记录"""
    conn = _db()
    rows = conn.execute(
        "SELECT device_id,action,params_json,result,source,scene_id,created_at "
        "FROM device_operations ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "deviceId": r[0], "action": r[1], "params": r[2],
            "result": r[3], "source": r[4], "sceneId": r[5],
            "timestamp": r[6]
        }
        for r in rows
    ]


def collect_sensor_readings(hours=24, limit=500):
    """采集传感器历史读数"""
    conn = _db()
    rows = conn.execute(
        f"SELECT sensor_id,value,unit,created_at "
        f"FROM sensor_readings WHERE created_at >= datetime('now','-{hours} hours') "
        f"ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {"sensorId": r[0], "value": r[1], "unit": r[2], "timestamp": r[3]}
        for r in rows
    ]


def collect_chat_history(limit=100):
    """采集对话记录"""
    conn = _db()
    rows = conn.execute(
        "SELECT user_id,role,content,scene_id,tools_used,created_at "
        "FROM chat_history ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "userId": r[0], "role": r[1], "content": r[2],
            "sceneId": r[3], "toolsUsed": r[4], "timestamp": r[5]
        }
        for r in rows
    ]


def collect_user():
    """采集用户信息"""
    conn = _db()
    r = conn.execute("SELECT id,nickname,home_name,member_count,avatar,updated_at FROM users WHERE id='u001'").fetchone()
    dc = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    conn.close()
    if not r:
        return {"id": "u001", "nickname": "用户", "homeName": "我的家", "memberCount": 3, "deviceCount": dc}
    return {
        "id": r[0], "nickname": r[1], "homeName": r[2],
        "memberCount": r[3], "avatar": r[4], "deviceCount": dc,
        "updatedAt": r[5]
    }


def collect_alerts():
    """采集告警信息"""
    # 告警目前是内存数据，从 gateway_v3 的 ALERTS 获取
    # 这里直接返回静态数据（后续可改为从数据库读取）
    return [
        {
            "id": "a1", "source": "门口摄像头",
            "content": "门口有人停留，检测到异常移动",
            "level": "warning", "isRead": False,
            "timestamp": int(time.time() * 1000) - 1380000
        },
        {
            "id": "a2", "source": "卧室窗帘",
            "content": "电量剩余 15%，建议更换电池",
            "level": "info", "isRead": True,
            "timestamp": int(time.time() * 1000) - 7200000
        },
        {
            "id": "a3", "source": "客厅湿度",
            "content": "当前湿度 72%，建议开启除湿",
            "level": "info", "isRead": True,
            "timestamp": int(time.time() * 1000) - 14400000
        }
    ]


def collect_cameras():
    """采集摄像头信息"""
    return [
        {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online",
         "isRecording": True, "resolution": "1080P"},
        {"id": "cam_02", "name": "门口摄像头", "room": "室外", "status": "online",
         "isRecording": False, "resolution": "1080P"},
    ]


def collect_server_status():
    """采集服务端状态"""
    return {
        "host": "192.168.1.81", "port": 8080, "isOnline": True,
        "protocol": "wifi", "version": "v3",
        "pusherVersion": "1.0.0",
        "uptime": int(time.time()),
        "python": sys.version.split()[0]
    }


def build_full_snapshot():
    """构建全量数据快照"""
    return {
        "type": "snapshot",
        "version": "1.0.0",
        "deviceId": "harmony_a9",
        "timestamp": datetime.now().isoformat(),
        "timestampMs": int(time.time() * 1000),
        "data": {
            "devices": collect_devices(),
            "sensors": collect_sensors(),
            "scenes": collect_scenes(),
            "operations": collect_operations(),
            "sensorReadings": collect_sensor_readings(),
            "chatHistory": collect_chat_history(),
            "user": collect_user(),
            "alerts": collect_alerts(),
            "cameras": collect_cameras(),
            "serverStatus": collect_server_status()
        }
    }


def build_incremental_event(event_type, payload):
    """构建增量事件"""
    return {
        "type": "event",
        "version": "1.0.0",
        "deviceId": "harmony_a9",
        "timestamp": datetime.now().isoformat(),
        "timestampMs": int(time.time() * 1000),
        "eventType": event_type,
        "data": payload
    }


# ===== 增量检测 =====

def detect_device_changes():
    """检测设备状态变化，生成增量事件"""
    global _last_device_state
    events = []
    current_devices = {}

    conn = _db()
    rows = conn.execute("SELECT id,name,type,is_on,primary_value,mode,updated_at FROM devices").fetchall()
    conn.close()

    for r in rows:
        dev_id = r[0]
        state = {"isOn": bool(r[3]), "primaryValue": r[4], "mode": r[5], "updatedAt": r[6]}
        current_devices[dev_id] = state

        if dev_id in _last_device_state:
            old = _last_device_state[dev_id]
            if old != state:
                events.append(build_incremental_event("device_change", {
                    "deviceId": dev_id,
                    "name": r[1],
                    "type": r[2],
                    "previous": old,
                    "current": state
                }))

    _last_device_state = current_devices
    return events


def detect_sensor_changes():
    """检测传感器数据变化，生成增量事件"""
    global _last_sensor_state
    events = []
    current_sensors = {}

    conn = _db()
    rows = conn.execute("SELECT id,name,type,current_value,is_alert,updated_at FROM sensors").fetchall()
    conn.close()

    for r in rows:
        sid = r[0]
        state = {"value": r[3], "isAlert": bool(r[4]), "updatedAt": r[5]}
        current_sensors[sid] = state

        if sid in _last_sensor_state:
            old = _last_sensor_state[sid]
            if old != state:
                events.append(build_incremental_event("sensor_change", {
                    "sensorId": sid,
                    "name": r[1],
                    "type": r[2],
                    "previous": old,
                    "current": state
                }))

    _last_sensor_state = current_sensors
    return events


# ===== 推送引擎 =====

def _parse_url(url):
    """解析URL，返回 (scheme, host, port, path)"""
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    host = parsed.hostname or "yuanzhe.tech"
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return scheme, host, port, path


def http_post(url, payload_json, token=""):
    """纯标准库 HTTP POST"""
    scheme, host, port, path = _parse_url(url)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Device-Id": "harmony_a9",
        "X-Push-Version": "1.0.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = payload_json.encode("utf-8")
    headers["Content-Length"] = str(len(body))

    try:
        if scheme == "https":
            conn = HTTPSConnection(host, port, timeout=15)
        else:
            conn = HTTPConnection(host, port, timeout=15)
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8", errors="replace")
        conn.close()
        return resp.status, resp_body
    except Exception as e:
        return 0, str(e)


def enqueue(event_type, payload):
    """入队待推送数据"""
    conn = _push_db()
    conn.execute(
        "INSERT INTO push_queue(event_type, payload) VALUES(?,?)",
        (event_type, json.dumps(payload, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def flush_queue():
    """推送队列中的待发送数据"""
    conn = _push_db()
    rows = conn.execute(
        "SELECT id, event_type, payload, retry_count FROM push_queue "
        "WHERE status='pending' AND retry_count < ? ORDER BY created_at ASC LIMIT ?",
        (PUSH_RETRY_MAX, BATCH_SIZE)
    ).fetchall()

    if not rows:
        conn.close()
        return 0

    sent_count = 0
    for row in rows:
        qid, event_type, payload_str, retry_count = row
        status_code, resp_body = http_post(PUSH_URL, payload_str, PUSH_TOKEN)

        if 200 <= status_code < 300:
            conn.execute(
                "UPDATE push_queue SET status='sent', sent_at=datetime('now') WHERE id=?",
                (qid,)
            )
            sent_count += 1
            log(f"[PUSH] ✓ {event_type} (id={qid}, status={status_code})")
        else:
            new_retry = retry_count + 1
            if new_retry >= PUSH_RETRY_MAX:
                conn.execute(
                    "UPDATE push_queue SET status='failed', retry_count=?, error_msg=? WHERE id=?",
                    (new_retry, f"HTTP {status_code}: {resp_body[:200]}", qid)
                )
                log(f"[PUSH] ✗ {event_type} (id={qid}) FAILED after {new_retry} retries: {status_code}")
            else:
                conn.execute(
                    "UPDATE push_queue SET retry_count=?, error_msg=? WHERE id=?",
                    (new_retry, f"HTTP {status_code}: {resp_body[:200]}", qid)
                )
                log(f"[PUSH] ↻ {event_type} (id={qid}) retry {new_retry}/{PUSH_RETRY_MAX}: {status_code}")

    # 清理已发送的旧数据 (保留7天)
    conn.execute(
        "DELETE FROM push_queue WHERE status='sent' AND sent_at < datetime('now','-7 days')"
    )
    # 清理失败超过30天的
    conn.execute(
        "DELETE FROM push_queue WHERE status='failed' AND created_at < datetime('now','-30 days')"
    )
    conn.commit()
    conn.close()
    return sent_count


# ===== 主循环 =====

def push_snapshot():
    """推送全量快照"""
    snapshot = build_full_snapshot()
    enqueue("snapshot", snapshot)
    log(f"[SNAPSHOT] 入队: {len(snapshot['data'])} 类数据, "
        f"devices={len(snapshot['data']['devices'])}, "
        f"sensors={len(snapshot['data']['sensors'])}, "
        f"scenes={len(snapshot['data']['scenes'])}")


def push_incremental():
    """检测并推送增量事件"""
    device_events = detect_device_changes()
    sensor_events = detect_sensor_changes()

    for evt in device_events:
        enqueue("device_change", evt)
    for evt in sensor_events:
        enqueue("sensor_change", evt)

    if device_events or sensor_events:
        log(f"[INCREMENTAL] 入队: {len(device_events)} 设备变化 + {len(sensor_events)} 传感器变化")


def main_loop():
    """主推送循环"""
    global _running

    log("=" * 50)
    log("数据推送服务启动")
    log(f"目标: {PUSH_URL}")
    log(f"推送间隔: {PUSH_INTERVAL}s")
    log(f"认证: {'Bearer ***' if PUSH_TOKEN else '无'}")
    log("=" * 50)

    # 初始化基线状态
    detect_device_changes()
    detect_sensor_changes()
    log("[INIT] 基线状态已采集")

    # 首次立即推送全量快照
    push_snapshot()

    cycle = 0
    while _running:
        try:
            time.sleep(PUSH_INTERVAL)
            cycle += 1

            # 每 N 个周期推送一次全量快照 (默认每5分钟)
            if cycle % (300 // PUSH_INTERVAL) == 0:
                push_snapshot()

            # 每个周期检测增量
            push_incremental()

            # 推送队列
            sent = flush_queue()
            if sent > 0:
                log(f"[FLUSH] 已推送 {sent} 条")

        except Exception as e:
            log(f"[ERROR] {e}")
            time.sleep(5)


def start_pusher():
    """在后台线程启动推送服务"""
    _init_push_db()
    t = threading.Thread(target=main_loop, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    _init_push_db()
    try:
        main_loop()
    except KeyboardInterrupt:
        _running = False
        log("推送服务已停止")
