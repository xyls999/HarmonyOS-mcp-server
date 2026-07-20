#!/usr/bin/env python3
"""
智慧家居 HTTP 网关 v4 · 纯标准库 + 真实硬件控制
在 /data/A9/ 设备上运行

v4 变更:
  - 删除所有 mock/虚拟接口，只保留真实硬件控制
  - 4区域设备(客厅/厨房/卫生间/卧室)全部对接 central_controller
  - 传感器持续轮询真实硬件，离线设备标记 offline
  - AI 对话强 prompt + RAG 强命中 + 固定格式输出
  - 保留 TTS 语音播报 + AI 对话
  - 厨房报警联动客厅蜂鸣器
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
LOG_PATH = ROOT / "gateway_v4.log"

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
from scenes.scene_config import SCENE_ACTIONS, SCENE_META, SCENE_ALIASES, get_scene_id_by_name, get_scene_summary
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

# ===== 设备ID → 中文名 =====
_DEVICE_NAMES = {
    "light_01": "客厅主灯", "light_02": "厨房灯", "light_03": "卧室灯",
    "light_04": "卫生间灯", "light_05": "客厅氛围灯",
    "ac_01": "客厅空调", "fan_01": "客厅吊扇", "fan_02": "换气扇",
    "curtain_01": "智能窗帘", "door_01": "客厅大门", "alarm_01": "蜂鸣警报",
    "camera_01": "客厅摄像头", "exhaust_01": "抽风机",
    "nfc_01": "NFC门禁", "voice_01": "语音中控", "radar_01": "毫米波雷达",
}

# ===== 实时设备状态缓存 =====
_DEVICE_STATUS = {}   # device_id -> {"is_on": bool, "primary_value": int, "online": bool, "ts": float, "mode": str}
_SENSOR_STATUS = {}   # sensor_id -> {"value": float, "unit": str, "online": bool, "ts": float, "is_alert": bool}
_STATUS_LOCK = threading.Lock()
_POLL_INTERVAL = 10   # 秒，轮询间隔

# ===== 厨房报警联动 =====
_last_kitchen_alarm = 0  # 0=正常, 1=报警
_ALARM_LOCK = threading.Lock()

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

# ===== TTS 语音输出 (只负责语音播报输出，语音输入由 /api/voice/input 接管) =====
def _tts_speak(text):
    """播放语音输出：后台线程，不阻塞HTTP响应
    注意：此函数只负责语音输出(播报)，不处理语音输入
    语音输入由前端ASR识别后发送到 /api/voice/input
    """
    if not text:
        return
    def _speak():
        try:
            from channel import tts_speak as _ch_tts
            _ch_tts(text)
        except Exception:
            pass
    threading.Thread(target=_speak, daemon=True).start()

# ===== voiceSequence 辅助 =====
def _vs_entry(text):
    h = hashlib.md5(f"{text}_7".encode()).hexdigest()
    return {"text": text, "audioUrl": f"/api/tts/audio/{h}.mp3"}

# ===== 数据库 =====
def db_init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text("utf-8"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM devices")
    if cur.fetchone()[0] == 0:
        _seed_data(conn)
    conn.commit(); conn.close()

def _seed_data(conn):
    devices = [
        ("ac_01", "客厅空调", "ac", "active", "客厅", "air_fill", 24, 1, "制冷", None, "wifi"),
        ("fan_01", "客厅吊扇", "fan", "online", "客厅", "fan_fill_1", 2, 1, None, 92, "wifi"),
        ("door_01", "客厅大门", "door", "online", "客厅", "lock", 0, 0, None, 88, "wifi"),
        ("alarm_01", "蜂鸣警报", "alarm", "online", "客厅", "bell_fill", 0, 0, None, None, "wifi"),
        ("light_01", "客厅主灯", "light", "online", "客厅", "lightbulb", 80, 1, None, None, "wifi"),
        ("light_05", "客厅氛围灯", "light", "online", "客厅", "lightbulb", 45, 0, None, None, "wifi"),
        ("camera_01", "客厅摄像头", "camera", "online", "客厅", "camera_fill", 0, 1, None, None, "wifi"),
        ("light_02", "厨房灯", "light", "online", "厨房", "lightbulb", 70, 1, None, None, "wifi"),
        ("exhaust_01", "抽风机", "fan", "online", "厨房", "fan_fill_1", 1, 0, None, None, "wifi"),
        ("curtain_01", "智能窗帘", "curtain", "online", "卧室", "lock_open_fill", 100, 1, None, 95, "wifi"),
        ("light_03", "卧室灯", "light", "online", "卧室", "lightbulb", 50, 0, None, None, "wifi"),
        ("fan_02", "换气扇", "fan", "online", "卫生间", "fan_fill_1", 1, 0, None, None, "wifi"),
        ("light_04", "卫生间灯", "light", "online", "卫生间", "lightbulb", 60, 0, None, None, "wifi"),
        ("nfc_01", "NFC门禁", "nfc", "online", "室外", "lock", 0, 0, None, None, "wifi"),
        ("voice_01", "语音中控", "voice", "online", "全局", "mic_fill", 0, 1, None, None, "wifi"),
        ("radar_01", "毫米波雷达", "radar", "active", "全局", "wifi", 0, 1, None, None, "wifi"),
    ]
    conn.executemany("INSERT OR IGNORE INTO devices VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))", devices)
    sensors = [
        ("temp_01", "客厅温度", "temperature", "环境监测", "客厅", "thermometer", 24.5, "°C", 18, 28, "wifi", 0),
        ("humid_01", "客厅湿度", "humidity", "环境监测", "客厅", "drop", 58, "%RH", 40, 70, "wifi", 0),
        ("light_s_01", "客厅光照", "illuminance", "环境监测", "客厅", "sun_max", 320, "lx", None, None, "wifi", 0),
        ("air_01", "空气质量", "air_quality", "环境监测", "客厅", "wind", 42, "AQI", None, 100, "wifi", 0),
        ("pir_01", "人体感应", "pir", "安防", "客厅", "figure_arms_open", 1, "有人", None, 1, "wifi", 0),
        ("smoke_01", "烟雾检测", "smoke", "安防", "厨房", "flame_fill", 0, "正常", None, 1, "starflash", 0),
        ("heat_01", "热敏火灾", "heat", "安防", "厨房", "flame_fill", 36.2, "°C", None, 60, "starflash", 0),
        ("door_s_01", "门窗感应", "door_window", "安防", "室外", "lock", 0, "关闭", None, None, "starflash", 0),
        ("power_01", "总功率", "power", "能耗", "全局", "bolt_fill", 1.2, "kW", None, None, "wifi", 0),
    ]
    conn.executemany("INSERT OR IGNORE INTO sensors VALUES(?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))", sensors)
    scenes_data = [
        ("s1", "回家", "house_fill", "#22D3EE", 1, "回家模式"),
        ("s2", "离家", "figure_walk", "#F97316", 0, "离家模式"),
        ("s3", "睡眠", "moon_fill", "#818CF8", 0, "睡眠模式"),
        ("s4", "观影", "film", "#F472B6", 0, "观影模式"),
        ("s5", "用餐", "fork_knife", "#34D399", 0, "用餐模式"),
    ]
    conn.executemany("INSERT OR IGNORE INTO scenes VALUES(?,?,?,?,?,?,datetime('now'),datetime('now'))", scenes_data)
    for sid, actions in SCENE_ACTIONS.items():
        for idx, (dev_id, is_on, pv) in enumerate(actions):
            conn.execute("INSERT OR IGNORE INTO scene_actions(scene_id,device_id,is_on,primary_value,sort_order) VALUES(?,?,?,?,?)",
                         (sid, dev_id, 1 if is_on else 0, pv, idx))
    conn.execute("INSERT OR IGNORE INTO users VALUES('u001','用户','我的家',3,'',datetime('now'),datetime('now'))")

def _db():
    return sqlite3.connect(str(DB_PATH))

# ===== 真实硬件状态轮询 =====
def _poll_living():
    """轮询客厅设备状态"""
    try:
        # 温湿度
        r = hw_sensor_read("temp_01")
        if r["success"] and "temp" in r.get("data", {}):
            d = r["data"]
            with _STATUS_LOCK:
                _SENSOR_STATUS["temp_01"] = {"value": d["temp"], "unit": "°C", "online": True, "ts": time.time(), "is_alert": d["temp"] > 28}
                if "humidity" in d:
                    _SENSOR_STATUS["humid_01"] = {"value": d["humidity"], "unit": "%RH", "online": True, "ts": time.time(), "is_alert": d["humidity"] > 70}
        else:
            with _STATUS_LOCK:
                _SENSOR_STATUS.setdefault("temp_01", {})["online"] = False
                _SENSOR_STATUS.setdefault("humid_01", {})["online"] = False
    except Exception:
        pass

    try:
        # 客厅灯状态
        r = hw_living_status("light")
        if r["success"]:
            reply = r.get("data", {}).get("reply", "") if isinstance(r.get("data"), dict) else str(r.get("data", ""))
            is_on = "ON" in str(reply).upper() or "开" in str(reply)
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_01"] = {"is_on": is_on, "primary_value": 100 if is_on else 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("light_01", {})["online"] = False
    except Exception:
        pass

    try:
        # 空调状态
        r = hw_living_status("ac")
        if r["success"]:
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else str(r.get("data", ""))
            is_on = "ON" in reply.upper() or "开" in reply
            with _STATUS_LOCK:
                _DEVICE_STATUS["ac_01"] = {"is_on": is_on, "primary_value": 24, "online": True, "ts": time.time(), "mode": "制冷"}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("ac_01", {})["online"] = False
    except Exception:
        pass

    try:
        # 门禁状态
        r = hw_living_status("door")
        if r["success"]:
            state = r.get("data", {}).get("state", "closed") if isinstance(r.get("data"), dict) else "closed"
            is_on = state == "open"
            with _STATUS_LOCK:
                _DEVICE_STATUS["door_01"] = {"is_on": is_on, "primary_value": 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("door_01", {})["online"] = False
    except Exception:
        pass

    try:
        # 蜂鸣器状态
        r = hw_living_status("beep")
        if r["success"]:
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else ""
            is_on = "ALARM" in reply.upper() or "ON" in reply.upper()
            with _STATUS_LOCK:
                _DEVICE_STATUS["alarm_01"] = {"is_on": is_on, "primary_value": 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("alarm_01", {})["online"] = False
    except Exception:
        pass


def _poll_kitchen():
    """轮询厨房设备状态"""
    try:
        r = hw_kitchen_status()
        if r["success"]:
            d = r.get("data", {})
            with _STATUS_LOCK:
                # 厨房灯
                _DEVICE_STATUS["light_02"] = {
                    "is_on": d.get("light_on", 0) > 0 or d.get("brightness", 0) > 0,
                    "primary_value": d.get("brightness", 0),
                    "online": True, "ts": time.time()
                }
                # 烟雾传感器
                _SENSOR_STATUS["smoke_01"] = {
                    "value": d.get("smoke_alarm", 0),
                    "unit": "报警" if d.get("smoke_alarm", 0) else "正常",
                    "online": True, "ts": time.time(),
                    "is_alert": d.get("smoke_alarm", 0) == 1
                }
                # 热敏传感器
                _SENSOR_STATUS["heat_01"] = {
                    "value": d.get("thermal_mv", 0),
                    "unit": "mV",
                    "online": True, "ts": time.time(),
                    "is_alert": d.get("temp_alarm", 0) == 1
                }
                # 空气质量(综合)
                _SENSOR_STATUS["air_01"] = {
                    "value": d.get("alarm", 0),
                    "unit": "综合报警",
                    "online": True, "ts": time.time(),
                    "is_alert": d.get("alarm", 0) == 1
                }

            # 厨房报警联动
            alarm_now = d.get("alarm", 0)
            with _ALARM_LOCK:
                global _last_kitchen_alarm
                if alarm_now == 1 and _last_kitchen_alarm == 0:
                    # 报警上升沿 → 触发客厅蜂鸣器
                    hw_toggle("alarm_01", True)
                    _tts_speak("厨房检测到异常，已触发警报")
                    log("[ALARM-LINKAGE] 厨房报警上升沿 → 客厅蜂鸣器已触发")
                elif alarm_now == 0 and _last_kitchen_alarm == 1:
                    # 报警恢复 → 关闭蜂鸣器
                    hw_toggle("alarm_01", False)
                    _tts_speak("厨房报警已恢复，警报已关闭")
                    log("[ALARM-LINKAGE] 厨房报警恢复 → 客厅蜂鸣器已关闭")
                _last_kitchen_alarm = alarm_now
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("light_02", {})["online"] = False
                _SENSOR_STATUS.setdefault("smoke_01", {})["online"] = False
                _SENSOR_STATUS.setdefault("heat_01", {})["online"] = False
    except Exception as e:
        log(f"[POLL-KITCHEN] {e}")


def _poll_bathroom():
    """轮询卫生间设备状态"""
    try:
        r = hw_bathroom_status()
        if r["success"]:
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
                    "mode": "正转" if d.get("motor_direction") == 1 else "反转" if d.get("motor_direction") == 2 else "停止"
                }
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("light_04", {})["online"] = False
                _DEVICE_STATUS.setdefault("fan_02", {})["online"] = False
    except Exception as e:
        log(f"[POLL-BATHROOM] {e}")


def _poll_bedroom():
    """轮询卧室设备状态"""
    try:
        r = hw_bedroom_status()
        if r["success"]:
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
                    "mode": "移动中" if d.get("curtain_moving") else "静止",
                    "homed": d.get("curtain_homed", 0) == 1,
                    "close_limit": d.get("close_limit", 0),
                    "open_limit": d.get("open_limit", 0),
                }
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS.setdefault("light_03", {})["online"] = False
                _DEVICE_STATUS.setdefault("curtain_01", {})["online"] = False
    except Exception as e:
        log(f"[POLL-BEDROOM] {e}")


def sensor_poll_thread():
    """后台线程: 持续轮询所有真实硬件设备状态"""
    log("[POLL] 传感器轮询线程启动")
    while True:
        _poll_living()
        _poll_kitchen()
        _poll_bathroom()
        _poll_bedroom()
        # 传感器数据入库
        _save_sensor_readings()
        time.sleep(_POLL_INTERVAL)


def _save_sensor_readings():
    """将轮询到的传感器数据写入数据库(每轮1次)"""
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


# ===== 厨房 UDP 报警监听 =====
_UDP_LISTENING = False

def udp_alarm_listener():
    """后台线程: 监听厨房UDP 8001广播报警
    UDP 8001 由厨房固件在报警时广播 255.255.255.255:8001
    """
    global _UDP_LISTENING
    UDP_PORT = 8001
    try:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.bind(("", UDP_PORT))
        udp_sock.setblocking(False)
        _UDP_LISTENING = True
        log(f"[UDP] 厨房报警监听已启动 :{UDP_PORT}")
    except OSError as e:
        log(f"[UDP] 监听启动失败: {e}")
        return

    while True:
        try:
            data, addr = udp_sock.recvfrom(1024)
            text = data.decode("utf-8", errors="replace").strip()
            log(f"[UDP] 厨房报警 from {addr[0]}: {text}")
            # UDP报警也触发联动
            with _ALARM_LOCK:
                global _last_kitchen_alarm
                if _last_kitchen_alarm == 0:
                    _last_kitchen_alarm = 1
                    hw_toggle("alarm_01", True)
                    _tts_speak("厨房UDP报警，已触发警报")
        except BlockingIOError:
            pass
        except Exception as e:
            log(f"[UDP] 接收错误: {e}")
        time.sleep(0.1)


# ===== AI 对话 =====
# 强 prompt: 固定格式输出
_SYSTEM_PROMPT = """你是智慧家居助手，必须严格遵守以下规则：

## 身份
你是控制4个区域(客厅/厨房/卫生间/卧室)的智慧家居AI助手。

## 输出格式规范
所有回复必须使用以下固定格式：

### 设备控制回复
[操作结果] {设备名}{动作}成功/失败
[设备状态] {设备名}: {状态描述}

### 状态查询回复（必须按此格式）
[客厅]
  温度: {X}°C
  湿度: {X}%RH
  客厅灯: 开/关
  空调: 开/关
  大门: 开/关
  蜂鸣器: 开/关

[厨房]
  烟雾: 正常/报警
  热敏: {X}mV
  厨房灯: 开/关(亮度{X}%)

[卫生间]
  卫生间灯: 开/关(亮度{X}%)
  换气扇: 开/关(风速{X}%)

[卧室]
  卧室灯: 开/关(亮度{X}%)
  窗帘: 位置{X}%

### 场景回复
[场景] {场景名}模式已激活
[影响] {N}台设备已控制

### 报警回复
[报警] {报警类型}检测到异常！
[联动] 已触发客厅蜂鸣器

## 约束
1. 只回答与智能家居相关的问题
2. 设备离线时明确标注"设备离线"
3. 不编造传感器数据，只使用真实数据
4. 回复简洁，不超过200字
5. 控制指令必须确认执行结果
"""

def chat(msgs):
    """AI对话，强prompt + RAG上下文"""
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

    # RAG 上下文
    rag_ctx = _rag.get_context(last_msg)
    rag_device = _rag.search_device(last_msg)
    rag_scene = _rag.search_scene(last_msg)

    # 构建实时设备状态上下文
    with _STATUS_LOCK:
        status_ctx_parts = []
        # 客厅
        temp_s = _SENSOR_STATUS.get("temp_01", {})
        humid_s = _SENSOR_STATUS.get("humid_01", {})
        light01 = _DEVICE_STATUS.get("light_01", {})
        ac01 = _DEVICE_STATUS.get("ac_01", {})
        door01 = _DEVICE_STATUS.get("door_01", {})
        alarm01 = _DEVICE_STATUS.get("alarm_01", {})
        status_ctx_parts.append(f"[客厅实时] 温度:{temp_s.get('value','?')}°C 湿度:{humid_s.get('value','?')}%RH 灯:{'开' if light01.get('is_on') else '关'} 空调:{'开' if ac01.get('is_on') else '关'} 门:{'开' if door01.get('is_on') else '关'} 蜂鸣器:{'开' if alarm01.get('is_on') else '关'}")
        # 厨房
        light02 = _DEVICE_STATUS.get("light_02", {})
        smoke_s = _SENSOR_STATUS.get("smoke_01", {})
        heat_s = _SENSOR_STATUS.get("heat_01", {})
        status_ctx_parts.append(f"[厨房实时] 灯:{'开' if light02.get('is_on') else '关'}(亮度{light02.get('primary_value','?')}%) 烟雾:{'报警' if smoke_s.get('is_alert') else '正常'} 热敏:{heat_s.get('value','?')}mV")
        # 卫生间
        light04 = _DEVICE_STATUS.get("light_04", {})
        fan02 = _DEVICE_STATUS.get("fan_02", {})
        status_ctx_parts.append(f"[卫生间实时] 灯:{'开' if light04.get('is_on') else '关'}(亮度{light04.get('primary_value','?')}%) 换气扇:{'开' if fan02.get('is_on') else '关'}(风速{fan02.get('primary_value','?')}%)")
        # 卧室
        light03 = _DEVICE_STATUS.get("light_03", {})
        curtain01 = _DEVICE_STATUS.get("curtain_01", {})
        status_ctx_parts.append(f"[卧室实时] 灯:{'开' if light03.get('is_on') else '关'}(亮度{light03.get('primary_value','?')}%) 窗帘:位置{curtain01.get('primary_value','?')}%")

    status_ctx = "\n".join(status_ctx_parts)

    # 增强系统提示
    sys_msg = _SYSTEM_PROMPT + f"\n\n## 当前实时设备状态\n{status_ctx}\n"
    if rag_ctx:
        sys_msg += f"\n## RAG匹配上下文\n{rag_ctx}\n"
    if rag_device:
        sys_msg += f"\n## RAG设备匹配\n设备类型:{rag_device.get('device_type','')} 动作:{rag_device.get('action','')}\n"
    if rag_scene:
        sys_msg += f"\n## RAG场景匹配\n场景:{rag_scene.get('scene_name','')} ID:{rag_scene.get('scene_id','')}\n"

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
                self._j(200, {"ok": True, "v": 4, "hardware": _HW_OK})
            elif p == "/api/devices":
                self._j(200, self._get_devices())
            elif p == "/api/sensors":
                self._j(200, self._get_sensors())
            elif p == "/api/scenes":
                self._j(200, self._get_scenes())
            elif p == "/api/user/profile":
                self._j(200, self._get_user())
            elif p == "/api/server/status":
                self._j(200, {
                    "host": "192.168.1.81", "port": PORT, "isOnline": True,
                    "protocol": "wifi", "latency": 5, "cpuUsage": 25,
                    "memUsage": 40, "storageUsage": 35, "version": "v4",
                    "hardware": _HW_OK, "pollInterval": _POLL_INTERVAL
                })
            elif p == "/api/cameras":
                self._j(200, self._get_cameras())
            elif p == "/api/alerts":
                self._j(200, self._get_alerts())
            elif p == "/api/sensors/history":
                self._j(200, self._get_sensor_history())
            elif p == "/api/hardware/status":
                self._j(200, self._hardware_check())
            elif p == "/api/rag/stats":
                self._j(200, _rag.get_stats())
            elif p == "/api/operations":
                qs = self.path.split("?", 1)
                did = None; days = 7
                if len(qs) > 1:
                    for kv in qs[1].split("&"):
                        k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                        if k == "device_id": did = v
                        if k == "days": days = int(v)
                self._j(200, self._get_operations(did, days))
            # TTS 代理到 channel.py
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
            elif p == "/api/devices":
                self._j(200, self._add_device(body))
            elif p == "/api/user/profile":
                self._j(200, self._update_user(body))
            elif p == "/api/rag/search":
                self._j(200, {"results": _rag.search(body.get("query", ""), n=body.get("n_results", 5))})
            # 场景激活
            else:
                m = re.match(r"^/api/scenes/([\w_]+)/activate$", p)
                if m:
                    self._j(200, self._activate_scene(m.group(1)))
                    return
                m = re.match(r"^/api/devices/([\w_]+)/control$", p)
                if m:
                    self._j(200, self._control_device(m.group(1), body))
                    return
                m = re.match(r"^/api/devices/([\w_]+)/toggle$", p)
                if m:
                    self._j(200, self._toggle_device(m.group(1), body))
                    return
                # TTS/AI 代理
                if p in ("/api/tts/config", "/api/tts/test", "/api/tts/speak",
                         "/api/ai/config", "/api/ai/test"):
                    self._proxy_post(f"http://127.0.0.1:8081{p}", body)
                else:
                    self._j(404, {"error": "nf"})
        except Exception as e:
            self._j(500, {"error": str(e)})

    # ===== 代理方法 =====
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
                    self.send_header("Cache-Control", "public, max-age=86400")
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

    # ===== 真实设备数据 =====
    def _get_devices(self):
        """从真实硬件状态缓存返回设备列表"""
        # 基础设备定义
        device_defs = [
            {"id": "ac_01", "name": "客厅空调", "type": "ac", "room": "客厅", "icon": "air_fill"},
            {"id": "fan_01", "name": "客厅吊扇", "type": "fan", "room": "客厅", "icon": "fan_fill_1"},
            {"id": "door_01", "name": "客厅大门", "type": "door", "room": "客厅", "icon": "lock"},
            {"id": "alarm_01", "name": "蜂鸣警报", "type": "alarm", "room": "客厅", "icon": "bell_fill"},
            {"id": "light_01", "name": "客厅主灯", "type": "light", "room": "客厅", "icon": "lightbulb"},
            {"id": "light_05", "name": "客厅氛围灯", "type": "light", "room": "客厅", "icon": "lightbulb"},
            {"id": "camera_01", "name": "客厅摄像头", "type": "camera", "room": "客厅", "icon": "camera_fill"},
            {"id": "light_02", "name": "厨房灯", "type": "light", "room": "厨房", "icon": "lightbulb"},
            {"id": "exhaust_01", "name": "抽风机", "type": "fan", "room": "厨房", "icon": "fan_fill_1"},
            {"id": "curtain_01", "name": "智能窗帘", "type": "curtain", "room": "卧室", "icon": "lock_open_fill"},
            {"id": "light_03", "name": "卧室灯", "type": "light", "room": "卧室", "icon": "lightbulb"},
            {"id": "fan_02", "name": "换气扇", "type": "fan", "room": "卫生间", "icon": "fan_fill_1"},
            {"id": "light_04", "name": "卫生间灯", "type": "light", "room": "卫生间", "icon": "lightbulb"},
            {"id": "nfc_01", "name": "NFC门禁", "type": "nfc", "room": "室外", "icon": "lock"},
            {"id": "voice_01", "name": "语音中控", "type": "voice", "room": "全局", "icon": "mic_fill"},
            {"id": "radar_01", "name": "毫米波雷达", "type": "radar", "room": "全局", "icon": "wifi"},
        ]
        result = []
        with _STATUS_LOCK:
            for d in device_defs:
                did = d["id"]
                cached = _DEVICE_STATUS.get(did, {})
                online = cached.get("online", False)
                entry = {
                    "id": did,
                    "name": d["name"],
                    "type": d["type"],
                    "status": "online" if online else "offline",
                    "room": d["room"],
                    "icon": d["icon"],
                    "primaryValue": cached.get("primary_value", 0),
                    "isOn": cached.get("is_on", False),
                }
                if "mode" in cached:
                    entry["mode"] = cached["mode"]
                if "battery" in cached:
                    entry["battery"] = cached["battery"]
                result.append(entry)
        return result

    def _get_sensors(self):
        """从真实硬件状态缓存返回传感器列表"""
        sensor_defs = [
            {"id": "temp_01", "name": "客厅温度", "type": "temperature", "group": "环境监测", "room": "客厅", "icon": "thermometer", "unit": "°C", "thresholdMin": 18, "thresholdMax": 28},
            {"id": "humid_01", "name": "客厅湿度", "type": "humidity", "group": "环境监测", "room": "客厅", "icon": "drop", "unit": "%RH", "thresholdMin": 40, "thresholdMax": 70},
            {"id": "light_s_01", "name": "客厅光照", "type": "illuminance", "group": "环境监测", "room": "客厅", "icon": "sun_max", "unit": "lx"},
            {"id": "air_01", "name": "空气质量", "type": "air_quality", "group": "环境监测", "room": "客厅", "icon": "wind", "unit": "AQI", "thresholdMax": 100},
            {"id": "pir_01", "name": "人体感应", "type": "pir", "group": "安防", "room": "客厅", "icon": "figure_arms_open", "unit": "有人"},
            {"id": "smoke_01", "name": "烟雾检测", "type": "smoke", "group": "安防", "room": "厨房", "icon": "flame_fill", "unit": "正常"},
            {"id": "heat_01", "name": "热敏火灾", "type": "heat", "group": "安防", "room": "厨房", "icon": "flame_fill", "unit": "mV", "thresholdMax": 60},
            {"id": "door_s_01", "name": "门窗感应", "type": "door_window", "group": "安防", "room": "室外", "icon": "lock", "unit": "关闭"},
            {"id": "power_01", "name": "总功率", "type": "power", "group": "能耗", "room": "全局", "icon": "bolt_fill", "unit": "kW"},
        ]
        result = []
        with _STATUS_LOCK:
            for s in sensor_defs:
                sid = s["id"]
                cached = _SENSOR_STATUS.get(sid, {})
                online = cached.get("online", False)
                entry = {
                    "id": sid,
                    "name": s["name"],
                    "type": s["type"],
                    "group": s["group"],
                    "room": s["room"],
                    "icon": s["icon"],
                    "current": {
                        "value": cached.get("value", 0),
                        "unit": cached.get("unit", s["unit"]),
                    },
                    "isAlert": cached.get("is_alert", False),
                }
                if "thresholdMin" in s:
                    entry["thresholdMin"] = s["thresholdMin"]
                if "thresholdMax" in s:
                    entry["thresholdMax"] = s["thresholdMax"]
                result.append(entry)
        return result

    def _get_scenes(self):
        conn = _db()
        scenes = []
        for s in conn.execute("SELECT id,name,icon,color,is_active,description FROM scenes").fetchall():
            actions = []
            for a in conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order", (s[0],)).fetchall():
                act = {"deviceId": a[0], "isOn": bool(a[1])}
                if a[2] is not None:
                    act["primaryValue"] = a[2]
                actions.append(act)
            scenes.append({"id": s[0], "name": s[1], "icon": s[2], "color": s[3], "isActive": bool(s[4]), "description": s[5], "actions": actions})
        conn.close()
        return scenes

    def _get_user(self):
        conn = _db()
        r = conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        dc = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
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

    def _hardware_check(self):
        """测试4个区域硬件连通性（使用缓存状态，不阻塞）"""
        results = {}
        with _STATUS_LOCK:
            # 从缓存中读取最近状态
            for area, ip in [("living_room", "192.168.1.62:8000"), ("kitchen", "192.168.1.23:8000"),
                             ("bathroom", "192.168.1.63:8000"), ("bedroom", "192.168.1.64:8000")]:
                # 检查该区域是否有设备在缓存中有online=True
                area_devices = {
                    "living_room": ["light_01", "ac_01", "door_01", "alarm_01"],
                    "kitchen": ["light_02"],
                    "bathroom": ["light_04", "fan_02"],
                    "bedroom": ["light_03", "curtain_01"],
                }
                online = any(_DEVICE_STATUS.get(d, {}).get("online", False) for d in area_devices.get(area, []))
                results[area] = {"online": online, "ip": ip}
        return {"available": _HW_OK, "devices": results}

    # ===== 摄像头/告警/传感器历史 =====
    def _get_cameras(self):
        return [
            {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online" if _HW_OK else "offline", "isRecording": False, "resolution": "1080P", "previewColor": "#1D7F68"},
            {"id": "cam_02", "name": "门口摄像头", "room": "室外", "status": "offline", "isRecording": False, "resolution": "1080P", "previewColor": "#7A6DE8"},
        ]

    def _get_alerts(self):
        """返回当前活跃告警（基于真实传感器数据）"""
        alerts = []
        with _STATUS_LOCK:
            # 烟雾告警
            smoke = _SENSOR_STATUS.get("smoke_01", {})
            if smoke.get("is_alert"):
                alerts.append({"id": "alert_smoke", "source": "烟雾检测", "content": "厨房烟雾报警！", "level": "critical", "isRead": False, "timestamp": now_ms()})
            # 热敏告警
            heat = _SENSOR_STATUS.get("heat_01", {})
            if heat.get("is_alert"):
                alerts.append({"id": "alert_heat", "source": "热敏火灾", "content": f"厨房热敏异常: {heat.get('value', '?')}mV", "level": "critical", "isRead": False, "timestamp": now_ms()})
            # 温度告警
            temp = _SENSOR_STATUS.get("temp_01", {})
            if temp.get("is_alert"):
                alerts.append({"id": "alert_temp", "source": "客厅温度", "content": f"温度异常: {temp.get('value', '?')}°C 超出阈值", "level": "warning", "isRead": False, "timestamp": now_ms()})
            # 湿度告警
            humid = _SENSOR_STATUS.get("humid_01", {})
            if humid.get("is_alert"):
                alerts.append({"id": "alert_humid", "source": "客厅湿度", "content": f"湿度异常: {humid.get('value', '?')}%RH 超出阈值", "level": "warning", "isRead": False, "timestamp": now_ms()})
        # 若无活跃告警，返回空
        return alerts

    def _get_sensor_history(self):
        """获取传感器历史数据（从数据库读取最近24小时）"""
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT sensor_id, value, unit, created_at FROM sensor_readings "
                "WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
            conn.close()
            # 按传感器分组
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

    # ===== 语音输入 (TTS只管输出，输入由此接口处理) =====
    def _voice_input(self, body):
        """语音输入接口：前端ASR识别后的文本发到这里处理
        TTS只负责语音输出(播报)，语音输入(识别)由前端完成
        """
        text = body.get("text", "")
        if not text:
            return {"reply": "未收到语音内容", "role": "assistant"}

        # 复用chat的完整处理流程
        return self._chat({"messages": [{"role": "user", "content": text}]})

    # ===== 门禁控制 =====
    def _door_control(self, body):
        """门禁直接控制接口"""
        action = body.get("action", "query")
        if action == "open":
            hw_result = hw_toggle("door_01", True)
        elif action == "close":
            hw_result = hw_toggle("door_01", False)
        else:
            # 查询
            hw_result = hw_living_status("door")

        hw_ok = hw_result.get("success", False)
        state = "open" if action == "open" else "closed" if action == "close" else (
            hw_result.get("data", {}).get("state", "unknown") if hw_ok else "unknown"
        )

        if action in ("open", "close"):
            _tts_speak(f"大门已{'开启' if action == 'open' else '关闭'}")

        return {
            "success": hw_ok,
            "state": state,
            "hardwareOnline": hw_ok
        }

    # ===== 设备控制 =====
    def _toggle_device(self, device_id, body):
        is_on = bool(body.get("isOn", False))
        # 真实硬件调用
        hw_result = hw_toggle(device_id, is_on)
        dev_name = _DEVICE_NAMES.get(device_id, device_id)
        hw_ok = hw_result["success"]

        # 更新缓存
        with _STATUS_LOCK:
            _DEVICE_STATUS[device_id] = {
                "is_on": is_on if hw_ok else _DEVICE_STATUS.get(device_id, {}).get("is_on", False),
                "primary_value": 100 if is_on else 0 if hw_ok else _DEVICE_STATUS.get(device_id, {}).get("primary_value", 0),
                "online": hw_ok,
                "ts": time.time()
            }

        # 记录操作
        conn = _db()
        conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, device_id))
        conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                     (device_id, "toggle", json.dumps({"isOn": is_on}), "api"))
        conn.commit(); conn.close()

        # 语音反馈
        if hw_ok:
            vs_text = f"{dev_name}已{'开启' if is_on else '关闭'}"
        else:
            vs_text = f"{dev_name}{'开启' if is_on else '关闭'}失败，设备离线"
        _tts_speak(vs_text)

        return {
            "success": True,
            "device": {"id": device_id, "name": dev_name, "isOn": is_on if hw_ok else not is_on},
            "voiceSequence": [_vs_entry(vs_text)],
            "hardwareOnline": hw_ok
        }

    def _control_device(self, device_id, body):
        action = body.get("action", "")
        ps = body.get("params", {})
        # 真实硬件调用
        hw_result = hw_control(device_id, action, ps)
        dev_name = _DEVICE_NAMES.get(device_id, device_id)
        hw_ok = hw_result["success"]

        # 更新缓存
        with _STATUS_LOCK:
            if action in ("set_speed", "set_temp", "set_brightness") and "value" in ps and hw_ok:
                _DEVICE_STATUS[device_id] = {
                    "is_on": True,
                    "primary_value": ps["value"],
                    "online": True,
                    "ts": time.time()
                }
            if action == "set_position" and "value" in ps and hw_ok:
                _DEVICE_STATUS[device_id] = {
                    "is_on": ps["value"] > 0,
                    "primary_value": ps["value"],
                    "online": True,
                    "ts": time.time()
                }

        # 记录操作
        conn = _db()
        if action in ("set_speed", "set_temp", "set_brightness") and "value" in ps:
            conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?", (ps["value"], device_id))
        if action == "set_mode" and "mode" in ps:
            conn.execute("UPDATE devices SET mode=?, updated_at=datetime('now') WHERE id=?", (ps["mode"], device_id))
        conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                     (device_id, action, json.dumps(ps, ensure_ascii=False), "api"))
        conn.commit(); conn.close()

        # 语音反馈
        if hw_ok:
            _vs_text_map = {
                "set_temp": f"空调温度已设置为{ps.get('value', '')}度",
                "set_mode": f"空调模式已切换为{ps.get('mode', '')}",
                "set_speed": f"风速已设置为{ps.get('value', '')}",
                "set_brightness": f"灯光亮度已设置为{ps.get('value', '')}%",
                "set_position": f"窗帘位置已设置为{ps.get('value', '')}%",
                "stop": "窗帘已停止",
                "home": "窗帘开始回零",
            }
            vs_text = _vs_text_map.get(action, f"{dev_name}已控制")
        else:
            vs_text = f"{dev_name}调用失败，设备离线"
        _tts_speak(vs_text)

        cached = _DEVICE_STATUS.get(device_id, {})
        return {
            "success": True,
            "device": {
                "id": device_id, "name": dev_name,
                "primaryValue": cached.get("primary_value", 0),
                "isOn": cached.get("is_on", False)
            },
            "voiceSequence": [_vs_entry(vs_text)],
            "hardwareOnline": hw_ok
        }

    def _activate_scene(self, scene_id):
        conn = _db()
        conn.execute("UPDATE scenes SET is_active=0")
        conn.execute("UPDATE scenes SET is_active=1, updated_at=datetime('now') WHERE id=?", (scene_id,))
        name_r = conn.execute("SELECT name FROM scenes WHERE id=?", (scene_id,)).fetchone()
        if not name_r:
            conn.commit(); conn.close()
            return {"success": False, "error": "场景不存在"}
        actions = conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order", (scene_id,)).fetchall()
        count = len(actions)
        conn.execute("INSERT INTO chat_history(user_id,role,content,scene_id) VALUES('u001','assistant',?,?)",
                     (f"已切换到「{name_r[0]}」模式，控制 {count} 台设备", scene_id))
        conn.commit(); conn.close()

        # 真实硬件执行
        hw_results = hw_scene_execute(actions)
        hw_ok_count = sum(1 for r in hw_results if r["success"])
        hw_fail_count = len(hw_results) - hw_ok_count
        hw_any_ok = hw_ok_count > 0

        # 更新缓存
        with _STATUS_LOCK:
            for dev_id, is_on, pv in actions:
                _DEVICE_STATUS[dev_id] = {
                    "is_on": is_on,
                    "primary_value": pv if pv is not None else (100 if is_on else 0),
                    "online": True,
                    "ts": time.time()
                }

        # 语音反馈
        _vs_scene_map = {
            "s1": "欢迎回家，回家模式已激活",
            "s2": "离家模式已激活，注意安全",
            "s3": "睡眠模式已激活，晚安",
            "s4": "观影模式已激活，请享受",
            "s5": "用餐模式已激活，请慢用"
        }
        scene_text = _vs_scene_map.get(scene_id, f"{name_r[0]}模式已激活")
        if hw_fail_count > 0 and hw_any_ok:
            tts_text = f"{scene_text}，{hw_fail_count}台设备调用失败"
        elif hw_fail_count > 0 and not hw_any_ok:
            tts_text = f"{name_r[0]}模式调用失败"
        else:
            tts_text = scene_text
        _tts_speak(tts_text)

        # voiceSequence
        _vs_texts = [scene_text]
        for _d, _io, _pv in actions:
            _dn = _DEVICE_NAMES.get(_d, _d)
            hw_r = next((r for r in hw_results if r["device_id"] == _d), None)
            if hw_r and not hw_r["success"]:
                _vs_texts.append(f"{_dn}调用失败")
            else:
                _vs_texts.append(f"{_dn}已{'开启' if _io else '关闭'}")
        _vs_seq = []
        for i, _t in enumerate(_vs_texts):
            _entry = _vs_entry(_t)
            if i > 0:
                _entry["delay"] = 500
            _vs_seq.append(_entry)

        return {
            "success": True,
            "scene_name": name_r[0],
            "affected_count": count,
            "voiceSequence": _vs_seq,
            "hardwareOnline": hw_any_ok
        }

    def _add_device(self, body):
        did = body.get("id", f"d{int(time.time()) % 10000}")
        conn = _db()
        conn.execute("INSERT OR IGNORE INTO devices(id,name,type,room,icon,primary_value,is_on,status) VALUES(?,?,?,?,?,0,0,'online')",
                     (did, body.get("name", "新设备"), body.get("type", "light"), body.get("room", "客厅"), body.get("icon", "lightbulb")))
        r = conn.execute("SELECT id,name,type,room FROM devices WHERE id=?", (did,)).fetchone()
        conn.commit(); conn.close()
        return {"success": True, "device": {"id": r[0], "name": r[1], "type": r[2], "room": r[3]}}

    def _update_user(self, body):
        conn = _db()
        if "nickname" in body:
            conn.execute("UPDATE users SET nickname=? WHERE id='u001'", (body["nickname"],))
        if "homeName" in body:
            conn.execute("UPDATE users SET home_name=? WHERE id='u001'", (body["homeName"],))
        if "memberCount" in body:
            conn.execute("UPDATE users SET member_count=? WHERE id='u001'", (body["memberCount"],))
        r = conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        conn.commit(); conn.close()
        return {"id": r[0], "nickname": r[1], "homeName": r[2], "memberCount": r[3]}

    # ===== AI 对话 =====
    def _chat(self, body):
        msgs = body.get("messages", [])
        if not msgs:
            return {"reply": "请输入消息", "role": "assistant"}
        last_msg = msgs[-1].get("content", "")

        # ★ 1. 设备控制意图检测 → 直接调用硬件
        _dev_ctrl = self._detect_device_control(last_msg)
        if _dev_ctrl:
            return _dev_ctrl

        # ★ 2. 状态查询意图检测 → 返回固定格式真实数据
        _status_query = self._detect_status_query(last_msg)
        if _status_query:
            return _status_query

        # ★ 3. RAG 固定回复
        fixed_reply = _rag.match_reply(last_msg)
        if fixed_reply:
            conn = _db()
            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (last_msg,))
            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (fixed_reply,))
            conn.commit(); conn.close()
            _tts_speak(fixed_reply)
            return {"reply": fixed_reply, "role": "assistant", "source": "rag", "voiceSequence": [_vs_entry(fixed_reply)]}

        # ★ 4. RAG 场景匹配
        scene_match = _rag.search_scene(last_msg)
        if scene_match and scene_match.get("scene_id"):
            result = self._activate_scene(scene_match["scene_id"])
            if result.get("success"):
                hw_ok = result.get("hardwareOnline", False)
                if hw_ok:
                    _vs_reply = f"已切换到「{result['scene_name']}」模式，控制 {result['affected_count']} 台设备"
                else:
                    _vs_reply = f"「{result['scene_name']}」模式调用失败，设备离线"
                _tts_speak(_vs_reply)
                return {"reply": _vs_reply, "role": "assistant", "scene_id": scene_match["scene_id"], "voiceSequence": result.get("voiceSequence", [])}

        # ★ 5. AI 大模型
        conn = _db()
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (last_msg,))
        reply = chat(msgs)
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
        conn.commit(); conn.close()
        _tts_speak(reply)
        return {"reply": reply, "role": "assistant", "voiceSequence": [_vs_entry(reply)]}

    def _detect_device_control(self, text):
        """检测设备控制意图，直接调用硬件"""
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
        dev_id = None
        is_on = None

        for kw in _ON_KEYWORDS:
            if kw in text:
                is_on = True
                break
        if is_on is None:
            for kw in _OFF_KEYWORDS:
                if kw in text:
                    is_on = False
                    break
        if is_on is None:
            return None

        for kw, did in _DEV_KEYWORDS.items():
            if kw in text:
                dev_id = did
                break
        if dev_id is None and "灯" in text:
            dev_id = "light_01"
        if dev_id is None:
            return None

        dev_name = _DEVICE_NAMES.get(dev_id, dev_id)
        hw_result = hw_toggle(dev_id, is_on)
        hw_ok = hw_result["success"]

        # 更新缓存
        with _STATUS_LOCK:
            _DEVICE_STATUS[dev_id] = {
                "is_on": is_on if hw_ok else _DEVICE_STATUS.get(dev_id, {}).get("is_on", False),
                "primary_value": 100 if is_on else 0 if hw_ok else _DEVICE_STATUS.get(dev_id, {}).get("primary_value", 0),
                "online": hw_ok,
                "ts": time.time()
            }

        conn = _db()
        conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (text,))
        if hw_ok:
            reply = f"[操作结果] {dev_name}已{'开启' if is_on else '关闭'}成功\n[设备状态] {dev_name}: {'开启' if is_on else '关闭'}"
        else:
            reply = f"[操作结果] {dev_name}{'开启' if is_on else '关闭'}失败\n[设备状态] {dev_name}: 设备离线"
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
        conn.commit(); conn.close()

        _tts_speak(reply.replace("[操作结果] ", "").replace("[设备状态] ", ""))
        return {"reply": reply, "role": "assistant", "voiceSequence": [_vs_entry(reply)], "hardwareOnline": hw_ok}

    def _detect_status_query(self, text):
        """检测状态查询意图，返回固定格式真实数据"""
        _STATUS_KEYWORDS = [
            "状态", "温度", "湿度", "检查", "查询", "查看", "现在",
            "怎么样", "什么情况", "有没有", "是否", "在线",
            "烟雾", "热敏", "窗帘位置", "灯", "空调",
            "status", "check", "query", "temperature", "humidity"
        ]
        text_lower = text.strip().lower()
        is_status_query = any(kw in text_lower for kw in _STATUS_KEYWORDS)
        if not is_status_query:
            return None

        # 确认不是控制指令（包含开关关键词的不算纯查询）
        _CTRL_KEYWORDS = ["打开", "开启", "关闭", "关掉", "启动", "停止"]
        if any(kw in text for kw in _CTRL_KEYWORDS):
            return None

        # 构建固定格式状态报告
        with _STATUS_LOCK:
            temp_s = _SENSOR_STATUS.get("temp_01", {})
            humid_s = _SENSOR_STATUS.get("humid_01", {})
            light01 = _DEVICE_STATUS.get("light_01", {})
            ac01 = _DEVICE_STATUS.get("ac_01", {})
            door01 = _DEVICE_STATUS.get("door_01", {})
            alarm01 = _DEVICE_STATUS.get("alarm_01", {})
            light02 = _DEVICE_STATUS.get("light_02", {})
            smoke_s = _SENSOR_STATUS.get("smoke_01", {})
            heat_s = _SENSOR_STATUS.get("heat_01", {})
            light04 = _DEVICE_STATUS.get("light_04", {})
            fan02 = _DEVICE_STATUS.get("fan_02", {})
            light03 = _DEVICE_STATUS.get("light_03", {})
            curtain01 = _DEVICE_STATUS.get("curtain_01", {})

        def _fmt_online(ok):
            return "" if ok else "(离线)"

        reply = f"""[客厅]{_fmt_online(temp_s.get('online', False))}
  温度: {temp_s.get('value', '?')}°C
  湿度: {humid_s.get('value', '?')}%RH
  客厅灯: {'开' if light01.get('is_on') else '关'}{_fmt_online(light01.get('online', False))}
  空调: {'开' if ac01.get('is_on') else '关'}{_fmt_online(ac01.get('online', False))}
  大门: {'开' if door01.get('is_on') else '关'}{_fmt_online(door01.get('online', False))}
  蜂鸣器: {'开' if alarm01.get('is_on') else '关'}{_fmt_online(alarm01.get('online', False))}

[厨房]{_fmt_online(smoke_s.get('online', False))}
  烟雾: {'报警' if smoke_s.get('is_alert') else '正常'}
  热敏: {heat_s.get('value', '?')}mV
  厨房灯: {'开' if light02.get('is_on') else '关'}(亮度{light02.get('primary_value', '?')}%){_fmt_online(light02.get('online', False))}

[卫生间]{_fmt_online(light04.get('online', False))}
  卫生间灯: {'开' if light04.get('is_on') else '关'}(亮度{light04.get('primary_value', '?')}%)
  换气扇: {'开' if fan02.get('is_on') else '关'}(风速{fan02.get('primary_value', '?')}%)

[卧室]{_fmt_online(light03.get('online', False))}
  卧室灯: {'开' if light03.get('is_on') else '关'}(亮度{light03.get('primary_value', '?')}%)
  窗帘: 位置{curtain01.get('primary_value', '?')}%{_fmt_online(curtain01.get('online', False))}"""

        conn = _db()
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (text,))
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
        conn.commit(); conn.close()

        # TTS 简短播报
        tts_text = f"客厅温度{temp_s.get('value', '?')}度，湿度{humid_s.get('value', '?')}%，厨房烟雾{'报警' if smoke_s.get('is_alert') else '正常'}"
        _tts_speak(tts_text)

        return {"reply": reply, "role": "assistant", "source": "realtime_status", "voiceSequence": [_vs_entry(tts_text)]}


def load_env():
    global DEEPSEEK_API_KEY
    ep = ROOT / "HarmonyOS-mcp-server" / ".deepseek_env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
                if k.strip() == "DEEPSEEK_API_KEY":
                    DEEPSEEK_API_KEY = v.strip()


def main():
    load_env()
    db_init()
    # 传感器轮询线程
    threading.Thread(target=sensor_poll_thread, daemon=True).start()
    log("[POLL] 传感器轮询已启动，间隔10秒")

    # 厨房UDP报警监听线程
    threading.Thread(target=udp_alarm_listener, daemon=True).start()

    # 启动数据推送服务
    try:
        from data_pusher import start_pusher
        start_pusher()
        log("[PUSHER] 数据推送服务已启动 → yuanzhe.tech")
    except Exception as e:
        log(f"[PUSHER] 推送服务启动失败: {e}")

    # 启动网络通道服务
    try:
        from channel import start_channel, tts_speak
        start_channel()
        log("[CHANNEL] 网络通道服务已启动 → yuanzhe.tech")
    except ImportError:
        log("[CHANNEL] 通道模块不可用，TTS输出降级为静音")
    except Exception as e:
        log(f"[CHANNEL] 通道服务启动失败: {e}")

    # 硬件状态
    if _HW_OK:
        log("[HW] ✓ 硬件控制已加载 (central_controller)")
    else:
        log("[HW] ✗ 硬件控制未加载，降级为数据库模式")

    srv = ThreadingHTTPServer((HOST, PORT), H)
    log("=" * 50)
    log(f"智慧家居网关v4 :{PORT} {_AI_CONFIG.get('provider', 'deepseek')}")
    log(f"硬件控制: {'已启用' if _HW_OK else '未加载'}")
    log(f"轮询间隔: {_POLL_INTERVAL}秒")
    log(f"RAG知识库: {_rag.get_stats()}")
    log(f"数据库: {DB_PATH}")
    log(f"报警联动: 厨房→客厅蜂鸣器(上升沿+UDP)")
    log(f"TTS: 语音输出(播报) only, 输入由 /api/voice/input 接管")
    log("=" * 50)
    srv.serve_forever()


if __name__ == "__main__":
    main()
