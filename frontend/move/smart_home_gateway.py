#!/usr/bin/env python3
"""
智慧家居 HTTP 网关 · 为鸿蒙 App 提供 RESTful API
零第三方依赖（仅标准库 http.server + sqlite3 + urllib + json）

能力:
  1. 设备控制 → 写 control.db + 调下位机骨架
  2. 大模型对话 → 调 DeepSeek 云 API
  3. 状态/传感器/摄像头/警报查询

启动: python3 smart_home_gateway.py
默认端口: 8080
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ===== 配置 =====
HOST = "0.0.0.0"
PORT = 8080
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "control" / "data" / "control.db"
SCHEMA_PATH = ROOT / "control" / "database" / "schema.sql"
LOG_PATH = ROOT / "gateway.log"

# DeepSeek 配置（从 .deepseek_env 加载）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===== 数据库 =====
def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def db_init() -> None:
    if not SCHEMA_PATH.exists():
        log(f"[WARN] schema not found: {SCHEMA_PATH}")
        return
    with db_connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    log(f"[DB] initialized at {DB_PATH}")


def save_device_status(device_id: str, device_type: str, status: str, payload: dict) -> int:
    with db_connect() as conn:
        cur = conn.execute(
            "INSERT INTO device_status(device_id, device_type, status, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (device_id, device_type, status, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
        )
        return int(cur.lastrowid)


def save_command(target: str, command: str, payload: dict, result: str = "ok") -> int:
    with db_connect() as conn:
        cur = conn.execute(
            "INSERT INTO control_commands(target, command, payload_json, result) VALUES (?, ?, ?, ?)",
            (target, command, json.dumps(payload, ensure_ascii=False), result),
        )
        return int(cur.lastrowid)


def list_commands(limit: int = 50) -> list:
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT target, command, payload_json, result, created_at FROM control_commands "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ===== 默认设备/传感器/摄像头（保证 App 首次有数据）=====
DEFAULT_DEVICES = [
    {"id": "fan_01", "name": "客厅吊扇", "type": "fan", "status": "online", "room": "客厅", "icon": "fan_fill_1", "primaryValue": 2, "isOn": True, "battery": 100},
    {"id": "fan_02", "name": "卧室循环扇", "type": "fan", "status": "online", "room": "主卧", "icon": "fan_fill_1", "primaryValue": 1, "isOn": False, "battery": 88},
    {"id": "ac_01", "name": "客厅中央空调", "type": "ac", "status": "active", "room": "客厅", "icon": "air_fill", "primaryValue": 24, "isOn": True, "mode": "制冷"},
    {"id": "ac_02", "name": "主卧空调", "type": "ac", "status": "online", "room": "主卧", "icon": "air_fill", "primaryValue": 26, "isOn": False, "mode": "制冷"},
    {"id": "door_01", "name": "入户门禁", "type": "door", "status": "online", "room": "玄关", "icon": "door_service", "primaryValue": 0, "isOn": False, "battery": 92},
    {"id": "light_01", "name": "客厅主灯", "type": "light", "status": "online", "room": "客厅", "icon": "lightbulb", "primaryValue": 80, "isOn": True},
    {"id": "light_02", "name": "卧室氛围灯", "type": "light", "status": "online", "room": "主卧", "icon": "lightbulb", "primaryValue": 40, "isOn": False},
]

# 运行时设备状态（内存，受控制指令影响）
DEVICE_STATE: dict[str, dict] = {d["id"]: dict(d) for d in DEFAULT_DEVICES}


def get_device(id_: str) -> dict | None:
    return DEVICE_STATE.get(id_)


DEFAULT_SENSORS = [
    {"id": "temp_01", "name": "客厅温度", "type": "temperature", "group": "环境监测", "room": "客厅", "icon": "thermometer", "current": {"value": 24.6, "unit": "°C"}, "thresholdMax": 35, "protocol": "wifi", "isAlert": False},
    {"id": "humid_01", "name": "客厅湿度", "type": "humidity", "group": "环境监测", "room": "客厅", "icon": "drop", "current": {"value": 52, "unit": "%RH"}, "thresholdMax": 70, "protocol": "wifi", "isAlert": False},
    {"id": "air_01", "name": "PM2.5", "type": "air_quality", "group": "环境监测", "room": "客厅", "icon": "wind", "current": {"value": 18, "unit": "μg/m³"}, "thresholdMax": 75, "protocol": "wifi", "isAlert": False},
    {"id": "light_s_01", "name": "客厅光照度", "type": "illuminance", "group": "环境监测", "room": "客厅", "icon": "sun_max", "current": {"value": 842, "unit": "lux"}, "thresholdMax": 2000, "protocol": "starflash", "isAlert": False},
    {"id": "pir_01", "name": "客厅人体感应", "type": "pir", "group": "安防", "room": "客厅", "icon": "figure_arms_open", "current": {"value": 1, "unit": "触发"}, "thresholdMax": 1, "protocol": "starflash", "isAlert": True},
    {"id": "smoke_01", "name": "厨房烟雾", "type": "smoke", "group": "安防", "room": "厨房", "icon": "flame_fill", "current": {"value": 0, "unit": "正常"}, "thresholdMax": 1, "protocol": "wifi", "isAlert": False},
    {"id": "power_01", "name": "实时功率", "type": "power", "group": "能耗", "room": "全屋", "icon": "bolt_fill", "current": {"value": 1.86, "unit": "kW"}, "thresholdMax": 10, "protocol": "wifi", "isAlert": False},
]

DEFAULT_CAMERAS = [
    {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online", "isRecording": True, "resolution": "2K", "previewColor": "#1A3A5C"},
    {"id": "cam_02", "name": "入户门铃", "room": "玄关", "status": "online", "isRecording": True, "resolution": "1080P", "previewColor": "#3A1A5C"},
    {"id": "cam_03", "name": "车库监控", "room": "车库", "status": "online", "isRecording": False, "resolution": "1080P", "previewColor": "#1A5C3A"},
]

DEFAULT_ALERTS = [
    {"id": "a1", "source": "客厅人体感应", "content": "检测到陌生人体活动，已自动开启布防", "level": "danger", "isRead": False, "timestamp": int(time.time() * 1000) - 300000},
    {"id": "a2", "source": "入户门铃", "content": "有人按响了门铃", "level": "info", "isRead": False, "timestamp": int(time.time() * 1000) - 1800000},
]


# ===== DeepSeek 对话 =====
def chat_with_deepseek(messages: list) -> str:
    """调 DeepSeek 云 API，返回回复文本"""
    if not DEEPSEEK_API_KEY:
        return "（网关未配置 DEEPSEEK_API_KEY，无法对话。请在 .deepseek_env 配置）"

    # 构造系统提示
    sys_msg = {
        "role": "system",
        "content": "你是智慧家居助手，可以帮用户控制风扇、空调、门禁、灯光，查询传感器数据和监控。回答简洁友好。"
    }
    full_messages = [sys_msg] + messages

    body = {
        "model": DEEPSEEK_MODEL,
        "messages": full_messages,
        "temperature": 0.6,
        "max_tokens": 800,
    }
    request = Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        log(f"[DeepSeek] HTTP {exc.code}: {detail}")
        return f"（大模型请求失败：HTTP {exc.code}）"
    except URLError as exc:
        log(f"[DeepSeek] URL error: {exc}")
        return f"（大模型网络错误：{exc.reason}）"
    except Exception as exc:
        log(f"[DeepSeek] error: {exc}")
        return f"（大模型调用异常：{exc}）"


# ===== HTTP 处理器 =====
class GatewayHandler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, data) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def log_message(self, format, *args) -> None:
        log(f"{self.command} {self.path} - {args[0] if args else ''}")

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        try:
            if path == "/health":
                self._send_json(200, {"ok": True, "service": "smart_home_gateway", "time": utc_now_iso()})
            elif path == "/api/devices":
                self._send_json(200, list(DEVICE_STATE.values()))
            elif path == "/api/sensors":
                self._send_json(200, DEFAULT_SENSORS)
            elif path == "/api/cameras":
                self._send_json(200, DEFAULT_CAMERAS)
            elif path == "/api/alerts":
                self._send_json(200, DEFAULT_ALERTS)
            elif path == "/api/user/profile":
                self._send_json(200, {"id": "u001", "nickname": "用户", "homeName": "我的家", "memberCount": 3, "deviceCount": len(DEVICE_STATE)})
            elif path == "/api/server/status":
                self._send_json(200, {"host": "192.168.1.81", "port": PORT, "isOnline": True, "protocol": "wifi", "latency": 8, "cpuUsage": 30, "memUsage": 45, "storageUsage": 38})
            elif path == "/api/commands":
                self._send_json(200, list_commands())
            else:
                self._send_json(404, {"error": "not found", "path": path})
        except Exception as exc:
            log(f"[GET {path}] error: {exc}")
            self._send_json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        body = self._read_body()
        try:
            # 控制设备: /api/devices/{id}/control
            m = re.match(r"^/api/devices/([\w_]+)/control$", path)
            if m:
                dev_id = m.group(1)
                dev = get_device(dev_id)
                if not dev:
                    self._send_json(404, {"error": "device not found"})
                    return
                action = body.get("action", "")
                params = body.get("params", {})
                # 应用控制
                if action in ("set_speed", "set_temp", "set_brightness") and "value" in params:
                    dev["primaryValue"] = params["value"]
                if action == "set_mode" and "mode" in params:
                    dev["mode"] = params["mode"]
                save_command(dev_id, action, params, "ok")
                save_device_status(dev_id, dev["type"], "active", {"action": action, **params})
                log(f"[CONTROL] {dev_id} {action} {params}")
                self._send_json(200, {"success": True, "device": dev})
                return

            # 开关: /api/devices/{id}/toggle
            m = re.match(r"^/api/devices/([\w_]+)/toggle$", path)
            if m:
                dev_id = m.group(1)
                dev = get_device(dev_id)
                if not dev:
                    self._send_json(404, {"error": "device not found"})
                    return
                is_on = bool(body.get("isOn", not dev["isOn"]))
                dev["isOn"] = is_on
                save_command(dev_id, "toggle", {"isOn": is_on}, "ok")
                save_device_status(dev_id, dev["type"], "active" if is_on else "online", {"isOn": is_on})
                log(f"[TOGGLE] {dev_id} isOn={is_on}")
                self._send_json(200, {"success": True, "device": dev})
                return

            # 添加设备: /api/devices
            if path == "/api/devices":
                new_dev = {
                    "id": body.get("id", f"dev_{int(time.time())}"),
                    "name": body.get("name", "新设备"),
                    "type": body.get("type", "light"),
                    "status": "online",
                    "room": body.get("room", "客厅"),
                    "icon": body.get("icon", "lightbulb"),
                    "primaryValue": body.get("primaryValue", 0),
                    "isOn": False,
                }
                DEVICE_STATE[new_dev["id"]] = new_dev
                save_command(new_dev["id"], "add", new_dev, "ok")
                log(f"[ADD] {new_dev['id']} {new_dev['name']}")
                self._send_json(200, {"success": True, "device": new_dev})
                return

            # 大模型对话: /api/chat/send
            if path == "/api/chat/send":
                messages = body.get("messages", [])
                # 转换为 deepseek 格式（只取 role + content）
                ds_messages = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
                log(f"[CHAT] {len(ds_messages)} messages")
                reply = chat_with_deepseek(ds_messages)
                log(f"[CHAT] reply: {reply[:80]}...")
                self._send_json(200, {"reply": reply, "role": "assistant"})
                return

            self._send_json(404, {"error": "not found", "path": path})
        except Exception as exc:
            log(f"[POST {path}] error: {exc}")
            self._send_json(500, {"error": str(exc)})


def load_env() -> None:
    """从 .deepseek_env 加载环境变量"""
    env_path = ROOT / "HarmonyOS-mcp-server" / ".deepseek_env"
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                os.environ[k] = v
                if k == "DEEPSEEK_API_KEY":
                    DEEPSEEK_API_KEY = v
                elif k == "DEEPSEEK_BASE_URL":
                    DEEPSEEK_BASE_URL = v
                elif k == "DEEPSEEK_MODEL":
                    DEEPSEEK_MODEL = v
    log(f"[ENV] DEEPSEEK_API_KEY={'*' + DEEPSEEK_API_KEY[-4:] if DEEPSEEK_API_KEY else '(empty)'}")
    log(f"[ENV] DEEPSEEK_MODEL={DEEPSEEK_MODEL}")


def main() -> None:
    load_env()
    db_init()
    server = ThreadingHTTPServer((HOST, PORT), GatewayHandler)
    log(f"=" * 50)
    log(f"智慧家居网关启动")
    log(f"监听: http://{HOST}:{PORT}")
    log(f"数据库: {DB_PATH}")
    log(f"设备数: {len(DEVICE_STATE)}")
    log(f"=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("收到退出信号，关闭服务")
        server.shutdown()


if __name__ == "__main__":
    main()
