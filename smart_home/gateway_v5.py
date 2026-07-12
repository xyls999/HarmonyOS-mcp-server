#!/usr/bin/env python3
"""
智慧家居 HTTP 网关 v5 · 纯标准库 + 真实硬件控制
在 /data/A9/ 设备上运行

v5 变更:
  - 删除所有场景/模式(回家/离家/观影/用餐等)
  - 设备离线=关+没有数据，不显示任何模拟/默认值
  - 厨房联动完全按交接文档: 1秒轮询+UDP8001+BEEP联动
  - 设备连通检查接口: 在线/离线/详细信息+语音播报
  - 所有操作有日志输出+语音确认
  - TTS只管语音输出，输入由/api/voice/input接管
"""
from __future__ import annotations
import json, os, re, socket, sqlite3, subprocess, threading, time, zlib, sys, ssl, hashlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

HOST = "0.0.0.0"; PORT = 8080
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "control" / "data" / "smart_home.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "db" / "schema.sql"
LOG_PATH = ROOT / "gateway_v5.log"

# ===== AI 配置 =====
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

_AI_CONFIG = {
    "provider": "astron",
    "models": {
        "deepseek": {
            "url": "https://api.deepseek.com/chat/completions",
            "key": os.environ.get("DEEPSEEK_API_KEY", ""),
            "model": "deepseek-chat",
            "maxTokens": 512,
            "temperature": 0.3,
        },
        "iflytek": {
            "url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",
            "key": os.environ.get("IFLYTEK_API_KEY", ""),
            "model": "4.0Ultra",
            "maxTokens": 512,
            "temperature": 0.3,
        },
        "astron": {
            "url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",
            "key": os.environ.get("ASTRON_API_KEY", ""),
            "model": "astron-code-latest",
            "maxTokens": 32768,
            "temperature": 0.3,
        },
    },
}

# ===== 导入模块 =====
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag.rag_service import SimpleRAG
_rag = SimpleRAG()

# 硬件控制桥接
try:
    from hardware_bridge import (
        hw_toggle, hw_control, hw_sensor_read, hw_scene_execute,
        hw_all_status, hw_living_status, hw_kitchen_status,
        hw_bathroom_status, hw_bedroom_status,
        _DEVICE_NAMES as _HW_DEV_NAMES
    )
    _HW_OK = True
except ImportError:
    _HW_OK = False
    hw_toggle = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_control = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_sensor_read = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_scene_execute = lambda *a, **kw: []
    hw_all_status = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_living_status = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_kitchen_status = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_bathroom_status = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_bedroom_status = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    _HW_DEV_NAMES = {}

# ===== 设备定义 (只保留真实硬件) =====
# 每个设备必须对应一块真实板子，离线=关+没有
DEVICE_DEFS = [
    # 客厅 - Hi3861 192.168.1.62:8000
    {"id": "light_01", "name": "客厅主灯",   "type": "light",  "room": "客厅", "icon": "lightbulb",      "area": "living_room"},
    {"id": "light_05", "name": "客厅氛围灯", "type": "light",  "room": "客厅", "icon": "lightbulb",      "area": "living_room"},
    {"id": "ac_01",    "name": "客厅空调",   "type": "ac",     "room": "客厅", "icon": "air_fill",        "area": "living_room"},
    {"id": "door_01",  "name": "客厅大门",   "type": "door",   "room": "客厅", "icon": "lock",            "area": "living_room"},
    {"id": "alarm_01", "name": "蜂鸣警报",   "type": "alarm",  "room": "客厅", "icon": "bell_fill",       "area": "living_room"},
    # 厨房 - H3863 192.168.1.23:8000
    {"id": "light_02", "name": "厨房灯",     "type": "light",  "room": "厨房", "icon": "lightbulb",       "area": "kitchen"},
    # 卫生间 - H3863 192.168.1.63:8000
    {"id": "light_04", "name": "卫生间灯",   "type": "light",  "room": "卫生间", "icon": "lightbulb",     "area": "bathroom"},
    {"id": "fan_02",   "name": "换气扇",     "type": "fan",    "room": "卫生间", "icon": "fan_fill_1",   "area": "bathroom"},
    # 卧室 - H3863 192.168.1.64:8000
    {"id": "light_03", "name": "卧室灯",     "type": "light",  "room": "卧室", "icon": "lightbulb",       "area": "bedroom"},
    {"id": "curtain_01","name": "智能窗帘",  "type": "curtain","room": "卧室", "icon": "lock_open_fill",  "area": "bedroom"},
]

SENSOR_DEFS = [
    {"id": "temp_01",  "name": "客厅温度", "type": "temperature", "group": "环境监测", "room": "客厅", "icon": "thermometer", "unit": "°C",  "thresholdMax": 28, "area": "living_room"},
    {"id": "humid_01", "name": "客厅湿度", "type": "humidity",    "group": "环境监测", "room": "客厅", "icon": "drop",        "unit": "%RH", "thresholdMax": 70, "area": "living_room"},
    {"id": "smoke_01", "name": "烟雾检测", "type": "smoke",       "group": "安防",     "room": "厨房", "icon": "flame_fill",  "unit": "正常", "area": "kitchen"},
    {"id": "heat_01",  "name": "热敏火灾", "type": "heat",        "group": "安防",     "room": "厨房", "icon": "flame_fill",  "unit": "mV",   "area": "kitchen"},
    {"id": "air_01",   "name": "综合报警", "type": "air_quality", "group": "安防",     "room": "厨房", "icon": "wind",        "unit": "",     "area": "kitchen"},
]

# 区域定义: 每个区域对应一块板子
AREA_DEFS = {
    "living_room": {"name": "客厅", "ip": "192.168.1.62", "port": 8000, "device": "Hi3861"},
    "kitchen":     {"name": "厨房", "ip": "192.168.1.23", "port": 8000, "device": "H3863", "udp_port": 8001},
    "bathroom":    {"name": "卫生间", "ip": "192.168.1.63", "port": 8000, "device": "H3863"},
    "bedroom":     {"name": "卧室", "ip": "192.168.1.64", "port": 8000, "device": "H3863"},
}

_DEVICE_NAMES = {d["id"]: d["name"] for d in DEVICE_DEFS}

# ===== 实时状态缓存: 只有检查到才有值，否则null =====
_DEVICE_STATUS = {}   # device_id -> {"is_on": bool, "primary_value": int, "online": bool, "ts": float, ...}  online=false时其他字段无效
_SENSOR_STATUS = {}   # sensor_id -> {"value": float, "unit": str, "online": bool, "ts": float, "is_alert": bool}  online=false时其他字段无效
_AREA_ONLINE = {}     # area_id -> bool
_STATUS_LOCK = threading.Lock()

# ===== 厨房报警联动 =====
_last_kitchen_alarm = 0
_ALARM_LOCK = threading.Lock()
_KITCHEN_POLL_INTERVAL = 1.0   # 厨房1秒轮询(按交接文档)
_OTHER_POLL_INTERVAL = 10.0    # 其他区域10秒轮询

def log(m):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def now_ms():
    return int(time.time() * 1000)

# ===== TTS 语音输出 (只负责播报，输入由/api/voice/input) =====
def _tts_speak(text):
    """播放语音输出。TTS只管输出(播报)，语音输入由前端ASR→/api/voice/input"""
    if not text:
        return
    def _speak():
        try:
            from channel import tts_speak as _ch_tts
            _ch_tts(text)
        except Exception:
            pass
    threading.Thread(target=_speak, daemon=True).start()

def _vs_entry(text):
    h = hashlib.md5(f"{text}_7".encode()).hexdigest()
    return {"text": text, "audioUrl": f"/api/tts/audio/{h}.mp3"}

# ===== 数据库 =====
def db_init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text("utf-8"))
    conn.commit(); conn.close()

def _db():
    return sqlite3.connect(str(DB_PATH))

# ===== 真实硬件轮询 =====
def _poll_living():
    """轮询客厅设备"""
    online = False
    # 温湿度
    try:
        r = hw_sensor_read("temp_01")
        if r["success"] and "temp" in r.get("data", {}):
            d = r["data"]
            online = True
            with _STATUS_LOCK:
                _SENSOR_STATUS["temp_01"] = {"value": d["temp"], "unit": "°C", "online": True, "ts": time.time(), "is_alert": d["temp"] > 28, "raw_temp": d["temp"]}
                if "humidity" in d:
                    _SENSOR_STATUS["humid_01"] = {"value": d["humidity"], "unit": "%RH", "online": True, "ts": time.time(), "is_alert": d["humidity"] > 70, "raw_humidity": d["humidity"]}
    except Exception:
        with _STATUS_LOCK:
            _SENSOR_STATUS["temp_01"] = {"online": False}
            _SENSOR_STATUS["humid_01"] = {"online": False}

    # 客厅灯
    try:
        r = hw_living_status("light")
        if r["success"]:
            online = True
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else str(r.get("data", ""))
            is_on = "ON" in reply.upper() or "开" in reply
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_01"] = {"is_on": is_on, "primary_value": 100 if is_on else 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["light_01"] = {"online": False}

    # 空调
    try:
        r = hw_living_status("ac")
        if r["success"]:
            online = True
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else ""
            is_on = "ON" in reply.upper() or "开" in reply
            with _STATUS_LOCK:
                _DEVICE_STATUS["ac_01"] = {"is_on": is_on, "primary_value": 24, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["ac_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["ac_01"] = {"online": False}

    # 门
    try:
        r = hw_living_status("door")
        if r["success"]:
            online = True
            state = r.get("data", {}).get("state", "closed") if isinstance(r.get("data"), dict) else "closed"
            with _STATUS_LOCK:
                _DEVICE_STATUS["door_01"] = {"is_on": state == "open", "primary_value": 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["door_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["door_01"] = {"online": False}

    # 蜂鸣器
    try:
        r = hw_living_status("beep")
        if r["success"]:
            online = True
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else ""
            is_on = "ALARM" in reply.upper() or "ON" in reply.upper()
            with _STATUS_LOCK:
                _DEVICE_STATUS["alarm_01"] = {"is_on": is_on, "primary_value": 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["alarm_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["alarm_01"] = {"online": False}

    with _STATUS_LOCK:
        _AREA_ONLINE["living_room"] = online
    if online:
        log("[POLL] 客厅在线")


def _poll_kitchen():
    """轮询厨房 — 按交接文档联动规则"""
    online = False
    try:
        r = hw_kitchen_status()
        if r["success"]:
            online = True
            d = r.get("data", {})
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_02"] = {
                    "is_on": d.get("light_on", 0) > 0 or d.get("brightness", 0) > 0,
                    "primary_value": d.get("brightness", 0),
                    "online": True, "ts": time.time()
                }
                _SENSOR_STATUS["smoke_01"] = {
                    "value": d.get("smoke_alarm", 0),
                    "unit": "报警" if d.get("smoke_alarm", 0) else "正常",
                    "online": True, "ts": time.time(),
                    "is_alert": d.get("smoke_alarm", 0) == 1,
                    "smoke_level": d.get("smoke_level", 0),
                }
                _SENSOR_STATUS["heat_01"] = {
                    "value": d.get("thermal_mv", 0),
                    "unit": "mV",
                    "online": True, "ts": time.time(),
                    "is_alert": d.get("temp_alarm", 0) == 1,
                    "temp_alarm": d.get("temp_alarm", 0),
                    "thermal_mv": d.get("thermal_mv", 0),
                }
                _SENSOR_STATUS["air_01"] = {
                    "value": d.get("alarm", 0),
                    "unit": "综合报警",
                    "online": True, "ts": time.time(),
                    "is_alert": d.get("alarm", 0) == 1,
                    "alarm": d.get("alarm", 0),
                }

            # 厨房报警联动 (按交接文档规则)
            alarm_now = d.get("alarm", 0)
            with _ALARM_LOCK:
                global _last_kitchen_alarm
                if alarm_now == 1 and _last_kitchen_alarm == 0:
                    # 上升沿 → BEEP ALARM
                    hw_toggle("alarm_01", True)
                    _tts_speak("厨房检测到异常，已触发警报")
                    log("[ALARM] 厨房报警上升沿 alarm=1 → 客厅 BEEP ALARM")
                    # 记录报警事件到数据库
                    try:
                        conn = _db()
                        conn.execute("INSERT INTO device_operations(device_id,action,params_json,result,source) VALUES(?,?,?,?,'alarm_linkage')",
                                     ("alarm_01", "alarm_linkage", json.dumps({"trigger": "kitchen_alarm_rising", "smoke_alarm": d.get("smoke_alarm"), "temp_alarm": d.get("temp_alarm")}), "ok"))
                        conn.commit(); conn.close()
                    except Exception:
                        pass
                elif alarm_now == 0 and _last_kitchen_alarm == 1:
                    # 下降沿 → BEEP OFF
                    hw_toggle("alarm_01", False)
                    _tts_speak("厨房报警已恢复，警报已关闭")
                    log("[ALARM] 厨房报警恢复 alarm=0 → 客厅 BEEP OFF")
                # 同一持续报警不重复触发
                _last_kitchen_alarm = alarm_now

            log(f"[POLL] 厨房在线 alarm={alarm_now} smoke={d.get('smoke_alarm',0)} thermal={d.get('thermal_mv',0)}mV brightness={d.get('brightness',0)}")
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_02"] = {"online": False}
                _SENSOR_STATUS["smoke_01"] = {"online": False}
                _SENSOR_STATUS["heat_01"] = {"online": False}
                _SENSOR_STATUS["air_01"] = {"online": False}
    except Exception as e:
        log(f"[POLL] 厨房轮询异常: {e}")
        with _STATUS_LOCK:
            _DEVICE_STATUS["light_02"] = {"online": False}
            _SENSOR_STATUS["smoke_01"] = {"online": False}
            _SENSOR_STATUS["heat_01"] = {"online": False}
            _SENSOR_STATUS["air_01"] = {"online": False}

    with _STATUS_LOCK:
        _AREA_ONLINE["kitchen"] = online


def _poll_bathroom():
    """轮询卫生间"""
    online = False
    try:
        r = hw_bathroom_status()
        if r["success"]:
            online = True
            d = r.get("data", {})
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_04"] = {
                    "is_on": d.get("light_brightness", 0) > 0,
                    "primary_value": d.get("light_brightness", 0),
                    "online": True, "ts": time.time()
                }
                _DEVICE_STATUS["fan_02"] = {
                    "is_on": d.get("motor_running", 0) == 1,
                    "primary_value": d.get("motor_speed", 0),
                    "online": True, "ts": time.time(),
                    "motor_direction": d.get("motor_direction", 0),
                }
            log(f"[POLL] 卫生间在线 brightness={d.get('light_brightness',0)} motor={d.get('motor_running',0)} speed={d.get('motor_speed',0)}")
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_04"] = {"online": False}
                _DEVICE_STATUS["fan_02"] = {"online": False}
    except Exception as e:
        log(f"[POLL] 卫生间轮询异常: {e}")
        with _STATUS_LOCK:
            _DEVICE_STATUS["light_04"] = {"online": False}
            _DEVICE_STATUS["fan_02"] = {"online": False}

    with _STATUS_LOCK:
        _AREA_ONLINE["bathroom"] = online


def _poll_bedroom():
    """轮询卧室"""
    online = False
    try:
        r = hw_bedroom_status()
        if r["success"]:
            online = True
            d = r.get("data", {})
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_03"] = {
                    "is_on": d.get("light_brightness", 0) > 0,
                    "primary_value": d.get("light_brightness", 0),
                    "online": True, "ts": time.time()
                }
                _DEVICE_STATUS["curtain_01"] = {
                    "is_on": d.get("curtain_position", 0) > 0,
                    "primary_value": d.get("curtain_position", 0),
                    "online": True, "ts": time.time(),
                    "curtain_moving": d.get("curtain_moving", 0),
                    "curtain_homed": d.get("curtain_homed", 0),
                    "close_limit": d.get("close_limit", 0),
                    "open_limit": d.get("open_limit", 0),
                }
            log(f"[POLL] 卧室在线 brightness={d.get('light_brightness',0)} curtain={d.get('curtain_position',0)} homed={d.get('curtain_homed',0)}")
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_03"] = {"online": False}
                _DEVICE_STATUS["curtain_01"] = {"online": False}
    except Exception as e:
        log(f"[POLL] 卧室轮询异常: {e}")
        with _STATUS_LOCK:
            _DEVICE_STATUS["light_03"] = {"online": False}
            _DEVICE_STATUS["curtain_01"] = {"online": False}

    with _STATUS_LOCK:
        _AREA_ONLINE["bedroom"] = online


def sensor_poll_thread():
    """后台线程: 厨房1秒轮询(联动)，其他10秒"""
    log("[POLL] 传感器轮询线程启动 (厨房1秒/其他10秒)")
    last_other = 0
    while True:
        now = time.time()
        # 厨房每1秒轮询
        _poll_kitchen()
        # 其他区域每10秒轮询
        if now - last_other >= _OTHER_POLL_INTERVAL:
            _poll_living()
            _poll_bathroom()
            _poll_bedroom()
            _save_sensor_readings()
            last_other = now
        time.sleep(_KITCHEN_POLL_INTERVAL)


def _save_sensor_readings():
    """传感器数据入库"""
    try:
        conn = _db()
        with _STATUS_LOCK:
            for sid, sdata in _SENSOR_STATUS.items():
                if sdata.get("online") and "value" in sdata:
                    conn.execute(
                        "INSERT INTO sensor_readings(sensor_id, value, unit, created_at) VALUES(?,?,?,datetime('now'))",
                        (sid, sdata["value"], sdata.get("unit", ""))
                    )
        conn.commit(); conn.close()
    except Exception:
        pass


# ===== UDP 8001 监听 =====
_UDP_LISTENING = False
def udp_alarm_listener():
    """后台线程: 监听厨房UDP 8001广播"""
    UDP_PORT = 8001
    try:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.bind(("", UDP_PORT))
        udp_sock.setblocking(False)
        log(f"[UDP] 厨房报警监听已启动 :{UDP_PORT}")
    except OSError as e:
        log(f"[UDP] 监听启动失败: {e}")
        return

    while True:
        try:
            data, addr = udp_sock.recvfrom(1024)
            text = data.decode("utf-8", errors="replace").strip()
            log(f"[UDP] 厨房报警 from {addr[0]}: {text}")
            with _ALARM_LOCK:
                global _last_kitchen_alarm
                if _last_kitchen_alarm == 0:
                    _last_kitchen_alarm = 1
                    hw_toggle("alarm_01", True)
                    _tts_speak("厨房UDP报警，已触发警报")
                    log("[ALARM] UDP报警 → 客厅 BEEP ALARM")
        except BlockingIOError:
            pass
        except Exception as e:
            log(f"[UDP] 接收错误: {e}")
        time.sleep(0.1)


# ===== AI 对话 =====
_SYSTEM_PROMPT = """你是智慧家居助手，严格遵守以下规则：

## 身份
你控制4个区域的智慧家居设备：客厅(192.168.1.62)、厨房(192.168.1.23)、卫生间(192.168.1.63)、卧室(192.168.1.64)。

## 离线规则
- 设备离线=关闭=没有数据，不要编造任何数据
- 离线时明确说"设备离线"，不显示默认值

## 输出格式

### 状态查询
[客厅]
  温度: X°C / 设备离线
  湿度: X%RH / 设备离线
  客厅灯: 开/关/离线
  空调: 开/关/离线
  大门: 开/关/离线
  蜂鸣器: 开/关/离线

[厨房]
  烟雾: 正常/报警/离线
  热敏: XmV/离线
  厨房灯: 开(亮度X%)/关/离线

[卫生间]
  卫生间灯: 开(亮度X%)/关/离线
  换气扇: 开(风速X%)/关/离线

[卧室]
  卧室灯: 开(亮度X%)/关/离线
  窗帘: 位置X%/离线

### 设备控制
[操作结果] XX已开启/关闭成功
[设备状态] XX: 开启/关闭/离线

### 厨房报警
[报警] 厨房检测到异常！
[联动] 已触发客厅蜂鸣器

## 约束
1. 只回答智能家居相关
2. 不编造数据
3. 回复不超过200字
"""

def chat(msgs):
    provider = _AI_CONFIG.get("provider", "deepseek")
    prov_cfg = _AI_CONFIG.get("models", {}).get(provider, {})
    ai_url = prov_cfg.get("url", "")
    ai_key = prov_cfg.get("key", "")
    ai_model = prov_cfg.get("model", "deepseek-chat")
    ai_max_tokens = prov_cfg.get("maxTokens", 512)
    ai_temp = prov_cfg.get("temperature", 0.3)

    if not ai_url or not ai_key:
        return "（未配置AI）"

    last_msg = msgs[-1].get("content", "") if msgs else ""
    rag_ctx = _rag.get_context(last_msg)

    # 实时设备状态上下文
    with _STATUS_LOCK:
        status_parts = []
        for area_id, area_info in AREA_DEFS.items():
            area_online = _AREA_ONLINE.get(area_id, False)
            parts = [f"{area_info['name']}({area_info['ip']}): {'在线' if area_online else '离线'}"]
            for d in DEVICE_DEFS:
                if d["area"] == area_id:
                    cached = _DEVICE_STATUS.get(d["id"], {})
                    if cached.get("online"):
                        parts.append(f"  {d['name']}: {'开' if cached.get('is_on') else '关'}")
                    else:
                        parts.append(f"  {d['name']}: 离线")
            for s in SENSOR_DEFS:
                if s["area"] == area_id:
                    cached = _SENSOR_STATUS.get(s["id"], {})
                    if cached.get("online"):
                        parts.append(f"  {s['name']}: {cached.get('value', '?')}{cached.get('unit', '')}")
                    else:
                        parts.append(f"  {s['name']}: 离线")
            status_parts.append("\n".join(parts))
    status_ctx = "\n\n".join(status_parts)

    sys_msg = _SYSTEM_PROMPT + f"\n\n## 当前实时设备状态\n{status_ctx}\n"
    if rag_ctx:
        sys_msg += f"\n## RAG: {rag_ctx}\n"

    body = {
        "model": ai_model,
        "messages": [{"role": "system", "content": sys_msg}] + msgs,
        "temperature": ai_temp,
        "max_tokens": ai_max_tokens,
    }
    req = Request(ai_url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                  headers={"Authorization": f"Bearer {ai_key}", "Content-Type": "application/json"}, method="POST")
    try:
        _ssl_ctx = ssl.create_default_context(cafile="/data/A9/certs/cacert.pem")
        with urlopen(req, timeout=30, context=_ssl_ctx) as r:
            resp = json.loads(r.read().decode("utf-8"))
            reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not reply:
                reply = json.dumps(resp, ensure_ascii=False)[:200]
            return reply
    except Exception as e:
        log(f"[CHAT] {e}")
        return f"（AI暂时不可用: {e}）"


# ===== HTTP 路由 =====
class H(BaseHTTPRequestHandler):
    def _j(self, c, d):
        try:
            b = json.dumps(d, ensure_ascii=False).encode("utf-8")
            self.send_response(c)
            self.send_header("Content-Type", "application/json;charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b)
        except BrokenPipeError:
            pass
        except Exception:
            pass

    def _b(self):
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._j(200, {"ok": True})

    def log_message(self, *a):
        log(f"{self.command} {self.path}")

    def do_GET(self):
        p = self.path.split("?")[0]
        try:
            if p == "/health":
                self._j(200, {"ok": True, "v": 5, "hardware": _HW_OK})
            elif p == "/api/devices":
                self._j(200, self._get_devices())
            elif p == "/api/sensors":
                self._j(200, self._get_sensors())
            elif p == "/api/cameras":
                self._j(200, [{"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "offline"}])
            elif p == "/api/alerts":
                self._j(200, self._get_alerts())
            elif p == "/api/user/profile":
                self._j(200, self._get_user())
            elif p == "/api/operations":
                qs = self.path.split("?", 1); did = None; days = 7
                if len(qs) > 1:
                    for kv in qs[1].split("&"):
                        k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                        if k == "device_id": did = v
                        if k == "days": days = int(v)
                self._j(200, self._get_operations(did, days))
            elif p == "/api/sensors/history":
                self._j(200, self._get_sensor_history())
            elif p == "/api/server/status":
                self._j(200, {
                    "host": "192.168.1.81", "port": PORT, "isOnline": True,
                    "protocol": "wifi", "version": "v5",
                    "hardware": _HW_OK,
                    "pollIntervalKitchen": _KITCHEN_POLL_INTERVAL,
                    "pollIntervalOther": _OTHER_POLL_INTERVAL
                })
            elif p == "/api/check":
                self._j(200, self._check_all())
            elif p == "/api/hardware/status":
                self._j(200, self._hardware_check())
            elif p == "/api/rag/stats":
                self._j(200, _rag.get_stats())
            elif p == "/api/stats":
                self._j(200, self._get_stats())
            # TTS语音输出代理
            elif p == "/api/tts/config":
                self._proxy_get("http://127.0.0.1:8081/tts/config")
            elif p == "/api/tts/list":
                self._proxy_get("http://127.0.0.1:8081/tts/list")
            elif p == "/api/tts/text_map":
                self._proxy_get("http://127.0.0.1:8081/tts/text_map")
            elif p == "/api/tts/cache":
                self._proxy_get("http://127.0.0.1:8081/tts/cache")
            elif p.startswith("/api/tts/audio/"):
                fname = p.split("/")[-1]
                self._proxy_get(f"http://127.0.0.1:8081/tts/audio/{fname}", binary=True)
            elif p == "/api/ai/config":
                self._proxy_get("http://127.0.0.1:8081/ai/config")
            else:
                self._j(404, {"error": "nf"})
        except Exception as e:
            self._j(500, {"error": str(e)})

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._b()
        try:
            if p == "/api/chat/send":
                self._j(200, self._chat(body))
            elif p == "/api/voice/input":
                self._j(200, self._voice_input(body))
            elif p == "/api/door/control":
                self._j(200, self._door_control(body))
            elif p == "/api/user/profile":
                self._j(200, self._update_user(body))
            elif p == "/api/rag/search":
                self._j(200, {"results": _rag.search(body.get("query", ""), n=body.get("n_results", 5))})
            else:
                m = re.match(r"^/api/devices/([\w_]+)/control$", p)
                if m:
                    self._j(200, self._control_device(m.group(1), body))
                    return
                m = re.match(r"^/api/devices/([\w_]+)/toggle$", p)
                if m:
                    self._j(200, self._toggle_device(m.group(1), body))
                    return
                # TTS/AI代理
                if p in ("/api/tts/config", "/api/tts/test", "/api/tts/speak",
                         "/api/ai/config", "/api/ai/test"):
                    self._proxy_post(f"http://127.0.0.1:8081{p}", body)
                else:
                    self._j(404, {"error": "nf"})
        except Exception as e:
            self._j(500, {"error": str(e)})

    # ===== 代理 =====
    def _proxy_get(self, url, binary=False):
        try:
            import urllib.request as _ureq
            with _ureq.urlopen(url, timeout=5) as _ur:
                if binary:
                    data = _ur.read()
                    ct = _ur.headers.get("Content-Type", "audio/mpeg")
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._j(200, json.loads(_ur.read().decode()))
        except Exception as _e:
            if not binary:
                self._j(200, {"error": str(_e)})

    def _proxy_post(self, url, body):
        try:
            import urllib.request as _ureq
            _bd = json.dumps(body, ensure_ascii=False).encode()
            _req = _ureq.Request(url, data=_bd, headers={"Content-Type": "application/json"})
            with _ureq.urlopen(_req, timeout=30) as _ur:
                self._j(200, json.loads(_ur.read().decode()))
        except Exception as _e:
            self._j(500, {"ok": False, "error": str(_e)})

    # ===== 设备列表: 离线=关+没有 =====
    def _get_devices(self):
        result = []
        with _STATUS_LOCK:
            for d in DEVICE_DEFS:
                cached = _DEVICE_STATUS.get(d["id"], {})
                online = cached.get("online", False)
                if online:
                    entry = {
                        "id": d["id"], "name": d["name"], "type": d["type"],
                        "status": "online", "room": d["room"], "icon": d["icon"],
                        "isOn": cached.get("is_on", False),
                        "primaryValue": cached.get("primary_value", 0),
                    }
                    for k in ("motor_direction", "curtain_moving", "curtain_homed", "close_limit", "open_limit"):
                        if k in cached:
                            entry[k] = cached[k]
                else:
                    # 离线=关+没有
                    entry = {
                        "id": d["id"], "name": d["name"], "type": d["type"],
                        "status": "offline", "room": d["room"], "icon": d["icon"],
                        "isOn": False, "primaryValue": None,
                    }
                result.append(entry)
        return result

    def _get_sensors(self):
        result = []
        with _STATUS_LOCK:
            for s in SENSOR_DEFS:
                cached = _SENSOR_STATUS.get(s["id"], {})
                online = cached.get("online", False)
                if online:
                    entry = {
                        "id": s["id"], "name": s["name"], "type": s["type"],
                        "group": s["group"], "room": s["room"], "icon": s["icon"],
                        "current": {"value": cached.get("value"), "unit": cached.get("unit", s["unit"])},
                        "isAlert": cached.get("is_alert", False),
                    }
                    for k in ("smoke_level", "temp_alarm"):
                        if k in cached:
                            entry[k] = cached[k]
                else:
                    # 离线=没有数据
                    entry = {
                        "id": s["id"], "name": s["name"], "type": s["type"],
                        "group": s["group"], "room": s["room"], "icon": s["icon"],
                        "current": None, "isAlert": False,
                    }
                if "thresholdMax" in s:
                    entry["thresholdMax"] = s["thresholdMax"]
                result.append(entry)
        return result

    def _get_alerts(self):
        """基于真实传感器的活跃告警"""
        alerts = []
        with _STATUS_LOCK:
            smoke = _SENSOR_STATUS.get("smoke_01", {})
            if smoke.get("online") and smoke.get("is_alert"):
                alerts.append({"id": "alert_smoke", "source": "烟雾检测", "content": "厨房烟雾报警！", "level": "critical", "isRead": False, "timestamp": now_ms()})
            heat = _SENSOR_STATUS.get("heat_01", {})
            if heat.get("online") and heat.get("is_alert"):
                alerts.append({"id": "alert_heat", "source": "热敏火灾", "content": f"厨房热敏异常: {heat.get('value', '?')}mV", "level": "critical", "isRead": False, "timestamp": now_ms()})
            temp = _SENSOR_STATUS.get("temp_01", {})
            if temp.get("online") and temp.get("is_alert"):
                alerts.append({"id": "alert_temp", "source": "客厅温度", "content": f"温度异常: {temp.get('value', '?')}°C", "level": "warning", "isRead": False, "timestamp": now_ms()})
            humid = _SENSOR_STATUS.get("humid_01", {})
            if humid.get("online") and humid.get("is_alert"):
                alerts.append({"id": "alert_humid", "source": "客厅湿度", "content": f"湿度异常: {humid.get('value', '?')}%RH", "level": "warning", "isRead": False, "timestamp": now_ms()})
        return alerts

    def _get_user(self):
        conn = _db()
        r = conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        dc = len(DEVICE_DEFS)
        conn.close()
        if not r:
            return {"id": "u001", "nickname": "用户", "homeName": "我的家", "memberCount": 3, "deviceCount": dc}
        return {"id": r[0], "nickname": r[1], "homeName": r[2], "memberCount": r[3], "deviceCount": dc}

    def _get_operations(self, device_id=None, days=7):
        conn = _db()
        time_filter = f"datetime('now','-{days} days')"
        if device_id:
            rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE device_id=? AND created_at>={time_filter} ORDER BY created_at DESC LIMIT 200", (device_id,)).fetchall()
        else:
            rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE created_at>={time_filter} ORDER BY created_at DESC LIMIT 200").fetchall()
        conn.close()
        return [{"device_id": r[0], "action": r[1], "params": r[2], "result": r[3], "source": r[4], "scene_id": r[5], "timestamp": r[6]} for r in rows]

    def _get_sensor_history(self):
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT sensor_id, value, unit, created_at FROM sensor_readings "
                "WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
            conn.close()
            grouped = {}
            for r in rows:
                sid = r[0]
                if sid not in grouped:
                    grouped[sid] = []
                grouped[sid].append({"value": r[1], "unit": r[2], "timestamp": r[3]})
            return {"sensors": grouped, "total": len(rows)}
        except Exception as e:
            conn.close()
            return {"sensors": {}, "total": 0, "error": str(e)}

    # ===== 10+类统计数据 =====
    def _get_stats(self):
        """统计接口：10类真实状态数据，设备未接入不写入模拟数据
        只有设备在线时才返回真实值，离线字段为null
        """
        stats = {
            "timestamp": datetime.now().isoformat(),
            "poll_interval_kitchen": _KITCHEN_POLL_INTERVAL,
            "poll_interval_other": _OTHER_POLL_INTERVAL,
        }

        with _STATUS_LOCK:
            # 1. 设备在线率
            total_devices = len(DEVICE_DEFS)
            online_devices = sum(1 for d in DEVICE_DEFS if _DEVICE_STATUS.get(d["id"], {}).get("online"))
            stats["device_online_rate"] = {
                "total": total_devices,
                "online": online_devices,
                "offline": total_devices - online_devices,
                "rate": round(online_devices / total_devices * 100, 1) if total_devices else 0,
            }

            # 2. 区域连通状态
            stats["area_connectivity"] = {}
            for area_id, area_info in AREA_DEFS.items():
                online = _AREA_ONLINE.get(area_id, False)
                stats["area_connectivity"][area_id] = {
                    "name": area_info["name"],
                    "ip": area_info["ip"],
                    "port": area_info["port"],
                    "online": online,
                    "last_seen": None,
                }
                # 从该区域任意设备取最后在线时间
                for d in DEVICE_DEFS:
                    if d["area"] == area_id:
                        ts = _DEVICE_STATUS.get(d["id"], {}).get("ts")
                        if ts:
                            stats["area_connectivity"][area_id]["last_seen"] = datetime.fromtimestamp(ts).isoformat()
                            break

            # 3. 客厅温度 (来自TEMP QUERY)
            temp_cached = _SENSOR_STATUS.get("temp_01", {})
            stats["living_temperature"] = {
                "value": temp_cached.get("raw_temp") if temp_cached.get("online") else None,
                "unit": "°C",
                "online": temp_cached.get("online", False),
                "is_alert": temp_cached.get("is_alert") if temp_cached.get("online") else None,
                "threshold": 28,
            }

            # 4. 客厅湿度 (来自TEMP QUERY)
            humid_cached = _SENSOR_STATUS.get("humid_01", {})
            stats["living_humidity"] = {
                "value": humid_cached.get("raw_humidity") if humid_cached.get("online") else None,
                "unit": "%RH",
                "online": humid_cached.get("online", False),
                "is_alert": humid_cached.get("is_alert") if humid_cached.get("online") else None,
                "threshold": 70,
            }

            # 5. 厨房烟雾状态 (CMD4: smoke_level, smoke_alarm)
            smoke_cached = _SENSOR_STATUS.get("smoke_01", {})
            stats["kitchen_smoke"] = {
                "smoke_level": smoke_cached.get("smoke_level") if smoke_cached.get("online") else None,
                "smoke_alarm": smoke_cached.get("is_alert") if smoke_cached.get("online") else None,
                "online": smoke_cached.get("online", False),
                "description": "GP03低电平报警" if smoke_cached.get("online") else None,
            }

            # 6. 厨房热敏ADC (CMD4: thermal_mv, temp_alarm)
            heat_cached = _SENSOR_STATUS.get("heat_01", {})
            stats["kitchen_thermal"] = {
                "thermal_mv": heat_cached.get("thermal_mv") if heat_cached.get("online") else None,
                "temp_alarm": heat_cached.get("temp_alarm") if heat_cached.get("online") else None,
                "online": heat_cached.get("online", False),
                "threshold_mv": 1400,
                "description": "ADC≤1400mV报警" if heat_cached.get("online") else None,
            }

            # 7. 厨房综合报警 (CMD4: alarm字段)
            air_cached = _SENSOR_STATUS.get("air_01", {})
            stats["kitchen_alarm"] = {
                "alarm": air_cached.get("alarm") if air_cached.get("online") else None,
                "online": air_cached.get("online", False),
                "description": "1=烟雾或过热任一报警" if air_cached.get("online") else None,
            }

            # 8. 卫生间电机/风扇 (CMD6: motor_direction, motor_speed, motor_running)
            fan_cached = _DEVICE_STATUS.get("fan_02", {})
            stats["bathroom_fan"] = {
                "motor_running": fan_cached.get("is_on") if fan_cached.get("online") else None,
                "motor_speed": fan_cached.get("primary_value") if fan_cached.get("online") else None,
                "motor_direction": fan_cached.get("motor_direction") if fan_cached.get("online") else None,
                "online": fan_cached.get("online", False),
                "direction_label": {0: "停止", 1: "正转", 2: "反转"}.get(fan_cached.get("motor_direction", 0)) if fan_cached.get("online") else None,
            }

            # 9. 卧室窗帘位置 (CMD9: curtain_position, curtain_moving, curtain_homed, limits)
            curtain_cached = _DEVICE_STATUS.get("curtain_01", {})
            stats["bedroom_curtain"] = {
                "position": curtain_cached.get("primary_value") if curtain_cached.get("online") else None,
                "moving": curtain_cached.get("curtain_moving") if curtain_cached.get("online") else None,
                "homed": curtain_cached.get("curtain_homed") if curtain_cached.get("online") else None,
                "close_limit": curtain_cached.get("close_limit") if curtain_cached.get("online") else None,
                "open_limit": curtain_cached.get("open_limit") if curtain_cached.get("online") else None,
                "online": curtain_cached.get("online", False),
            }

            # 10. 所有灯亮度汇总
            stats["all_lights"] = {}
            for d in DEVICE_DEFS:
                if d["type"] == "light":
                    cached = _DEVICE_STATUS.get(d["id"], {})
                    if cached.get("online"):
                        stats["all_lights"][d["id"]] = {
                            "name": d["name"],
                            "room": d["room"],
                            "brightness": cached.get("primary_value"),
                            "is_on": cached.get("is_on"),
                            "online": True,
                        }
                    else:
                        stats["all_lights"][d["id"]] = {
                            "name": d["name"],
                            "room": d["room"],
                            "brightness": None,
                            "is_on": None,
                            "online": False,
                        }

            # 11. 厨房报警联动状态
            stats["alarm_linkage"] = {
                "last_kitchen_alarm": _last_kitchen_alarm,
                "buzzer_triggered": _DEVICE_STATUS.get("alarm_01", {}).get("is_on") if _DEVICE_STATUS.get("alarm_01", {}).get("online") else None,
                "udp_listening": _UDP_LISTENING,
                "rule": "alarm 0→1: BEEP ALARM / alarm 1→0: BEEP OFF / 不重复触发",
            }

            # 12. 报警事件计数(最近24小时从数据库读)
            try:
                conn = _db()
                alarm_count = conn.execute(
                    "SELECT COUNT(*) FROM device_operations WHERE action='alarm_linkage' AND created_at >= datetime('now', '-1 day')"
                ).fetchone()[0]
                conn.close()
                stats["alarm_linkage"]["events_24h"] = alarm_count
            except Exception:
                stats["alarm_linkage"]["events_24h"] = None

        log(f"[STATS] online={stats['device_online_rate']['online']}/{total_devices} alarm={stats['kitchen_alarm'].get('alarm')}")
        return stats

    # ===== 设备连通检查 =====
    def _check_all(self):
        """检查所有区域设备连通状态，返回详细信息，并语音播报"""
        check_result = {
            "timestamp": datetime.now().isoformat(),
            "areas": [],
            "online_count": 0,
            "offline_count": 0,
            "devices_online": [],
            "devices_offline": [],
        }

        with _STATUS_LOCK:
            for area_id, area_info in AREA_DEFS.items():
                online = _AREA_ONLINE.get(area_id, False)
                area_data = {
                    "id": area_id,
                    "name": area_info["name"],
                    "ip": area_info["ip"],
                    "port": area_info["port"],
                    "device_type": area_info["device"],
                    "online": online,
                    "devices": [],
                    "sensors": [],
                }
                if online:
                    check_result["online_count"] += 1
                    check_result["devices_online"].append(f"{area_info['name']}({area_info['ip']})")
                else:
                    check_result["offline_count"] += 1
                    check_result["devices_offline"].append(f"{area_info['name']}({area_info['ip']})")

                for d in DEVICE_DEFS:
                    if d["area"] == area_id:
                        cached = _DEVICE_STATUS.get(d["id"], {})
                        dev_data = {"id": d["id"], "name": d["name"], "online": cached.get("online", False)}
                        if cached.get("online"):
                            dev_data["isOn"] = cached.get("is_on", False)
                            dev_data["primaryValue"] = cached.get("primary_value")
                        area_data["devices"].append(dev_data)

                for s in SENSOR_DEFS:
                    if s["area"] == area_id:
                        cached = _SENSOR_STATUS.get(s["id"], {})
                        sen_data = {"id": s["id"], "name": s["name"], "online": cached.get("online", False)}
                        if cached.get("online"):
                            sen_data["value"] = cached.get("value")
                            sen_data["unit"] = cached.get("unit", "")
                        area_data["sensors"].append(sen_data)

                check_result["areas"].append(area_data)

        # 语音播报检查结果
        online_names = [a["name"] for a in check_result["areas"] if a["online"]]
        offline_names = [a["name"] for a in check_result["areas"] if not a["online"]]
        if online_names and not offline_names:
            tts_text = f"设备检查完成，{len(online_names)}个区域全部在线：{'、'.join(online_names)}"
        elif online_names and offline_names:
            tts_text = f"设备检查完成，{len(online_names)}个在线：{'、'.join(online_names)}；{len(offline_names)}个离线：{'、'.join(offline_names)}"
        else:
            tts_text = f"设备检查完成，所有{len(offline_names)}个区域均离线"
        _tts_speak(tts_text)
        log(f"[CHECK] {tts_text}")

        check_result["message"] = tts_text
        check_result["voiceSequence"] = [_vs_entry(tts_text)]
        return check_result

    def _hardware_check(self):
        """4区域连通性(从缓存读取，不阻塞)"""
        results = {}
        with _STATUS_LOCK:
            for area_id, area_info in AREA_DEFS.items():
                results[area_id] = {
                    "online": _AREA_ONLINE.get(area_id, False),
                    "ip": f"{area_info['ip']}:{area_info['port']}",
                    "name": area_info["name"],
                }
        return {"available": _HW_OK, "devices": results}

    # ===== 设备控制 =====
    def _toggle_device(self, device_id, body):
        is_on = bool(body.get("isOn", False))
        hw_result = hw_toggle(device_id, is_on)
        hw_ok = hw_result["success"]
        dev_name = _DEVICE_NAMES.get(device_id, device_id)

        if hw_ok:
            with _STATUS_LOCK:
                _DEVICE_STATUS[device_id] = {
                    "is_on": is_on, "primary_value": 100 if is_on else 0,
                    "online": True, "ts": time.time()
                }
            vs_text = f"{dev_name}已{'开启' if is_on else '关闭'}"
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS[device_id] = {"online": False}
            vs_text = f"{dev_name}{'开启' if is_on else '关闭'}失败，设备离线"

        log(f"[TOGGLE] {vs_text} (hw={'OK' if hw_ok else 'FAIL'})")

        conn = _db()
        conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                     (device_id, "toggle", json.dumps({"isOn": is_on}), "api"))
        conn.commit(); conn.close()

        _tts_speak(vs_text)
        return {
            "success": True,
            "device": {"id": device_id, "name": dev_name, "isOn": is_on if hw_ok else False, "online": hw_ok},
            "voiceSequence": [_vs_entry(vs_text)],
            "hardwareOnline": hw_ok
        }

    def _control_device(self, device_id, body):
        action = body.get("action", "")
        ps = body.get("params", {})
        hw_result = hw_control(device_id, action, ps)
        hw_ok = hw_result["success"]
        dev_name = _DEVICE_NAMES.get(device_id, device_id)

        if hw_ok:
            with _STATUS_LOCK:
                if action in ("set_speed", "set_temp", "set_brightness") and "value" in ps:
                    _DEVICE_STATUS[device_id] = {"is_on": True, "primary_value": ps["value"], "online": True, "ts": time.time()}
                if action == "set_position" and "value" in ps:
                    _DEVICE_STATUS[device_id] = {"is_on": ps["value"] > 0, "primary_value": ps["value"], "online": True, "ts": time.time()}

        _vs_text_map = {
            "set_temp": f"空调温度已设置为{ps.get('value', '')}度",
            "set_mode": f"空调模式已切换为{ps.get('mode', '')}",
            "set_speed": f"风速已设置为{ps.get('value', '')}",
            "set_brightness": f"灯光亮度已设置为{ps.get('value', '')}%",
            "set_position": f"窗帘位置已设置为{ps.get('value', '')}%",
            "stop": "窗帘已停止", "home": "窗帘开始回零",
        }
        vs_text = _vs_text_map.get(action, f"{dev_name}已控制") if hw_ok else f"{dev_name}调用失败，设备离线"

        log(f"[CONTROL] {dev_name} {action} {ps} → {'OK' if hw_ok else 'FAIL'}")

        conn = _db()
        conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                     (device_id, action, json.dumps(ps, ensure_ascii=False), "api"))
        conn.commit(); conn.close()

        _tts_speak(vs_text)
        cached = _DEVICE_STATUS.get(device_id, {})
        return {
            "success": True,
            "device": {"id": device_id, "name": dev_name, "online": hw_ok,
                       "primaryValue": cached.get("primary_value") if hw_ok else None,
                       "isOn": cached.get("is_on", False) if hw_ok else False},
            "voiceSequence": [_vs_entry(vs_text)],
            "hardwareOnline": hw_ok
        }

    def _door_control(self, body):
        action = body.get("action", "query")
        if action == "open":
            hw_result = hw_toggle("door_01", True)
        elif action == "close":
            hw_result = hw_toggle("door_01", False)
        else:
            hw_result = hw_living_status("door")
        hw_ok = hw_result.get("success", False)
        state = "open" if action == "open" else "closed" if action == "close" else (
            hw_result.get("data", {}).get("state", "unknown") if hw_ok else "离线")
        if action in ("open", "close"):
            _tts_speak(f"大门已{'开启' if action == 'open' else '关闭'}" if hw_ok else "大门操作失败，设备离线")
        log(f"[DOOR] {action} → {state} ({'OK' if hw_ok else 'FAIL'})")
        return {"success": hw_ok, "state": state, "hardwareOnline": hw_ok}

    def _update_user(self, body):
        conn = _db()
        if "nickname" in body: conn.execute("UPDATE users SET nickname=? WHERE id='u001'", (body["nickname"],))
        if "homeName" in body: conn.execute("UPDATE users SET home_name=? WHERE id='u001'", (body["homeName"],))
        if "memberCount" in body: conn.execute("UPDATE users SET member_count=? WHERE id='u001'", (body["memberCount"],))
        r = conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        conn.commit(); conn.close()
        return {"id": r[0], "nickname": r[1], "homeName": r[2], "memberCount": r[3]}

    # ===== AI 对话 =====
    def _chat(self, body):
        msgs = body.get("messages", [])
        if not msgs:
            return {"reply": "请输入消息", "role": "assistant"}
        last_msg = msgs[-1].get("content", "")

        # 1. 设备控制意图
        _dev_ctrl = self._detect_device_control(last_msg)
        if _dev_ctrl:
            return _dev_ctrl

        # 2. 状态查询意图
        _status_query = self._detect_status_query(last_msg)
        if _status_query:
            return _status_query

        # 3. 连通检查意图
        if any(kw in last_msg for kw in ["检查设备", "设备检查", "连通", "在线", "offline", "check"]):
            check = self._check_all()
            return {"reply": check["message"], "role": "assistant", "source": "check",
                    "voiceSequence": check.get("voiceSequence", [])}

        # 4. RAG固定回复
        fixed_reply = _rag.match_reply(last_msg)
        if fixed_reply:
            _tts_speak(fixed_reply)
            return {"reply": fixed_reply, "role": "assistant", "source": "rag", "voiceSequence": [_vs_entry(fixed_reply)]}

        # 5. AI大模型
        conn = _db()
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (last_msg,))
        reply = chat(msgs)
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
        conn.commit(); conn.close()
        _tts_speak(reply)
        return {"reply": reply, "role": "assistant", "voiceSequence": [_vs_entry(reply)]}

    def _detect_device_control(self, text):
        _DEV_KEYWORDS = {
            "空调": "ac_01", "客厅灯": "light_01", "主灯": "light_01",
            "氛围灯": "light_05", "厨房灯": "light_02",
            "卧室灯": "light_03", "卫生间灯": "light_04",
            "窗帘": "curtain_01", "大门": "door_01", "门": "door_01",
            "换气扇": "fan_02", "排风扇": "fan_02",
            "警报": "alarm_01", "蜂鸣": "alarm_01",
        }
        _ON_KEYWORDS = ["打开", "开启", "开", "启动", "合上"]
        _OFF_KEYWORDS = ["关闭", "关掉", "关", "停止", "停", "熄灭", "断开"]

        text = text.strip()
        dev_id = is_on = None
        for kw in _ON_KEYWORDS:
            if kw in text: is_on = True; break
        if is_on is None:
            for kw in _OFF_KEYWORDS:
                if kw in text: is_on = False; break
        if is_on is None:
            return None

        for kw, did in _DEV_KEYWORDS.items():
            if kw in text: dev_id = did; break
        if dev_id is None and "灯" in text:
            dev_id = "light_01"
        if dev_id is None:
            return None

        dev_name = _DEVICE_NAMES.get(dev_id, dev_id)
        hw_result = hw_toggle(dev_id, is_on)
        hw_ok = hw_result["success"]

        if hw_ok:
            with _STATUS_LOCK:
                _DEVICE_STATUS[dev_id] = {"is_on": is_on, "primary_value": 100 if is_on else 0, "online": True, "ts": time.time()}
            reply = f"[操作结果] {dev_name}已{'开启' if is_on else '关闭'}成功\n[设备状态] {dev_name}: {'开启' if is_on else '关闭'}"
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS[dev_id] = {"online": False}
            reply = f"[操作结果] {dev_name}{'开启' if is_on else '关闭'}失败\n[设备状态] {dev_name}: 离线"

        log(f"[CHAT-CTRL] {reply.strip()}")
        _tts_speak(reply.replace("[操作结果] ", "").replace("[设备状态] ", ""))
        return {"reply": reply, "role": "assistant", "voiceSequence": [_vs_entry(reply)], "hardwareOnline": hw_ok}

    def _detect_status_query(self, text):
        _STATUS_KEYWORDS = ["状态", "温度", "湿度", "检查", "查询", "查看", "现在", "怎么样", "什么情况", "有没有", "是否", "烟雾", "热敏", "窗帘位置", "status", "check", "query"]
        text_lower = text.strip().lower()
        is_status = any(kw in text_lower for kw in _STATUS_KEYWORDS)
        if not is_status:
            return None
        _CTRL = ["打开", "开启", "关闭", "关掉", "启动", "停止"]
        if any(kw in text for kw in _CTRL):
            return None

        with _STATUS_LOCK:
            lines = []
            for area_id, area_info in AREA_DEFS.items():
                area_online = _AREA_ONLINE.get(area_id, False)
                header = f"[{area_info['name']}]"
                if not area_online:
                    header += "(离线)"
                lines.append(header)

                for d in DEVICE_DEFS:
                    if d["area"] == area_id:
                        cached = _DEVICE_STATUS.get(d["id"], {})
                        if cached.get("online"):
                            on_text = "开" if cached.get("is_on") else "关"
                            pv = cached.get("primary_value")
                            if d["type"] == "light" and pv is not None:
                                on_text += f"(亮度{pv}%)"
                            elif d["type"] == "fan" and pv is not None:
                                on_text += f"(风速{pv}%)"
                            elif d["type"] == "curtain" and pv is not None:
                                on_text = f"位置{pv}%"
                            lines.append(f"  {d['name']}: {on_text}")
                        else:
                            lines.append(f"  {d['name']}: 离线")

                for s in SENSOR_DEFS:
                    if s["area"] == area_id:
                        cached = _SENSOR_STATUS.get(s["id"], {})
                        if cached.get("online"):
                            lines.append(f"  {s['name']}: {cached.get('value', '?')}{cached.get('unit', '')}")
                        else:
                            lines.append(f"  {s['name']}: 离线")
                lines.append("")

        reply = "\n".join(lines).strip()
        _tts_speak(f"状态查询完成，{sum(1 for a in _AREA_ONLINE.values() if a)}个区域在线")
        return {"reply": reply, "role": "assistant", "source": "realtime_status", "voiceSequence": [_vs_entry("状态查询完成")]}

    # ===== 语音输入 =====
    def _voice_input(self, body):
        """前端ASR识别结果发送到这里处理，TTS只管输出"""
        text = body.get("text", "")
        if not text:
            return {"reply": "未收到语音内容", "role": "assistant"}
        return self._chat({"messages": [{"role": "user", "content": text}]})


def load_env():
    global DEEPSEEK_API_KEY
    ep = ROOT / "HarmonyOS-mcp-server" / ".deepseek_env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "): line = line[7:]
            if "=" in line:
                k, v = line.split("=", 1); os.environ[k.strip()] = v.strip()
                if k.strip() == "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY = v.strip()


def main():
    load_env()
    db_init()
    # 轮询线程: 厨房1秒/其他10秒
    threading.Thread(target=sensor_poll_thread, daemon=True).start()
    log("[POLL] 传感器轮询已启动 (厨房1秒/其他10秒)")
    # UDP报警监听
    threading.Thread(target=udp_alarm_listener, daemon=True).start()
    # 数据推送
    try:
        from data_pusher import start_pusher
        start_pusher()
        log("[PUSHER] 数据推送服务已启动")
    except Exception as e:
        log(f"[PUSHER] 推送服务启动失败: {e}")
    # 网络通道
    try:
        from channel import start_channel, tts_speak
        start_channel()
        log("[CHANNEL] 网络通道服务已启动")
    except ImportError:
        log("[CHANNEL] 通道模块不可用，TTS输出降级为静音")
    except Exception as e:
        log(f"[CHANNEL] 通道服务启动失败: {e}")

    if _HW_OK:
        log("[HW] ✓ 硬件控制已加载")
    else:
        log("[HW] ✗ 硬件控制未加载")

    srv = ThreadingHTTPServer((HOST, PORT), H)
    log("=" * 50)
    log(f"智慧家居网关v5 :{PORT} {_AI_CONFIG.get('provider', 'deepseek')}")
    log(f"硬件控制: {'已启用' if _HW_OK else '未加载'}")
    log(f"轮询: 厨房{_KITCHEN_POLL_INTERVAL}秒 / 其他{_OTHER_POLL_INTERVAL}秒")
    log(f"报警联动: 厨房alarm上升沿→BEEP ALARM + UDP8001")
    log(f"设备离线: =关+没有数据(不显示默认值)")
    log(f"TTS: 只管输出(播报) / 输入: /api/voice/input")
    log(f"检查接口: GET /api/check (连通检查+语音播报)")
    log("=" * 50)
    srv.serve_forever()


if __name__ == "__main__":
    main()
