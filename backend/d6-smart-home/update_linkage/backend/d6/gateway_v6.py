#!/usr/bin/env python3
"""
智慧家居安全远程 API 网关 v6 · 国密双层加密 + 完整远程控制
在 /data/A9/ 设备上运行

v6 变更 (基于 v5):
  - 新增国密双层加密: 传输层 SM4-CBC + 应用层 SM2 签名/SM3 摘要
  - 新增 Token 认证系统 (SM3-HMAC 签名 Token)
  - 新增 /api/auth/* 认证接口
  - 新增 /api/secure/* 加密通信接口
  - 新增 /api/remote/* 远程管理接口
  - 新增请求签名验证 + Nonce 防重放
  - 新增 API Key 管理
  - 保留 v5 全部功能 (本地 HTTP 不加密, 远程 API 加密)
  - 保留硬件轮询 + 厨房联动 + 安全护栏 + AI 对话 + TTS
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import struct
import sys
import threading
import time
import zlib
import ssl
from datetime import datetime, timezone, timedelta

# ===== 时区: Asia/Shanghai (UTC+8) =====
_CST = timezone(timedelta(hours=8))

def _cst_now():
    """返回 Asia/Shanghai 时区的当前时间"""
    return datetime.now(_CST)

def _cst_today_str():
    """返回 Asia/Shanghai 时区的今日日期字符串 YYYY-MM-DD"""
    return _cst_now().strftime("%Y-%m-%d")

def _cst_now_str():
    """返回 Asia/Shanghai 时区的当前时间字符串 YYYY-MM-DD HH:MM:SS"""
    return _cst_now().strftime("%Y-%m-%d %H:%M:%S")
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

# ===== 路径配置 =====
HOST = "0.0.0.0"
PORT = 8080
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "control" / "data" / "smart_home.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "db" / "schema.sql"
LOG_PATH = ROOT / "gateway_v6.log"
SMART_HOME_DIR = Path(__file__).resolve().parent
PROJECT_CONTEXT_PATH = SMART_HOME_DIR / "project_context.json"
VOICE_CONFIG_PATH = SMART_HOME_DIR / "voice_control.json"
VOICE_STATUS_PATH = SMART_HOME_DIR / "voice_bridge_status.json"
VOICE_DISABLED_PATH = SMART_HOME_DIR / "voice.disabled"
VOICE_BRIDGE_PATH = SMART_HOME_DIR / "voice_bridge_d6.py"
OFFLINE_MODEL_CONFIG_PATH = SMART_HOME_DIR / "offline_model.json"
MAX_MCP_BODY_BYTES = 1024 * 1024
MCP_ALLOWED_ORIGINS = {
    item.strip()
    for item in os.environ.get(
        "A9_MCP_ALLOWED_ORIGINS",
        "http://127.0.0.1:8080,http://localhost:8080",
    ).split(",")
    if item.strip()
}

# ===== 导入加密模块 =====
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gm_crypto import (
    sm3_hash, sm4_encrypt, sm4_decrypt,
    SM2KeyPair, sm2_sign, sm2_verify,
    SecureEnvelope, generate_sm4_key, generate_sm2_keypair,
    generate_token, verify_token, sm3_hkdf,
    _nonce_check, quick_encrypt, quick_decrypt,
)

# ===== 导入其他模块 =====
from rag.rag_service import SimpleRAG
_rag = SimpleRAG()

from context_engine import ContextEngine
from ai_provider_router import ProviderRouter, extract_text_content
from adaptive_guard import AdaptiveGuard
from proactive_intelligence import ProactiveIntelligence
from bounded_http_server import BoundedThreadingHTTPServer
from gateway_context_runtime import build_turn_context, merge_context_summaries
from notification_service import NotificationService
from super_mcp import COMPATIBLE_VERSIONS, PROTOCOL_VERSION, SuperMCP
from external_intelligence import ExternalIntelligenceCollector
try:
    from hardware_bridge_compat import set_living_light_auto
except ImportError:
    set_living_light_auto = lambda enabled: {
        "success": False, "data": {}, "error": "光敏灯现场协议适配器未加载",
    }

_context_engine = None
_super_mcp = None
_adaptive_guard = None
_proactive_intelligence = None
_notification_service = None
_external_intelligence = None
_external_digest_cache = {"success": True, "categories": [], "items": []}
_external_digest_at = 0.0
_external_digest_lock = threading.Lock()
_VOICE_BRIDGE_LOCK = threading.RLock()
_voice_bridge_process = None

from safety_shield import shield as _shield

# ===== 导入意图引擎 =====
from intent_engine import (
    IntentEngine, get_device_capabilities, build_ai_intent_prompt,
    parse_ai_commands as _orig_parse_ai_commands, strip_ai_commands, DEVICE_NAMES as _INTENT_DEV_NAMES,
    DeviceRegistry, ConversationMemory, EmotionAnalyzer,
    LinkageEngine, EnergyAdvisor,
)

# 扩展 parse_ai_commands 支持 <<CALL:>> 指令
def parse_ai_commands(reply: str) -> list:
    commands = _orig_parse_ai_commands(reply)
    # 新增 <<CALL:/api/path:METHOD:params_json>>
    for m in re.finditer(r'<<CALL:([^:>]+):(\w+):(\{[^>]*\})>>', reply):
        api_path, method, params_str = m.group(1), m.group(2), m.group(3)
        try:
            params = json.loads(params_str)
        except Exception:
            params = {}
        commands.append({"type": "call", "api_path": api_path, "method": method, "params": params})
    return commands

try:
    from hardware_bridge import (
        hw_toggle, hw_control, hw_sensor_read, hw_scene_execute,
        hw_all_status, hw_living_status, hw_kitchen_status,
        hw_bathroom_status, hw_bedroom_status,
        _DEVICE_NAMES as _HW_DEV_NAMES,
        get_auth_status, verify_door_password_api,
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
    get_auth_status = lambda: {"enable_auth": False, "door_password_required": False, "shared_key_set": False}
    verify_door_password_api = lambda p=None: (True, None)


def _configure_field_nonce_clock():
    """补偿 D6 与现场板卡控制机的时钟差，避免门禁防重放误拒绝。"""
    controller = sys.modules.get("central_controller")
    if controller is None or not hasattr(controller, "next_nonce"):
        return False
    skew_ms = max(0, int(os.environ.get("A9_FIELD_NONCE_SKEW_MS", "15000")))
    nonce_lock = threading.Lock()
    last_nonce = [0]

    def d6_nonce():
        with nonce_lock:
            value = (int(time.time() * 1000) + skew_ms) & 0xFFFFFFFF
            if value <= last_nonce[0]:
                value = (last_nonce[0] + 1) & 0xFFFFFFFF
            last_nonce[0] = value
            return value

    controller.next_nonce = d6_nonce
    return True


_configure_field_nonce_clock()

# ===== AI 配置 =====
_AI_CONFIG = {
    "provider": os.environ.get("AI_PROVIDER", "astron"),
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
        "codex": {
            "url": os.environ.get("CODEX_API_URL", ""),
            "key": os.environ.get("CODEX_API_KEY", ""),
            "model": os.environ.get("CODEX_MODEL", "gpt-5.6-sol"),
            "wireApi": "responses",
            "maxTokens": int(os.environ.get("CODEX_MAX_TOKENS", "4096")),
            "reasoningEffort": os.environ.get("CODEX_REASONING_EFFORT", "medium"),
        },
        "offline": {
            "url": os.environ.get("OFFLINE_MODEL_URL", "http://192.168.1.11:8080/v1/chat/completions"),
            "key": os.environ.get("OFFLINE_MODEL_KEY", ""),
            "model": os.environ.get("OFFLINE_MODEL", "local-model"),
            "requiresKey": False,
            "timeout": float(os.environ.get("OFFLINE_MODEL_TIMEOUT", "4")),
            "maxTokens": int(os.environ.get("OFFLINE_MODEL_MAX_TOKENS", "1024")),
            "temperature": 0.3,
        },
    },
}
_ai_router = None
_LAST_AI_PROVIDER = ""
_PENDING_INTENT_PLANS: dict[str, dict] = {}
_PENDING_PLAN_LOCK = threading.Lock()
_NEGATED_EXECUTION = re.compile(r"(?:不要|别|先别|暂不|取消|不需要|不用|别执行|不要执行)")
_EXPLICIT_DEVICE = re.compile(r"(?:客厅主灯|厨房灯|卧室灯|卫生间灯|灯|空调|窗帘|换气扇|排气扇|门禁|大门)")
_EXPLICIT_ACTION = re.compile(r"(?:打开|开启|关闭|关掉|熄灭|调到|设为|设置为|升高|降低|开门|关门|停止)")


def is_explicit_execution_request(text: str) -> bool:
    """Only direct action language may execute without a plan confirmation."""
    normalized = str(text or "").strip()
    if not normalized or _NEGATED_EXECUTION.search(normalized):
        return False
    return bool(_EXPLICIT_DEVICE.search(normalized) and _EXPLICIT_ACTION.search(normalized))


def _direct_device_intent(text: str) -> dict | None:
    """Small deterministic bridge for clear device phrases before AI fallback."""
    normalized = str(text or "").strip()
    state = True if re.search(r"(?:打开|开启|开|点亮)", normalized) else False if re.search(r"(?:关闭|关掉|关|熄灭)", normalized) else None
    if state is None:
        return None
    targets = (
        ("客厅主灯", "light_01"), ("厨房灯", "light_02"), ("卧室灯", "light_03"),
        ("卫生间灯", "light_04"), ("换气扇", "fan_02"), ("排气扇", "fan_02"),
        ("空调", "ac_01"), ("窗帘", "curtain_01"),
    )
    for label, device_id in targets:
        if label in normalized:
            return {"type": "device_toggle", "device_id": device_id, "isOn": state,
                    "reason": f"用户明确要求{label}{'开启' if state else '关闭'}"}
    if re.search(r"(?:开灯|关灯)$", normalized):
        return {"type": "device_toggle", "device_id": "light_01", "isOn": state,
                "reason": "用户明确要求客厅主灯变更状态"}
    return None


def _plan_confirmation_enabled() -> bool:
    if _adaptive_guard is None:
        return True
    try:
        return bool(_adaptive_guard.get_config().get("planConfirmation", {}).get("enabled", True))
    except Exception:
        return True


def _format_intent_plan(intent: dict) -> str:
    """Explain an inferred device plan without executing it."""
    intent = dict(intent or {})
    intent_type = str(intent.get("type", "")).lower()
    device_id = str(intent.get("device_id", ""))
    device_name = _DEVICE_NAMES.get(device_id, device_id or "待确认设备")
    if intent_type == "scene":
        target = intent.get("scene_name") or intent.get("scene_id") or "当前需求"
        detail = f"根据当前状态推导“{target}”所需的设备组合"
    elif intent_type == "device_toggle":
        detail = f"{device_name} → {'开启' if intent.get('isOn', True) else '关闭'}"
    elif intent_type == "device_control":
        detail = f"{device_name} → {intent.get('action', '调整')} {json.dumps(intent.get('params', {}), ensure_ascii=False)}"
    else:
        detail = "先读取相关设备和历史状态，再决定是否调整"
    return (
        "计划草案（尚未执行）\n"
        f"推断目标：{intent.get('reason', '根据当前对话、设备表和历史上下文推导')}\n"
        f"具体设备计划：{detail}\n"
        "依据：实时状态、最近操作、历史行为和可用能力\n"
        "审核方式：无需输入确认文字，请在助手卡片下方点击“确认执行”一键执行；点击“取消计划”不会调用设备接口。"
    )


def _format_command_plan(commands: list[dict]) -> str:
    visible_commands = _safe_plan_commands(commands)
    lines = []
    for command in visible_commands:
        if command.get("type") == "device":
            device = _DEVICE_NAMES.get(str(command.get("device_id", "")), str(command.get("device_id", "待确认设备")))
            lines.append(f"{device} → {command.get('action', '调整')} {json.dumps(command.get('params', {}), ensure_ascii=False)}")
        elif command.get("type") == "scene":
            lines.append(f"根据当前状态组合设备（原始目标：{command.get('scene_id', '需求')})")
        else:
            lines.append(f"调用 {command.get('type', '系统')} 能力")
    return (
        "计划草案（尚未执行）\n"
        "推断依据：当前对话、实时设备表、历史操作与检索上下文\n"
        "具体设备计划：\n- " + "\n- ".join(lines) +
        "\n审核方式：无需输入确认文字，请在助手卡片下方点击“确认执行”一键执行；点击“取消计划”不会调用设备接口。"
    )


def _safe_plan_commands(commands: list[dict]) -> list[dict]:
    """Keep only user-visible device mutations; never hide API calls in a plan."""
    return [
        json.loads(json.dumps(command))
        for command in commands
        if isinstance(command, dict) and command.get("type") in {"device", "scene"}
    ][:8]


def _normalize_ambiguous_ai_reply(user_text: str, reply: str) -> str:
    """Turn an upstream generic fallback into one useful, safe clarification."""
    if is_explicit_execution_request(user_text):
        return reply
    text = str(reply or "")
    generic_tokens = ("没能理解", "没理解", "有什么智能家居方面", "请问有什么")
    if not any(token in text for token in generic_tokens):
        return reply
    return (
        "我已读取实时设备、最近操作和历史上下文。\n"
        "当前信息还不足以安全推导唯一方案；请补充一个目标（例如希望更安静、降低温度，"
        "或只查看状态）。我会先列出具体设备计划，等你确认后执行，不会直接套用场景或擅自操作。"
    )


def _plan_scope(body: dict) -> str:
    user_id = str(body.get("userId", body.get("user_id", "u001")) or "u001")[:80]
    session_id = str(body.get("sessionId", body.get("session_id", "default")) or "default")[:120]
    return f"{user_id}:{session_id}"


def _put_pending_plan(scope: str, payload: dict) -> dict:
    now = time.time()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    plan_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    entry = {
        "payload": json.loads(json.dumps(payload)),
        "createdAt": now,
        "expiresAt": now + 300,
        "planNonce": secrets.token_urlsafe(12),
        "planDigest": plan_digest,
        "idempotencyKey": secrets.token_urlsafe(18),
        "status": "pending",
    }
    with _PENDING_PLAN_LOCK:
        _PENDING_INTENT_PLANS[scope] = entry
    return dict(entry)


def _get_pending_plan(scope: str, plan_nonce: str = "") -> dict | None:
    with _PENDING_PLAN_LOCK:
        entry = _PENDING_INTENT_PLANS.get(scope)
        if not entry:
            return None
        if float(entry.get("expiresAt", 0)) < time.time():
            _PENDING_INTENT_PLANS.pop(scope, None)
            return None
        if plan_nonce and plan_nonce != str(entry.get("planNonce", "")):
            return None
        return json.loads(json.dumps(entry))


def _clear_pending_plan(scope: str) -> None:
    with _PENDING_PLAN_LOCK:
        _PENDING_INTENT_PLANS.pop(scope, None)


def _claim_pending_plan(scope: str, plan_nonce: str, plan_digest: str = "") -> dict | None:
    """Atomically claim one plan so repeated Confirm cannot execute it twice."""
    with _PENDING_PLAN_LOCK:
        entry = _PENDING_INTENT_PLANS.get(scope)
        if not entry or float(entry.get("expiresAt", 0)) < time.time():
            return None
        if str(entry.get("planNonce", "")) != str(plan_nonce):
            return None
        if plan_digest and str(entry.get("planDigest", "")) != str(plan_digest):
            return None
        if entry.get("status") != "pending":
            result = json.loads(json.dumps(entry))
            result["_claimed_here"] = False
            return result
        entry["status"] = "claimed"
        entry["claimedAt"] = time.time()
        result = json.loads(json.dumps(entry))
        result["_claimed_here"] = True
        return result

# ===== 设备定义 =====
DEVICE_DEFS = [
    {"id": "light_01", "name": "客厅主灯",   "type": "light",  "room": "客厅", "icon": "lightbulb",      "area": "living_room"},
    {"id": "ac_01",    "name": "客厅空调",   "type": "ac",     "room": "客厅", "icon": "air_fill",        "area": "living_room"},
    {"id": "door_01",  "name": "客厅大门",   "type": "door",   "room": "客厅", "icon": "lock",            "area": "living_room"},
    {"id": "alarm_01", "name": "蜂鸣警报",   "type": "alarm",  "room": "客厅", "icon": "bell_fill",       "area": "living_room"},
    {"id": "light_02", "name": "厨房灯",     "type": "light",  "room": "厨房", "icon": "lightbulb",       "area": "kitchen"},
    {"id": "light_04", "name": "卫生间灯",   "type": "light",  "room": "卫生间", "icon": "lightbulb",     "area": "bathroom"},
    {"id": "fan_02",   "name": "换气扇",     "type": "fan",    "room": "卫生间", "icon": "fan_fill_1",   "area": "bathroom"},
    {"id": "light_03", "name": "卧室灯",     "type": "light",  "room": "卧室", "icon": "lightbulb",       "area": "bedroom"},
    {"id": "curtain_01","name": "智能窗帘",  "type": "curtain","room": "卧室", "icon": "lock_open_fill",  "area": "bedroom"},
    {"id": "voice_01", "name": "语音控制",   "type": "voice",  "room": "中控", "icon": "mic_fill",        "area": "controller"},
]

REMOVED_LEGACY_DEVICE_IDS = {"fan_01", "exhaust_01"}


def _visible_devices(devices: list[dict]) -> list[dict]:
    return [
        item for item in devices
        if str(item.get("id", "")) not in REMOVED_LEGACY_DEVICE_IDS
    ]

SENSOR_DEFS = [
    {"id": "temp_01",  "name": "客厅温度", "type": "temperature", "group": "环境监测", "room": "客厅", "icon": "thermometer", "unit": "°C",  "thresholdMax": 28, "area": "living_room"},
    {"id": "humid_01", "name": "客厅湿度", "type": "humidity",    "group": "环境监测", "room": "客厅", "icon": "drop",        "unit": "%RH", "thresholdMax": 70, "area": "living_room"},
    {"id": "smoke_01", "name": "烟雾检测", "type": "smoke",       "group": "安防",     "room": "厨房", "icon": "flame_fill",  "unit": "正常", "area": "kitchen"},
    {"id": "heat_01",  "name": "热敏火灾", "type": "heat",        "group": "安防",     "room": "厨房", "icon": "flame_fill",  "unit": "mV",   "area": "kitchen"},
    {"id": "air_01",   "name": "综合报警", "type": "air_quality", "group": "安防",     "room": "厨房", "icon": "wind",        "unit": "",     "area": "kitchen"},
]

AREA_DEFS = {
    "living_room": {"name": "客厅", "ip": "192.168.1.62", "port": 8000, "device": "Hi3861"},
    "kitchen":     {"name": "厨房", "ip": "192.168.1.23", "port": 8000, "device": "H3863", "udp_port": 8001},
    "bathroom":    {"name": "卫生间", "ip": "192.168.1.63", "port": 8000, "device": "H3863"},
    "bedroom":     {"name": "卧室", "ip": "192.168.1.64", "port": 8000, "device": "H3863"},
}

_DEVICE_NAMES = {d["id"]: d["name"] for d in DEVICE_DEFS}

# ===== 实时状态缓存 =====
_DEVICE_STATUS = {}
_SENSOR_STATUS = {}
_AREA_ONLINE = {}
_STATUS_LOCK = threading.Lock()

# ===== 厨房报警联动 =====
_last_kitchen_alarm = 0
_ALARM_LOCK = threading.Lock()
_KITCHEN_POLL_INTERVAL = 1.0
_OTHER_POLL_INTERVAL = 10.0

# ===== 联动规则配置 =====
_LINKAGE_CONFIG = {
    "kitchen_alarm_buzzer": {
        "enabled": True,          # 厨房烟雾/过温 -> 客厅蜂鸣器
        "clear_on_recovery": True,
        "description": "厨房烟雾或过温报警上升沿触发客厅蜂鸣器，恢复后关闭"
    },
    "kitchen_alarm_exhaust": {
        "enabled": True,          # 厨房烟雾/过温 -> 卫生间换气扇
        "description": "厨房报警联动换气扇排烟"
    },
    "temp_humidity_ac": {
        "enabled": False,         # 客厅温湿度异常 -> 空调联动
        "cool_on_temp_c": 30,
        "cool_off_temp_c": 27,
        "dry_on_humi_pct": 75,
        "dry_off_humi_pct": 65,
        "cool_profile": "COOL_26_AUTO",
        "dry_profile": "DRY_26_AUTO",
        "description": "客厅温度>=30°C联动空调制冷，湿度>=75%联动空调除湿"
    },
    "door_event_broadcast": {
        "enabled": True,          # 门禁事件 -> 记录和播报
        "tts_on_open": True,
        "tts_on_close": True,
        "log_to_db": True,
        "description": "门禁事件记录到数据库并TTS播报"
    },
    "radar_light": {
        "enabled": False,         # 雷达/人体感应 -> 灯光控制
        "description": "雷达检测到人体时自动开启对应区域灯光(需雷达模块支持)"
    },
    "radar_presence": {
        "enabled": True,          # 毫米波人体存在功能总开关；与灯光联动独立
        "source_device": "bathroom",
        "sensor": "Rd-03 V2",
        "description": "毫米波人体存在感知总开关"
    },
    "living_light_auto": {
        "enabled": True,
        "device_id": "light_01",
        "mode": "auto",
        "description": "客厅光敏灯使用现场 LIGHT AUTO 模式"
    }
}
_LINKAGE_LOCK = threading.Lock()


def _linkage_master_enabled() -> bool:
    """统一读取设置页的联动自动管理总开关。"""
    if _adaptive_guard is None:
        return True
    try:
        return bool(_adaptive_guard.get_config().get("enabled", True))
    except Exception:
        return False


def _load_linkage_config():
    """从SQLite加载联动配置"""
    global _LINKAGE_CONFIG
    try:
        conn = _db()
        rows = conn.execute("SELECT rule_key, config_json FROM linkage_config").fetchall()
        conn.close()
        if not rows:
            return
        for rule_key, config_json in rows:
            try:
                import json as _json
                saved = _json.loads(config_json)
                if rule_key in _LINKAGE_CONFIG:
                    _LINKAGE_CONFIG[rule_key].update(saved)
            except Exception:
                pass
        log(f"[LINKAGE] 从SQLite加载了 {len(rows)} 条联动配置")
    except Exception as e:
        log(f"[LINKAGE] 加载配置失败: {e}")


def _save_linkage_config():
    """保存联动配置到SQLite"""
    try:
        import json as _json
        conn = _db()
        conn.execute("DELETE FROM linkage_config")
        for rule_key, cfg in _LINKAGE_CONFIG.items():
            conn.execute(
                "INSERT INTO linkage_config(rule_key, config_json, updated_at) VALUES(?,?,datetime('now','+8 hours'))",
                (rule_key, _json.dumps(cfg, ensure_ascii=False))
            )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"[LINKAGE] 保存配置失败: {e}")


# ===== KV上下文引擎 =====
_DEVICE_TYPE_CAPS = {
    "light": ["on", "off", "set_brightness", "query"],
    "ac": ["on", "off", "set_temp", "set_mode", "set_fan", "set_swing", "query"],
    "fan": ["on", "off", "set_speed", "forward", "stop", "reverse", "query"],
    "curtain": ["on", "off", "set_position", "query"],
    "door": ["on", "off", "query"],
    "alarm": ["on", "off", "alarm", "query"],
    "camera": ["query"],
    "smoke": ["query"],
}


def _get_device_caps(dev_type):
    return _DEVICE_TYPE_CAPS.get(dev_type, ["on", "off", "query"])


def _build_api_list():
    """构建可调用API列表"""
    return [
        {"path": "/mcp", "methods": ["POST"], "desc": "MCP 2025-11-25 Streamable HTTP JSON-RPC", "auth": "API Key/Bearer"},
        {"path": "/api/ai/context/manifest", "methods": ["GET"], "desc": "完整脱敏项目上下文 JSON", "auth": "read"},
        {"path": "/api/ai/context/stats", "methods": ["GET"], "desc": "上下文采集统计", "auth": "read"},
        {"path": "/api/ai/context/search", "methods": ["GET", "POST"], "desc": "源码/文档/实体/日志混合检索", "auth": "read"},
        {"path": "/api/ai/context/rebuild", "methods": ["POST"], "desc": "全量重建上下文", "auth": "admin"},
        {"path": "/api/ai/context/events", "methods": ["GET"], "desc": "最近脱敏上下文事件", "auth": "read",
         "params": {"GET": {"limit": "int? (1-500)", "severity": "string?"}}},
        {"path": "/api/ai/radar/config", "methods": ["GET", "POST"], "desc": "毫米波总开关与雷达灯联动独立配置", "auth": "read/admin",
         "params": {"GET": {}, "POST": {"enabled": "boolean"}}},
        {"path": "/api/ai/linkage/config", "methods": ["GET", "POST"], "desc": "联动规则配置", "auth": "read/admin",
         "params": {"GET": {}, "POST": {"rule_key": "string", "config": "object"}}},
        {"path": "/api/ai/linkage/rules", "methods": ["GET"], "desc": "联动规则列表", "auth": "read"},
        {"path": "/api/ai/linkage/log", "methods": ["GET"], "desc": "联动执行日志", "auth": "read"},
        {"path": "/api/ai/guard/status", "methods": ["GET"], "desc": "自适应警戒状态与待评分统计", "auth": "read"},
        {"path": "/api/ai/guard/config", "methods": ["GET", "POST"], "desc": "主动/被动警戒与规则配置", "auth": "read/admin"},
        {"path": "/api/ai/guard/incidents", "methods": ["GET"], "desc": "警戒事件和自动动作记录", "auth": "read"},
        {"path": "/api/ai/guard/feedback", "methods": ["POST"], "desc": "主人对自动动作提交0-10评分与改进建议", "auth": "write"},
        {"path": "/api/ai/guard/learning", "methods": ["GET"], "desc": "长期评分学习摘要与相关反馈", "auth": "read"},
        {"path": "/api/ai/assistant/feed", "methods": ["GET"], "desc": "助手主动智能与警戒事件流", "auth": "read"},
        {"path": "/api/ai/status/check", "methods": ["POST"], "desc": "手动触发一次五分钟状态检测", "auth": "write"},
        {"path": "/api/ai/offline/config", "methods": ["GET", "POST"], "desc": "离线模型路由开关", "auth": "write"},
        {"path": "/api/ai/plan/confirm", "methods": ["POST"], "desc": "助手计划卡幂等确认执行", "auth": "write"},
        {"path": "/api/ai/plan/cancel", "methods": ["POST"], "desc": "助手计划卡取消", "auth": "write"},
        {"path": "/api/ai/external/feed", "methods": ["GET"], "desc": "天气、交通、新闻、科技与行情的有来源摘要", "auth": "read"},
        {"path": "/api/ai/external/config", "methods": ["GET", "POST"], "desc": "外部信息采集开关与位置/数据源配置", "auth": "write"},
        {"path": "/api/ai/assistant/feedback", "methods": ["POST"], "desc": "助手事件1-10评分与A-D改进选项", "auth": "write"},
        {"path": "/api/app/telemetry", "methods": ["POST"], "desc": "脱敏记录App主控行为与非请求数据", "auth": "write"},
        {"path": "/api/log/chart", "methods": ["GET"], "desc": "日志实时与近七日图表数据", "auth": "read"},
        {"path": "/api/devices", "methods": ["GET"], "desc": "设备列表", "auth": "read"},
        {"path": "/api/sensors", "methods": ["GET"], "desc": "传感器列表", "auth": "read"},
        {"path": "/api/hardware/status", "methods": ["GET"], "desc": "硬件状态", "auth": "read"},
        {"path": "/api/ai/context/kv", "methods": ["GET", "POST", "DELETE"], "desc": "KV知识库管理", "auth": "read/admin/admin",
         "params": {"GET": {"namespace": "string?", "key": "string?"}, "POST": {"namespace": "string", "key": "string", "value": "any", "priority": "int?"}, "DELETE": {"namespace": "string", "key": "string"}}},
        {"path": "/api/ai/context/kv/dump", "methods": ["GET"], "desc": "导出全部KV", "auth": "read"},
        {"path": "/api/ai/context/kv/sync", "methods": ["POST"], "desc": "从代码同步KV", "auth": "admin"},
        {"path": "/api/ai/push/config", "methods": ["GET", "POST"], "desc": "推送配置", "auth": "read/admin"},
        {"path": "/api/ai/push/status", "methods": ["GET"], "desc": "推送状态", "auth": "read"},
        {"path": "/api/ai/push/test", "methods": ["POST"], "desc": "推送测试", "auth": "write"},
        {"path": "/api/ai/emotion", "methods": ["POST"], "desc": "情感分析", "auth": "read"},
        {"path": "/api/ai/intent", "methods": ["POST"], "desc": "意图解析", "auth": "write"},
        {"path": "/api/chat/send", "methods": ["POST"], "desc": "AI对话", "auth": "write"},
    ]


def _build_capability_desc():
    """构建AI能力格式描述"""
    return [
        {"name": "设备控制", "format": "<<DEVICE:device_id:action:params_json>>",
         "examples": ["<<DEVICE:light_01:on:{}>>", '<<DEVICE:ac_01:set_temp:{"value":26}>>', '<<DEVICE:curtain_01:set_position:{"value":50}>>']},
        {"name": "场景激活", "format": "<<SCENE:scene_id>>",
         "examples": ["<<SCENE:s1>>", "<<SCENE:s3>>"]},
        {"name": "状态查询", "format": "<<QUERY:type>>",
         "examples": ["<<QUERY:temperature>>", "<<QUERY:all>>"]},
        {"name": "定时任务", "format": "<<SCHEDULE:time_expr:action_json>>",
         "examples": ['<<SCHEDULE:20:00:{"type":"scene","scene_id":"s3"}>>']},
        {"name": "QQ推送", "format": "<<PUSH:priority:title:message>>",
         "examples": ["<<PUSH:high:警报:厨房烟雾报警>>"]},
        {"name": "API调用", "format": "<<CALL:/api/path:METHOD:params_json>>",
         "examples": ['<<CALL:/api/ai/linkage/config:POST:{"rule_key":"kitchen_alarm_exhaust","config":{"enabled":true}}>>', '<<CALL:/api/ai/context/kv:POST:{"namespace":"custom","key":"my_note","value":"备忘"}>>']},
    ]


def _build_protocol_knowledge():
    """构建协议知识KV"""
    return {
        "aa55_packet": {"size": 32, "format": "AA55+LEN+CMD+CONTENT(20bytes)+CRC32",
                        "devices": {"kitchen": "CMD4=status/CMD5=light", "bathroom": "CMD6=status/CMD7=light/CMD8=fan",
                                    "bedroom": "CMD9=status/CMD10=light/CMD11=curtain_pos/CMD12=curtain_action"}},
        "hi3861_text": {"format": "ASCII命令+AUTH+nonce_hex+tag_hex", "device": "living_room",
                        "commands": ["LIGHT ON/OFF", "AC ON/OFF/MODE/TEMP/FAN/SWING", "BEEP ON/OFF/ALARM", "DOOR OPEN/CLOSE",
                                     "TEMP", "EVENT"]},
        "hmac_sm3_tag32": {"algorithm": "HMAC-SM3取前4字节uint32_le", "shared_key": "配置在devices.json",
                           "binary": "auth_tag = uint32_le(HMAC-SM3(key, content[0:20])[0:4])",
                           "text": "auth_tag = uint32_le(HMAC-SM3(key, 'CMD|nonce_hex')[0:4])"},
        "kitchen_udp": {"port": 8001, "broadcast": "255.255.255.255", "format": "JSON",
                        "fields": "type,ip,thermal_mv,smoke_level,smoke_alarm,temp_alarm,alarm,light,brightness"},
        "voice_bridge": {"frame_format": "AA 55 <category> <command> FB", "mappings": 40,
                         "examples": {"AA550001FB": "开客厅灯", "AA550007FB": "开蜂鸣器", "AA550021FB": "雷达联动"}},
        "radar_zone": {"sensor": "Rd-03 V2 on bathroom UART1", "zones": 4,
                       "ranges": "kitchen 20-35cm, bathroom 40-55cm, living_room 60-85cm, bedroom 90-110cm",
                       "filter": "7-sample window, 5 stable required"},
        "door_password": {"algorithm": "PBKDF2-SHA256", "iterations": 120000,
                          "salt": "A9_LIVING_DOOR_DEMO_SALT_V1", "env_var": "A9_DOOR_PASSWORD"},
        "nfc": {"module": "PN532 I2C", "mode": "NFC_ALLOW_ANY_CARD=1", "action": "直接开门"},
    }


def _sync_kv_from_code():
    """从代码定义同步到KV表(不覆盖custom namespace)"""
    conn = _db()
    synced = 0
    # 同步设备
    for d in DEVICE_DEFS:
        kv_val = json.dumps({
            "name": d["name"], "type": d["type"], "room": d["room"],
            "area": d["area"], "icon": d.get("icon", ""),
            "capabilities": _get_device_caps(d["type"]),
        }, ensure_ascii=False)
        conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                     ("device", d["id"], kv_val, 1, "device_defs"))
        synced += 1
    # 同步传感器
    for s in SENSOR_DEFS:
        kv_val = json.dumps({
            "name": s["name"], "type": s["type"], "room": s.get("room", ""),
            "unit": s.get("unit", ""), "thresholdMax": s.get("thresholdMax"),
            "area": s.get("area", ""),
        }, ensure_ascii=False)
        conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                     ("sensor", s["id"], kv_val, 1, "sensor_defs"))
        synced += 1
    # 同步联动规则
    for rk, rv in _LINKAGE_CONFIG.items():
        conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                     ("linkage", rk, json.dumps(rv, ensure_ascii=False), 2, "linkage_config"))
        synced += 1
    # 同步场景
    try:
        from scenes.scene_config import SCENE_META
        for sid, meta in SCENE_META.items():
            conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                         ("scene", sid, json.dumps(meta, ensure_ascii=False), 1, "scene_config"))
            synced += 1
    except Exception:
        pass
    # 同步API列表
    api_list = _build_api_list()
    conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                 ("api", "all_apis", json.dumps(api_list, ensure_ascii=False), 2, "api_registry"))
    synced += 1
    # 同步AI能力格式
    capabilities = _build_capability_desc()
    conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                 ("capability", "all_formats", json.dumps(capabilities, ensure_ascii=False), 2, "system"))
    synced += 1
    # 同步协议知识
    protocol_knowledge = _build_protocol_knowledge()
    for pk, pv in protocol_knowledge.items():
        conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                     ("protocol", pk, json.dumps(pv, ensure_ascii=False), 0, "protocol_doc"))
        synced += 1
    conn.commit()
    conn.close()
    log(f"[KV] 同步了 {synced} 条KV记录")


def _update_kv_realtime():
    """轮询后更新KV中的实时状态"""
    try:
        conn = _db()
        with _STATUS_LOCK:
            for d in DEVICE_DEFS:
                cached = _DEVICE_STATUS.get(d["id"], {})
                row = conn.execute("SELECT value FROM ai_context_kv WHERE namespace='device' AND key=?", (d["id"],)).fetchone()
                if row:
                    try:
                        val = json.loads(row[0])
                        val["status"] = "开" if cached.get("is_on") else "关"
                        val["online"] = cached.get("online", False)
                        val["primary_value"] = cached.get("primary_value")
                        conn.execute("UPDATE ai_context_kv SET value=? WHERE namespace='device' AND key=?",
                                    (json.dumps(val, ensure_ascii=False), d["id"]))
                    except Exception:
                        pass
            for s in SENSOR_DEFS:
                cached = _SENSOR_STATUS.get(s["id"], {})
                row = conn.execute("SELECT value FROM ai_context_kv WHERE namespace='sensor' AND key=?", (s["id"],)).fetchone()
                if row:
                    try:
                        val = json.loads(row[0])
                        val["value"] = cached.get("value")
                        val["is_alert"] = cached.get("is_alert", False)
                        val["online"] = cached.get("online", False)
                        conn.execute("UPDATE ai_context_kv SET value=? WHERE namespace='sensor' AND key=?",
                                    (json.dumps(val, ensure_ascii=False), s["id"]))
                    except Exception:
                        pass
        # 更新最近操作日志
        try:
            rows = conn.execute("SELECT device_id,action,source,created_at FROM device_operations ORDER BY id DESC LIMIT 10").fetchall()
            ops = [{"device": r[0], "action": r[1], "source": r[2], "time": r[3]} for r in rows]
            conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                         ("log", "recent_ops", json.dumps(ops, ensure_ascii=False), 0, "realtime"))
        except Exception:
            pass
        # 更新报警状态
        try:
            alarm_state = json.dumps({
                "kitchen_alarm": _last_kitchen_alarm,
                "buzzer_on": _DEVICE_STATUS.get("alarm_01", {}).get("is_on", False),
                "exhaust_on": _DEVICE_STATUS.get("fan_02", {}).get("is_on", False),
                "temp": _SENSOR_STATUS.get("temp_01", {}).get("value"),
                "humidity": _SENSOR_STATUS.get("humid_01", {}).get("value"),
            }, ensure_ascii=False)
            conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,?,datetime('now','+8 hours'))",
                         ("log", "alarm_state", alarm_state, 2, "realtime"))
        except Exception:
            pass
        conn.commit()
        conn.close()
    except Exception:
        pass


def _build_kv_context(user_msg: str) -> str:
    """构建KV上下文，注入到system prompt"""
    try:
        conn = _db()
        # 1. 始终注入: priority >= 2
        always_rows = conn.execute(
            "SELECT namespace, key, value FROM ai_context_kv WHERE priority >= 2 ORDER BY namespace, key"
        ).fetchall()
        # 2. 关键词匹配: priority = 1
        related_rows = []
        if user_msg:
            # 提取关键词(中文词+英文词)
            kw_list = re.findall(r'[一-鿿]{1,4}|[a-zA-Z_]{2,}', user_msg)
            for kw in kw_list[:5]:  # 最多5个关键词
                try:
                    rows = conn.execute(
                        "SELECT namespace, key, value FROM ai_context_kv WHERE priority = 1 AND (key LIKE ? OR value LIKE ?) LIMIT 20",
                        (f"%{kw}%", f"%{kw}%")
                    ).fetchall()
                    related_rows.extend(rows)
                except Exception:
                    pass
        conn.close()
        # 去重
        seen = set()
        all_rows = []
        for row in always_rows + related_rows:
            rk = (row[0], row[1])
            if rk not in seen:
                seen.add(rk)
                all_rows.append(row)
        # 组装
        sections = {}
        for ns, key, val in all_rows:
            sections.setdefault(ns, []).append(f"  {key}: {val}")
        ns_order = ["capability", "api", "linkage", "device", "sensor", "scene", "protocol", "custom", "log"]
        parts = []
        for ns in ns_order:
            if ns in sections:
                parts.append(f"### {ns.upper()}\n" + "\n".join(sections[ns]))
        return "\n\n".join(parts) if parts else ""
    except Exception as e:
        log(f"[KV] 构建上下文失败: {e}")
        return ""


def _build_runtime_context(user_msg: str) -> str:
    """Build a compact, fresh context packet for every model turn.

    It deliberately combines live state, recent operations, sensor history,
    prior proactive reports, and semantic context hits. The packet is bounded
    so historical collection cannot crowd out the user's current request.
    """
    packet = {"当前时间": _cst_now_str(), "实时状态": {}, "近期操作": [], "传感器历史": [], "历史汇报": [], "近期日志": [], "检索命中": []}
    try:
        packet["实时状态"] = _context_live_state()
    except Exception:
        packet["实时状态"] = {"error": "实时状态暂不可用"}
    try:
        conn = _db()
        op_rows = conn.execute(
            "SELECT device_id, action, params_json, result, source, created_at "
            "FROM device_operations ORDER BY COALESCE(created_ts, 0) DESC, id DESC LIMIT 20"
        ).fetchall()
        for row in op_rows:
            try:
                params = json.loads(row[2] or "{}")
            except (TypeError, ValueError):
                params = {"解析失败": True}
            packet["近期操作"].append(
                {"设备": row[0], "动作": row[1], "参数": params,
                 "结果": row[3], "来源": row[4], "时间": row[5]}
            )
        sensor_rows = conn.execute(
            "SELECT sensor_id, value, unit, created_at FROM sensor_readings "
            "ORDER BY created_at DESC LIMIT 80"
        ).fetchall()
        packet["传感器历史"] = [
            {"传感器": row[0], "值": row[1], "单位": row[2], "时间": row[3]}
            for row in sensor_rows
        ]
        report_rows = conn.execute(
            "SELECT kind, title, summary, severity, created_at FROM assistant_proactive_reports "
            "ORDER BY created_ts DESC, id DESC LIMIT 10"
        ).fetchall()
        packet["历史汇报"] = [
            {"类型": row[0], "标题": row[1], "摘要": row[2], "级别": row[3], "时间": row[4]}
            for row in report_rows
        ]
        if _context_engine is not None:
            log_rows = conn.execute(
                "SELECT event_type, summary, source, severity, created_at "
                "FROM ai_context_events ORDER BY id DESC LIMIT 20"
            ).fetchall()
            packet["近期日志"] = [
                {"类型": row[0], "摘要": row[1], "来源": row[2], "级别": row[3], "时间": row[4]}
                for row in log_rows
            ]
        conn.close()
    except Exception as exc:
        packet["数据读取异常"] = type(exc).__name__
    if _context_engine is not None and str(user_msg or "").strip():
        try:
            hits = _context_engine.search(str(user_msg), limit=12, event_limit=20)
            packet["检索命中"] = hits if isinstance(hits, list) else []
        except Exception:
            packet["检索命中"] = []
    # Bound each collection independently so search hits and current state are
    # not lost merely because one history stream grew large.
    packet["传感器历史"] = packet["传感器历史"][:48]
    packet["近期日志"] = packet["近期日志"][:16]
    packet["检索命中"] = packet["检索命中"][:12]

    # Keep the context valid JSON even when a custom device or a long log entry
    # contains unusually large payloads. Shrink whole collections in priority
    # order instead of slicing the serialized string in the middle of a token.
    def _encode() -> str:
        return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))

    encoded = _encode()
    for key, minimum in (("检索命中", 4), ("近期日志", 6), ("历史汇报", 4), ("传感器历史", 12), ("近期操作", 8)):
        if len(encoded) <= 14000:
            break
        values = packet.get(key)
        if isinstance(values, list) and len(values) > minimum:
            packet[key] = values[:minimum]
            encoded = _encode()
    if len(encoded) > 14000:
        # The live state and current request remain more valuable than old
        # history. Trim oversized text fields as a final, still-valid step.
        for key in ("历史汇报", "近期日志", "检索命中", "传感器历史", "近期操作"):
            for item in packet.get(key, []):
                if isinstance(item, dict):
                    for field, value in list(item.items()):
                        if isinstance(value, str) and len(value) > 240:
                            item[field] = value[:240]
            encoded = _encode()
            if len(encoded) <= 14000:
                break
    return encoded

# ===== 国密密钥配置 =====
_KEYS_DIR = Path(__file__).resolve().parent / "keys"
_KEYS_DIR.mkdir(parents=True, exist_ok=True)

# SM4 传输层密钥 (设备与远程服务器共享)
_SM4_KEY_FILE = _KEYS_DIR / "sm4_transport.key"
# SM2 设备密钥对 (设备端签名用)
_SM2_KEY_FILE = _KEYS_DIR / "sm2_device.key"
# SM2 远程服务器公钥 (验证远程服务器签名)
_SM2_REMOTE_PUB_FILE = _KEYS_DIR / "sm2_remote.pub"
# Token 签名密钥
_TOKEN_SECRET_FILE = _KEYS_DIR / "token_secret.key"
# API Key 数据库
_API_KEY_DB = _KEYS_DIR / "api_keys.db"


def _load_or_generate_sm4_key() -> bytes:
    """加载或生成 SM4 传输层密钥"""
    if _SM4_KEY_FILE.exists():
        key = bytes.fromhex(_SM4_KEY_FILE.read_text().strip())
        if len(key) == 16:
            return key
    key = generate_sm4_key()
    _SM4_KEY_FILE.write_text(key.hex())
    os.chmod(str(_SM4_KEY_FILE), 0o600) if hasattr(os, 'chmod') else None
    return key


def _load_or_generate_sm2_keypair() -> SM2KeyPair:
    """加载或生成 SM2 设备密钥对"""
    if _SM2_KEY_FILE.exists():
        try:
            d = int(_SM2_KEY_FILE.read_text().strip(), 16)
            return SM2KeyPair(private_key=d)
        except Exception:
            pass
    kp = generate_sm2_keypair()
    _SM2_KEY_FILE.write_text(kp.private_key_hex)
    os.chmod(str(_SM2_KEY_FILE), 0o600) if hasattr(os, 'chmod') else None
    return kp


def _load_or_generate_token_secret() -> bytes:
    """加载或生成 Token 签名密钥"""
    if _TOKEN_SECRET_FILE.exists():
        secret = bytes.fromhex(_TOKEN_SECRET_FILE.read_text().strip())
        if len(secret) >= 32:
            return secret[:32]
    secret = os.urandom(32)
    _TOKEN_SECRET_FILE.write_text(secret.hex())
    os.chmod(str(_TOKEN_SECRET_FILE), 0o600) if hasattr(os, 'chmod') else None
    return secret


def _load_remote_pubkey() -> bytes | None:
    """加载远程服务器 SM2 公钥"""
    if _SM2_REMOTE_PUB_FILE.exists():
        try:
            return bytes.fromhex(_SM2_REMOTE_PUB_FILE.read_text().strip())
        except Exception:
            pass
    return None


# 初始化密钥
_SM4_KEY = _load_or_generate_sm4_key()
_SM2_KEYPAIR = _load_or_generate_sm2_keypair()
_TOKEN_SECRET = _load_or_generate_token_secret()
_REMOTE_SM2_PUB = _load_remote_pubkey()

# 安全信封实例
_envelope = SecureEnvelope(_SM4_KEY, _SM2_KEYPAIR)

# ===== 意图引擎上下文函数 =====
def _get_intent_context() -> dict:
    """获取意图引擎所需的上下文(设备状态+传感器+时间)"""
    ctx = {"hour": datetime.now().hour, "weekday": datetime.now().weekday()}
    with _STATUS_LOCK:
        for d in DEVICE_DEFS:
            cached = _DEVICE_STATUS.get(d["id"], {})
            ctx[f"{d['id']}_on"] = cached.get("is_on", False) if cached.get("online") else None
        temp_c = _SENSOR_STATUS.get("temp_01", {})
        humid_c = _SENSOR_STATUS.get("humid_01", {})
        smoke_c = _SENSOR_STATUS.get("smoke_01", {})
        heat_c = _SENSOR_STATUS.get("heat_01", {})
        if temp_c.get("online"):
            ctx["temp"] = temp_c.get("raw_temp")
        if humid_c.get("online"):
            ctx["humidity"] = humid_c.get("raw_humidity")
        ctx["smoke_alarm"] = smoke_c.get("is_alert", False) if smoke_c.get("online") else False
        ctx["heat_alarm"] = heat_c.get("is_alert", False) if heat_c.get("online") else False
    return ctx

def _get_anomaly_status() -> dict:
    """获取异常检测器所需的状态"""
    return _get_intent_context()

# 意图引擎实例(延迟初始化, 在 main() 中创建)
_intent_engine: IntentEngine | None = None

# 多协议网关实例(延迟初始化, 在 main() 中创建)
_proto_gateway = None

# ===== API Key 管理 =====
def _init_api_key_db():
    """初始化 API Key 数据库"""
    conn = sqlite3.connect(str(_API_KEY_DB))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id      TEXT PRIMARY KEY,
            api_key     TEXT NOT NULL UNIQUE,
            name        TEXT NOT NULL,
            permissions TEXT DEFAULT 'read',
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now','+8 hours')),
            last_used   TEXT,
            usage_count INTEGER DEFAULT 0,
            rate_limit  INTEGER DEFAULT 100,
            expires_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS api_key_usage (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id      TEXT NOT NULL,
            endpoint    TEXT NOT NULL,
            ip_address  TEXT,
            created_at  TEXT DEFAULT (datetime('now','+8 hours'))
        );
    """)
    # 创建默认管理员 API Key
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM api_keys")
    if cur.fetchone()[0] == 0:
        admin_key = "sm_" + os.urandom(24).hex()[:48]
        conn.execute(
            "INSERT INTO api_keys(key_id, api_key, name, permissions) VALUES(?,?,?,?)",
            ("admin_001", admin_key, "管理员", "read,write,admin,remote")
        )
        conn.commit()
        log(f"[INIT] 管理员 API Key 已创建: {admin_key[:16]}...{admin_key[-8:]}")
    conn.close()


def _verify_api_key(api_key: str, required_permission: str = "read") -> dict | None:
    """验证 API Key"""
    conn = sqlite3.connect(str(_API_KEY_DB))
    row = conn.execute(
        "SELECT key_id, name, permissions, is_active, rate_limit, expires_at FROM api_keys WHERE api_key=?",
        (api_key,)
    ).fetchone()
    if not row:
        conn.close()
        return None

    key_id, name, permissions, is_active, rate_limit, expires_at = row

    if not is_active:
        conn.close()
        return None

    # 过期检查
    if expires_at and expires_at < datetime.now().isoformat():
        conn.close()
        return None

    # 权限检查
    perm_list = permissions.split(",")
    if required_permission not in perm_list and "admin" not in perm_list:
        conn.close()
        return None

    # 更新使用统计
    conn.execute("UPDATE api_keys SET last_used=datetime('now','+8 hours'), usage_count=usage_count+1 WHERE key_id=?",
                 (key_id,))
    conn.commit()
    conn.close()

    return {"key_id": key_id, "name": name, "permissions": perm_list, "rate_limit": rate_limit}


# ===== 日志 =====
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


# ===== TTS =====
_TTS_LOCK = threading.Lock()
_LAST_TTS_TEXT = ""
_LAST_TTS_AT = 0.0
_TTS_COOLDOWN_SECONDS = 12.0
_TTS_URGENT_COOLDOWN_SECONDS = 5.0
_TTS_REPEAT_SECONDS = 60.0
_TTS_THEME_COOLDOWN_SECONDS = 2.5
_TTS_DEVICE_COOLDOWN_SECONDS = 1.5
_TTS_LAST_BY_CATEGORY = {}


def _zh_voice_text(text):
    """把所有进入播报和语音序列的文本收敛为中文可读内容。"""
    value = " ".join(str(text or "").split())
    replacements = {
        "OpenAI": "开放人工智能", "DeepSeek": "深度求索", "Codex": "代码助手",
        "AI": "人工智能", "TTS": "语音播报", "UART": "串口", "MCP": "工具协议",
        "HTTP": "网络协议", "HTTPS": "安全网络协议", "RSS": "订阅源", "D6": "设备六号",
        "WiFi": "无线网络", "MQTT": "消息协议", "API": "接口",
        "weather": "天气", "traffic": "交通", "news": "新闻",
        "technology": "科技", "market": "行情", "offline": "离线",
    }
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        value = value.replace(source, target)
    # 链接和英文标识不适合直接交给中文语音引擎：删除后保留前后中文，
    # 不再用“相关信息”覆盖，避免播报听起来像占位符。
    value = re.sub(r"https?://[^\s，。；！？]+", "", value, flags=re.I)
    value = re.sub(r"[A-Za-z][A-Za-z0-9_.:/-]*", "", value)
    value = re.sub(r"[_-]+", " ", value)
    return " ".join(value.split()).strip()


def _voice_summary(text, max_chars=180):
    """生成完整句子的中文播报摘要，避免百度语音接口截断长文本。"""
    normalized = _zh_voice_text(text)
    if not normalized:
        return ""
    limit = max(60, int(max_chars))
    if len(normalized) <= limit:
        return normalized
    sentences = [part.strip() for part in re.split(r"(?<=[。！？；])|\n+", normalized) if part.strip()]
    suffix = "。详细内容请查看助手。"
    budget = max(1, limit - len(suffix))
    selected = ""
    for sentence in sentences:
        candidate = f"{selected}{sentence}" if not selected else f"{selected} {sentence}"
        if len(candidate) > budget:
            break
        selected = candidate
    if not selected:
        selected = normalized[:budget].rstrip("，、；：")
    return f"{selected}{suffix}"


def _tts_speak(text, category="default"):
    if not text or os.path.exists('/data/A9/smart_home/tts.disabled'):
        return False
    global _LAST_TTS_TEXT, _LAST_TTS_AT, _TTS_LAST_BY_CATEGORY
    normalized = _voice_summary(text)
    if not normalized:
        return False
    now = time.monotonic()
    urgent = any(token in normalized for token in ("报警", "警报", "烟雾", "热敏", "火灾"))
    category = str(category or "default")
    previous_text, previous_at = _TTS_LAST_BY_CATEGORY.get(category, ("", 0.0))
    with _TTS_LOCK:
        if category == "theme":
            cooldown = 0.0 if normalized != previous_text else _TTS_THEME_COOLDOWN_SECONDS
        elif category.startswith("device:"):
            cooldown = _TTS_DEVICE_COOLDOWN_SECONDS
        else:
            cooldown = _TTS_URGENT_COOLDOWN_SECONDS if urgent else _TTS_COOLDOWN_SECONDS
        if now - previous_at < cooldown:
            return False
        if normalized == previous_text and now - previous_at < _TTS_REPEAT_SECONDS:
            return False
        _TTS_LAST_BY_CATEGORY[category] = (normalized, now)
        _LAST_TTS_TEXT = normalized
        _LAST_TTS_AT = now
    def _speak():
        try:
            from channel import tts_speak as _ch_tts
            _ch_tts(normalized)
        except Exception:
            pass
    threading.Thread(target=_speak, daemon=True).start()
    return True


def _vs_entry(text):
    spoken = _voice_summary(text)
    h = hashlib.md5(f"{spoken}_7".encode()).hexdigest()
    return {"text": spoken, "audioUrl": f"/api/tts/audio/{h}.mp3"}


def _public_ai_config():
    """Expose routing health without ever returning credentials or private URLs."""
    models = {}
    for name in ("offline", "deepseek", "iflytek", "codex"):
        config = _AI_CONFIG.get("models", {}).get(name, {})
        models[name] = {
            "model": str(config.get("model", "")),
            "configured": bool(str(config.get("url", "")).strip() and
                               (not config.get("requiresKey", True) or str(config.get("key", "")).strip())),
        }
    return {
        "provider": _LAST_AI_PROVIDER or "deepseek",
        "models": models,
        "routes": {
            "text": (["offline"] if _offline_model_config().get("enabled") else []) + ["deepseek", "codex"],
            "multimodal": ["iflytek", "codex"],
        },
        "responseStorage": False,
    }


def _offline_model_config():
    configured = {}
    try:
        value = json.loads(OFFLINE_MODEL_CONFIG_PATH.read_text("utf-8"))
        if isinstance(value, dict):
            configured = value
    except Exception:
        pass
    model = _AI_CONFIG.get("models", {}).get("offline", {})
    return {
        "enabled": bool(configured.get("enabled", False)),
        "baseUrl": "http://192.168.1.11:8080/v1",
        "endpoint": str(model.get("url", "")),
        "model": str(model.get("model", "local-model")),
        "fallback": ["deepseek", "codex"],
    }


def _set_offline_model_enabled(enabled):
    global _ai_router
    OFFLINE_MODEL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OFFLINE_MODEL_CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"enabled": bool(enabled), "updatedAt": time.time()}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, OFFLINE_MODEL_CONFIG_PATH)
    _ai_router = None
    result = _offline_model_config()
    _record_context_event("ai_route_config", "离线模型路由已更新",
                          details={"enabled": result["enabled"], "endpoint": result["baseUrl"]},
                          source="settings", severity="info")
    _tts_speak("离线模型已开启，连接失败时自动回退在线模型" if result["enabled"] else "离线模型已关闭",
               category="settings")
    return {"success": True, **result}


def _public_tts_config():
    return {
        "enabled": not os.path.exists('/data/A9/smart_home/tts.disabled'),
        "backend": "device-channel",
        "cooldownSeconds": _TTS_COOLDOWN_SECONDS,
        "urgentCooldownSeconds": _TTS_URGENT_COOLDOWN_SECONDS,
        "repeatWindowSeconds": _TTS_REPEAT_SECONDS,
    }


def _read_voice_json():
    try:
        value = json.loads(VOICE_CONFIG_PATH.read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_voice_json(value):
    VOICE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = VOICE_CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, VOICE_CONFIG_PATH)


def _voice_bridge_status():
    status = {}
    try:
        status = json.loads(VOICE_STATUS_PATH.read_text("utf-8"))
    except Exception:
        status = {}
    with _VOICE_BRIDGE_LOCK:
        process = _voice_bridge_process
        if process is not None and process.poll() is not None:
            status["running"] = False
            status.setdefault("lastError", f"语音桥接已退出（返回码 {process.returncode}）")
    return status


def _voice_config():
    configured = _read_voice_json()
    serial_port = str(configured.get("serialPort") or os.environ.get("A9_VOICE_SERIAL", "")).strip()
    enabled = bool(configured.get("enabled", False)) and bool(serial_port)
    status = _voice_bridge_status()
    return {
        "enabled": enabled,
        "serialPort": serial_port,
        "running": bool(status.get("running", False)),
        "pid": int(status.get("pid", 0) or 0),
        "frames": int(status.get("frames", 0) or 0),
        "lastFrameAt": status.get("lastFrameAt"),
        "lastCommand": status.get("lastCommand", ""),
        "lastError": status.get("lastError", "") if serial_port else "串口未配置",
        "inputMode": "D6串口语音",
    }


def _stop_voice_bridge():
    global _voice_bridge_process
    with _VOICE_BRIDGE_LOCK:
        process = _voice_bridge_process
        _voice_bridge_process = None
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _ensure_voice_bridge():
    global _voice_bridge_process
    config = _read_voice_json()
    serial_port = str(config.get("serialPort") or os.environ.get("A9_VOICE_SERIAL", "")).strip()
    if not bool(config.get("enabled", False)) or not serial_port:
        _stop_voice_bridge()
        return _voice_config()
    with _VOICE_BRIDGE_LOCK:
        if _voice_bridge_process is not None and _voice_bridge_process.poll() is None:
            return _voice_config()
        if not VOICE_BRIDGE_PATH.exists():
            config["enabled"] = False
            _write_voice_json(config)
            return _voice_config()
        log_path = SMART_HOME_DIR / "voice_bridge_stdout.log"
        stream = open(log_path, "a", encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        try:
            _voice_bridge_process = subprocess.Popen(
                [sys.executable, str(VOICE_BRIDGE_PATH), "--port", serial_port,
                 "--gateway", f"http://127.0.0.1:{PORT}"],
                cwd=str(SMART_HOME_DIR), env=env, stdout=stream, stderr=stream,
                start_new_session=True,
            )
            log(f"[VOICE] D6串口桥接已启动，等待端口: {serial_port}")
            time.sleep(0.15)
            if _voice_bridge_process.poll() is not None:
                config["enabled"] = False
                config["lastError"] = "串口桥接未能打开，请检查端口和权限"
                _write_voice_json(config)
        except Exception as exc:
            stream.close()
            config["enabled"] = False
            config["lastError"] = str(exc)
            _write_voice_json(config)
            log(f"[VOICE] 串口桥接启动失败: {exc}")
    return _voice_config()


def _set_voice_enabled(enabled, serial_port=None):
    config = _read_voice_json()
    if serial_port is not None:
        serial_port = str(serial_port).strip()
        if serial_port and (not serial_port.startswith("/dev/") or len(serial_port) <= 5):
            return {"success": False, "error": "串口路径必须是明确的设备路径，例如 /dev/ttyS3"}
        config["serialPort"] = serial_port
    current_port = str(config.get("serialPort") or os.environ.get("A9_VOICE_SERIAL", "")).strip()
    if enabled and not current_port:
        config["enabled"] = False
        _write_voice_json(config)
        return {"success": False, "enabled": False, "error": "请先填写 D6 串口路径，系统不会猜测占用端口", "config": _voice_config()}
    config["enabled"] = bool(enabled)
    _write_voice_json(config)
    if enabled:
        try:
            VOICE_DISABLED_PATH.unlink()
        except FileNotFoundError:
            pass
        result = _ensure_voice_bridge()
        return {"success": bool(result.get("enabled")) and bool(result.get("running")), "config": result,
                "error": result.get("lastError", "") if not result.get("running") else ""}
    _stop_voice_bridge()
    try:
        VOICE_DISABLED_PATH.write_text("disabled", encoding="utf-8")
    except Exception:
        pass
    return {"success": True, "config": _voice_config()}


# ===== 数据库 =====
def db_init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text("utf-8"))
    # 新增安全事件表
    conn.execute("""CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id TEXT NOT NULL, severity TEXT NOT NULL,
        category TEXT NOT NULL, input_text TEXT NOT NULL,
        matched_text TEXT NOT NULL, reason TEXT NOT NULL,
        source TEXT DEFAULT 'chat', blocked INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','+8 hours')))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_security_severity ON security_events(severity)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_security_time ON security_events(created_at)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_security_rule ON security_events(rule_id)""")
    # 新增远程访问日志表
    conn.execute("""CREATE TABLE IF NOT EXISTS remote_access_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        method TEXT NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        status_code INTEGER,
        encrypted INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','+8 hours')))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_remote_client ON remote_access_log(client_id)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_remote_time ON remote_access_log(created_at)""")
    # chat_history 增强字段
    try: conn.execute("ALTER TABLE chat_history ADD COLUMN intent_json TEXT")
    except: pass
    try: conn.execute("ALTER TABLE chat_history ADD COLUMN emotion TEXT")
    except: pass
    try: conn.execute("ALTER TABLE chat_history ADD COLUMN source TEXT DEFAULT 'ai'")
    except: pass
    # 每日日志汇总表
    # KV上下文引擎表
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_context_kv (
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        auto_sync TEXT DEFAULT '',
        updated_at TEXT DEFAULT (datetime('now','+8 hours')),
        PRIMARY KEY (namespace, key))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_kv_namespace ON ai_context_kv(namespace)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_kv_priority ON ai_context_kv(priority)""")
    # 联动配置持久化表
    conn.execute("""CREATE TABLE IF NOT EXISTS linkage_config (
        rule_key TEXT PRIMARY KEY,
        config_json TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now','+8 hours')))""")
    # linkage_log 表可能已被 intent_engine 创建(列名 rule_id), 兼容处理
    try: conn.execute("ALTER TABLE linkage_log ADD COLUMN rule_key TEXT")
    except: pass
    try: conn.execute("ALTER TABLE linkage_log ADD COLUMN action_taken TEXT")
    except: pass
    try: conn.execute("ALTER TABLE linkage_log ADD COLUMN detail_json TEXT")
    except: pass
    try: conn.execute("CREATE INDEX IF NOT EXISTS idx_linkage_log_time ON linkage_log(created_at)")
    except: pass
    try: conn.execute("CREATE INDEX IF NOT EXISTS idx_linkage_log_rule ON linkage_log(rule_key)")
    except: pass
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date TEXT NOT NULL UNIQUE,
        total_requests INTEGER DEFAULT 0,
        total_chat INTEGER DEFAULT 0,
        total_device_ops INTEGER DEFAULT 0,
        total_security_events INTEGER DEFAULT 0,
        devices_online_peak INTEGER DEFAULT 0,
        sensors_active INTEGER DEFAULT 0,
        summary_json TEXT,
        created_at TEXT DEFAULT (datetime('now','+8 hours')))""")
    # light_05 was a UI-only duplicate of the physical living-room light.
    for statement in (
        "DELETE FROM scene_actions WHERE device_id='light_05'",
        "DELETE FROM devices WHERE id='light_05'",
        "DELETE FROM custom_device_registry WHERE device_id='light_05'",
        "DELETE FROM device_registry WHERE device_id='light_05'",
    ):
        try:
            conn.execute(statement)
        except sqlite3.Error:
            pass
    conn.commit()
    conn.close()


def _daily_log_update():
    """更新今日daily_log汇总（每次请求时调用，节流5分钟）"""
    try:
        conn = _db()
        today = _cst_today_str()
        # SQL中也使用UTC+8时间，与Python端对齐
        row = conn.execute("SELECT id FROM daily_log WHERE log_date=?", (today,)).fetchone()
        total_req = conn.execute("SELECT COUNT(*) FROM remote_access_log WHERE created_at >= ? AND created_at < ?", (today + " 00:00:00", _cst_now().strftime("%Y-%m-%d") + " 00:00:00" if today == _cst_today_str() else today + " 23:59:59")).fetchone()[0]
        # 使用LIKE匹配日期前缀（created_at格式为 YYYY-MM-DD HH:MM:SS）
        today_prefix = today + "%"
        total_req = conn.execute("SELECT COUNT(*) FROM remote_access_log WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        total_chat = conn.execute("SELECT COUNT(*) FROM chat_history WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        total_ops = conn.execute("SELECT COUNT(*) FROM device_operations WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        total_sec = conn.execute("SELECT COUNT(*) FROM security_events WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        # 峰值追踪：取历史峰值和当前在线的较大值
        with _STATUS_LOCK:
            current_online = sum(1 for s in _DEVICE_STATUS.values() if s.get("online"))
            current_sensors = sum(1 for s in _SENSOR_STATUS.values() if s.get("online"))
        # 读取历史峰值，取较大值
        if row:
            prev = conn.execute("SELECT devices_online_peak, sensors_active FROM daily_log WHERE log_date=?", (today,)).fetchone()
            online_peak = max(current_online, prev[0] if prev and prev[0] else 0)
            sensors_active = max(current_sensors, prev[1] if prev and prev[1] else 0)
        else:
            online_peak = current_online
            sensors_active = current_sensors
        if row:
            conn.execute("UPDATE daily_log SET total_requests=?, total_chat=?, total_device_ops=?, total_security_events=?, devices_online_peak=?, sensors_active=? WHERE log_date=?",
                         (total_req, total_chat, total_ops, total_sec, online_peak, sensors_active, today))
        else:
            conn.execute("INSERT INTO daily_log(log_date,total_requests,total_chat,total_device_ops,total_security_events,devices_online_peak,sensors_active) VALUES(?,?,?,?,?,?,?)",
                         (today, total_req, total_chat, total_ops, total_sec, online_peak, sensors_active))
        conn.commit(); conn.close()
    except Exception:
        pass


_last_daily_update = 0
def _maybe_daily_log_update():
    """节流：最多5分钟更新一次daily_log"""
    global _last_daily_update
    now = time.time()
    if now - _last_daily_update >= 300:
        _last_daily_update = now
        _daily_log_update()


def _db():
    return sqlite3.connect(str(DB_PATH))


# ===== 安全护栏日志 =====
def _log_security(result, input_text, source="chat"):
    try:
        conn = _db()
        conn.execute("INSERT INTO security_events(rule_id,severity,category,input_text,matched_text,reason,source,blocked) VALUES(?,?,?,?,?,?,?,?)",
                     (result.rule_id, result.severity, result.category,
                      input_text[:500], result.matched_text[:200], result.reason, source, 1 if result.blocked else 0))
        conn.commit()
        conn.close()
        log(f"[SHIELD] BLOCKED rule={result.rule_id} sev={result.severity} matched={result.matched_text[:50]}")
        # 广播安全事件
        if _proto_gateway:
            _proto_gateway.broadcast_event("security_alert", {"rule_id": result.rule_id, "severity": result.severity, "category": result.category, "reason": result.reason, "blocked": result.blocked})
    except Exception as e:
        log(f"[SHIELD] log error: {e}")


def _security_block_reply(result):
    _tts_speak(f"检测到非安全指令，已阻止。具体指令：{result.matched_text}")
    return {
        "reply": f"⚠️ 检测到非安全指令，已阻止\n类别：{result.category}\n原因：{result.reason}\n具体指令：\"{result.matched_text}\"",
        "role": "assistant",
        "source": "security_block",
        "voiceSequence": [_vs_entry(f"检测到非安全指令，已阻止。具体指令：{result.matched_text}")],
        "securityBlocked": True,
        "securityRule": result.rule_id,
        "securitySeverity": result.severity
    }


def _log_security_auth(rule_id, input_text, reason, source="api"):
    try:
        conn = _db()
        conn.execute("INSERT INTO security_events(rule_id,severity,category,input_text,matched_text,reason,source,blocked) VALUES(?,?,?,?,?,?,?,?)",
                     (rule_id, "High", "auth", input_text[:500], "", reason[:200], source, 1))
        conn.commit()
        conn.close()
        log(f"[AUTH-SEC] rule={rule_id} reason={reason[:80]}")
    except Exception as e:
        log(f"[AUTH-SEC] log error: {e}")


def _reply_state_is_on(reply: str) -> bool:
    """Parse a hardware reply by field value, never by substring (ACTION contains ON)."""
    normalized = str(reply or "").upper().replace(" ", "")
    return bool(re.search(r"(?:^|,)(?:state|power|action)=(?:ON|OPEN|ALARM|开)(?:,|$)|(?:^|,)alarm=(?:ON|OPEN|ALARM|开)(?:,|$)", normalized))


def _valid_living_environment(data: dict) -> bool:
    try:
        temp = float(data.get("temp"))
        humidity = float(data.get("humidity"))
    except (TypeError, ValueError):
        return False
    if temp == 0 and humidity == 0:
        return False
    return -20 <= temp <= 60 and 0 < humidity <= 100


# ===== 硬件轮询 (与 v5 完全一致) =====
def _poll_living():
    online = False
    try:
        r = hw_sensor_read("temp_01")
        if r["success"] and _valid_living_environment(r.get("data", {})):
            d = r["data"]
            online = True
            with _STATUS_LOCK:
                _SENSOR_STATUS["temp_01"] = {"value": d["temp"], "unit": "°C", "online": True, "ts": time.time(), "is_alert": d["temp"] > 28, "raw_temp": d["temp"]}
                if "humidity" in d:
                    _SENSOR_STATUS["humid_01"] = {"value": d["humidity"], "unit": "%RH", "online": True, "ts": time.time(), "is_alert": d["humidity"] > 70, "raw_humidity": d["humidity"]}
                # 温湿度→空调联动 (受配置控制)
                _check_temp_humidity_ac_linkage(d)
        elif r.get("success"):
            with _STATUS_LOCK:
                _SENSOR_STATUS["temp_01"] = {"online": False, "error": "温湿度设备返回无效零值"}
                _SENSOR_STATUS["humid_01"] = {"online": False, "error": "温湿度设备返回无效零值"}
    except Exception:
        with _STATUS_LOCK:
            _SENSOR_STATUS["temp_01"] = {"online": False}
            _SENSOR_STATUS["humid_01"] = {"online": False}

    try:
        r = hw_living_status("light")
        if r["success"]:
            online = True
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else str(r.get("data", ""))
            is_on = _reply_state_is_on(reply)
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_01"] = {"is_on": is_on, "primary_value": 100 if is_on else 0, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["light_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["light_01"] = {"online": False}

    try:
        r = hw_living_status("ac")
        if r["success"]:
            online = True
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else ""
            is_on = _reply_state_is_on(reply)
            with _STATUS_LOCK:
                _DEVICE_STATUS["ac_01"] = {"is_on": is_on, "primary_value": 24, "online": True, "ts": time.time()}
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["ac_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["ac_01"] = {"online": False}

    try:
        r = hw_living_status("door")
        if r["success"]:
            online = True
            state = r.get("data", {}).get("state", "closed") if isinstance(r.get("data"), dict) else "closed"
            with _STATUS_LOCK:
                was_open = _DEVICE_STATUS.get("door_01", {}).get("is_on", False)
                now_open = state == "open"
                _DEVICE_STATUS["door_01"] = {"is_on": now_open, "primary_value": 0, "online": True, "ts": time.time()}
                # 门禁事件 -> 播报和记录 (受配置控制)
                if was_open != now_open:
                    _handle_door_event(now_open, r.get("data", {}))
        else:
            with _STATUS_LOCK:
                _DEVICE_STATUS["door_01"] = {"online": False}
    except Exception:
        with _STATUS_LOCK:
            _DEVICE_STATUS["door_01"] = {"online": False}

    try:
        r = hw_living_status("beep")
        if r["success"]:
            online = True
            reply = str(r.get("data", {}).get("reply", "")) if isinstance(r.get("data"), dict) else ""
            is_on = _reply_state_is_on(reply)
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
    global _last_kitchen_alarm
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

            alarm_now = d.get("alarm", 0)
            with _ALARM_LOCK:
                if _adaptive_guard is None and alarm_now == 1 and _last_kitchen_alarm == 0:
                    linkage_actions = []
                    # 厨房报警 -> 蜂鸣器 (受配置开关)
                    if _LINKAGE_CONFIG.get("kitchen_alarm_buzzer", {}).get("enabled", True):
                        result = hw_toggle("alarm_01", True)
                        if isinstance(result, dict) and result.get("success"):
                            linkage_actions.append("alarm_01=on")
                        _tts_speak("厨房检测到异常，已触发警报")
                        log("[ALARM-LINKAGE] 厨房报警→蜂鸣器 alarm=1 → BEEP ALARM")
                    else:
                        log("[ALARM] 厨房报警上升沿 alarm=1 (蜂鸣器联动已关闭)")
                    # 厨房报警 -> 换气扇 (受配置开关)
                    if _LINKAGE_CONFIG.get("kitchen_alarm_exhaust", {}).get("enabled", False):
                        result = hw_toggle("fan_02", True)
                        if isinstance(result, dict) and result.get("success"):
                            linkage_actions.append("fan_02=on")
                        _tts_speak("厨房报警，已开启换气扇排烟")
                        log("[ALARM-LINKAGE] 厨房报警→换气扇 alarm=1 → FAN ON")
                    # 记录联动日志
                    try:
                        conn = _db()
                        if linkage_actions:
                            conn.execute("INSERT INTO device_operations(device_id,action,params_json,result,source) VALUES(?,?,?,?,'alarm_linkage')",
                                         ("alarm_01", "alarm_linkage", json.dumps({"trigger": "kitchen_alarm_rising", "actions": linkage_actions, "smoke_alarm": d.get("smoke_alarm"), "temp_alarm": d.get("temp_alarm")}), "ok"))
                        conn.execute("INSERT INTO linkage_log(rule_key,trigger_event,action_taken,result,detail_json) VALUES(?,?,?,?,?)",
                                     ("kitchen_alarm_buzzer", "kitchen_alarm_rising",
                                      ",".join(linkage_actions) or "未执行设备调整",
                                      "ok" if linkage_actions else "failed", json.dumps({"smoke_alarm": d.get("smoke_alarm"), "temp_alarm": d.get("temp_alarm")})))
                        conn.commit(); conn.close()
                    except Exception:
                        pass
                elif _adaptive_guard is None and alarm_now == 0 and _last_kitchen_alarm == 1:
                    # 报警恢复 -> 关蜂鸣器 (受配置)
                    if _LINKAGE_CONFIG.get("kitchen_alarm_buzzer", {}).get("clear_on_recovery", True):
                        hw_toggle("alarm_01", False)
                        _tts_speak("厨房报警已恢复，警报已关闭")
                        log("[ALARM-LINKAGE] 厨房报警恢复 alarm=0 → BEEP OFF")
                    # 报警恢复 -> 关换气扇 (受配置)
                    if _LINKAGE_CONFIG.get("kitchen_alarm_exhaust", {}).get("enabled", False):
                        hw_toggle("fan_02", False)
                        log("[ALARM-LINKAGE] 厨房报警恢复 → 换气扇关闭")
                    try:
                        conn = _db()
                        conn.execute("INSERT INTO linkage_log(rule_key,trigger_event,action_taken,result,detail_json) VALUES(?,?,?,?,?)",
                                     ("kitchen_alarm_buzzer", "kitchen_alarm_recovery",
                                      "alarm_01=off,fan_02=off" if _LINKAGE_CONFIG.get("kitchen_alarm_exhaust", {}).get("enabled") else "alarm_01=off",
                                      "ok", json.dumps({"recovered": True})))
                        conn.commit(); conn.close()
                    except Exception:
                        pass
                _last_kitchen_alarm = alarm_now

            _process_adaptive_guard(d)
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


# ===== 联动辅助函数 =====
_last_temp_ac_state = None   # None/idle/cooling/drying
_last_door_state = None      # 跟踪门状态变化


def _apply_living_light_auto_linkage(announce=False):
    """Align the gateway rule with the field package's ``LIGHT AUTO`` command."""
    cfg = _LINKAGE_CONFIG.get("living_light_auto", {})
    enabled = bool(cfg.get("enabled", True)) and _linkage_master_enabled()
    result = set_living_light_auto(enabled)
    if result.get("success"):
        with _STATUS_LOCK:
            state = dict(_DEVICE_STATUS.get("light_01", {}))
            state["auto_mode"] = bool(enabled)
            state["auto_mode_source"] = "field_LIGHT_AUTO" if enabled else "gateway_disabled"
            _DEVICE_STATUS["light_01"] = state
        log(f"[LINKAGE] 客厅光敏灯 auto_mode={'on' if enabled else 'off'}")
        if announce:
            _tts_speak("客厅光敏灯自动模式已开启" if enabled else "客厅光敏灯自动联动已关闭", category="settings")
    else:
        log(f"[LINKAGE] 客厅光敏灯自动模式失败: {result.get('error', 'unknown')}")
    return result


def _check_temp_humidity_ac_linkage(sensor_data):
    """温湿度异常 -> 空调联动"""
    global _last_temp_ac_state
    if not _linkage_master_enabled():
        return  # 设置页总开关关闭时，所有自动设备动作都停止。
    if _adaptive_guard is not None:
        # 主动警戒已经用同一份实时快照负责温度/湿度空调动作，避免重复下发。
        return
    cfg = _LINKAGE_CONFIG.get("temp_humidity_ac", {})
    if not cfg.get("enabled", False):
        return
    temp = sensor_data.get("temp")
    humi = sensor_data.get("humidity")
    if temp is None:
        return

    new_state = "idle"
    # 优先制冷
    if temp >= cfg.get("cool_on_temp_c", 30):
        new_state = "cooling"
    elif humi is not None and humi >= cfg.get("dry_on_humi_pct", 75):
        new_state = "drying"
    # 恢复条件
    if _last_temp_ac_state == "cooling" and temp < cfg.get("cool_off_temp_c", 27):
        if humi is not None and humi >= cfg.get("dry_on_humi_pct", 75):
            new_state = "drying"  # 温度恢复但湿度仍高，切换除湿
        else:
            new_state = "idle"
    elif _last_temp_ac_state == "drying" and humi is not None and humi < cfg.get("dry_off_humi_pct", 65):
        if temp >= cfg.get("cool_on_temp_c", 30):
            new_state = "cooling"  # 湿度恢复但温度仍高，切换制冷
        else:
            new_state = "idle"

    if new_state != _last_temp_ac_state and new_state != "idle":
        # 触发联动
        if new_state == "cooling":
            r = hw_control("ac_01", "cool", {"profile": cfg.get("cool_profile", "COOL_26_AUTO")})
            _tts_speak(f"客厅温度{temp}度，已自动开启空调制冷")
            log(f"[LINKAGE] 温度{temp}°C>=阈值 → 空调制冷 ({cfg.get('cool_profile', 'COOL_26_AUTO')})")
        elif new_state == "drying":
            r = hw_control("ac_01", "dry", {"profile": cfg.get("dry_profile", "DRY_26_AUTO")})
            _tts_speak(f"客厅湿度{humi}%，已自动开启空调除湿")
            log(f"[LINKAGE] 湿度{humi}%>=阈值 → 空调除湿 ({cfg.get('dry_profile', 'DRY_26_AUTO')})")
        try:
            conn = _db()
            conn.execute("INSERT INTO linkage_log(rule_key,trigger_event,action_taken,result,detail_json) VALUES(?,?,?,?,?)",
                         ("temp_humidity_ac", f"temp={temp},humi={humi}", f"ac_01={new_state}",
                          "ok" if r.get("success") else "fail", json.dumps({"temp": temp, "humidity": humi, "state": new_state})))
            conn.commit(); conn.close()
        except Exception:
            pass
    _last_temp_ac_state = new_state


def _handle_door_event(is_open, event_data):
    """门禁事件 -> 记录和播报"""
    global _last_door_state
    if _adaptive_guard is not None:
        incident = _adaptive_guard.record_door_event(bool(is_open), event_data if isinstance(event_data, dict) else {})
        if _proto_gateway:
            _proto_gateway.broadcast_event("door_event", {"isOpen": bool(is_open), "incidentId": incident.get("id")})
        _last_door_state = bool(is_open)
        return
    cfg = _LINKAGE_CONFIG.get("door_event_broadcast", {})
    if not cfg.get("enabled", True):
        return
    if _last_door_state == is_open:
        return  # 没变化不重复处理
    _last_door_state = is_open

    event_type = "门已打开" if is_open else "门已关闭"
    # TTS播报
    if is_open and cfg.get("tts_on_open", True):
        _tts_speak("门已打开")
    elif not is_open and cfg.get("tts_on_close", False):
        _tts_speak("门已关闭")

    # 记录到数据库
    if cfg.get("log_to_db", True):
        try:
            conn = _db()
            conn.execute("INSERT INTO linkage_log(rule_key,trigger_event,action_taken,result,detail_json) VALUES(?,?,?,?,?)",
                         ("door_event_broadcast", event_type, "tts+log", "ok",
                          json.dumps({"is_open": is_open, "event_data": {k: v for k, v in event_data.items() if isinstance(v, (str, int, float, bool))} if isinstance(event_data, dict) else {}})))
            conn.commit(); conn.close()
        except Exception:
            pass
    log(f"[LINKAGE] 门禁事件: {event_type}")


def sensor_poll_thread():
    log("[POLL] 传感器轮询线程启动 (厨房1秒/其他10秒)")
    last_other = 0
    last_kv_update = 0
    while True:
        now = time.time()
        _poll_kitchen()
        if now - last_other >= _OTHER_POLL_INTERVAL:
            _poll_living()
            _poll_bathroom()
            _poll_bedroom()
            _save_sensor_readings()
            _save_device_snapshots()
            _process_adaptive_guard()
            last_other = now
        # KV实时状态更新(每10秒)
        if now - last_kv_update >= 10.0:
            _update_kv_realtime()
            last_kv_update = now
        time.sleep(_KITCHEN_POLL_INTERVAL)


def _save_sensor_readings():
    try:
        conn = _db()
        with _STATUS_LOCK:
            for sid, sdata in _SENSOR_STATUS.items():
                if sdata.get("online") and "value" in sdata:
                    conn.execute(
                        "INSERT INTO sensor_readings(sensor_id, value, unit, created_at) VALUES(?,?,?,datetime('now','+8 hours'))",
                        (sid, sdata["value"], sdata.get("unit", ""))
                    )
            # 离线传感器也记录(value=-999表示离线)，确保前端能看到真实状态
            for sdef in SENSOR_DEFS:
                sid = sdef["id"]
                if sid not in _SENSOR_STATUS or not _SENSOR_STATUS[sid].get("online"):
                    conn.execute(
                        "INSERT INTO sensor_readings(sensor_id, value, unit, created_at) VALUES(?,?,?,datetime('now','+8 hours'))",
                        (sid, -999.0, sdef.get("unit", ""))
                    )
        conn.commit(); conn.close()
    except Exception:
        pass


# ===== UDP 8001 监听 =====
_UDP_LISTENING = False
def udp_alarm_listener():
    global _last_kitchen_alarm, _UDP_LISTENING
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
            if _adaptive_guard is not None:
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = {"smoke_alarm": 1, "temp_alarm": 0}
                _process_adaptive_guard(payload)
                if _proto_gateway:
                    _proto_gateway.broadcast_event("kitchen_alarm", {"source": addr[0], "message": text[:200], "action": "guard_evaluated"})
            else:
                with _ALARM_LOCK:
                    if _last_kitchen_alarm == 0:
                        _last_kitchen_alarm = 1
                        if _LINKAGE_CONFIG.get("kitchen_alarm_buzzer", {}).get("enabled", True):
                            hw_toggle("alarm_01", True)
                            _tts_speak("厨房UDP报警，已触发警报")
                        if _LINKAGE_CONFIG.get("kitchen_alarm_exhaust", {}).get("enabled", True):
                            hw_toggle("fan_02", True)
                        if _proto_gateway:
                            _proto_gateway.broadcast_event("kitchen_alarm", {"source": addr[0], "message": text[:200], "action": "alarm_triggered"})
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
[客厅] 温度: X°C / 设备离线 ...

## 约束
1. 只回答智能家居相关
2. 不编造数据
3. 回复不超过200字

## 智能控制能力
你可以直接控制设备！在回复中使用以下特殊指令格式：

### 设备控制
<<DEVICE:device_id:action:params_json>>
示例:
- <<DEVICE:light_01:on:{"brightness":80}>>  开客厅灯80%
- <<DEVICE:ac_01:set_temp:{"value":26}>>     空调设26°C
- <<DEVICE:curtain_01:set_position:{"value":50}>> 窗帘开50%
- <<DEVICE:light_01:off:{}>>                 关客厅灯

### 场景激活
<<SCENE:scene_id>>
示例:
- <<SCENE:s3>>  激活睡眠模式
- <<SCENE:s1>>  激活回家模式

### 查询
<<QUERY:type>>
示例:
- <<QUERY:temperature>>  查温度
- <<QUERY:all>>          查全部状态

### API调用(超级MCP)
<<CALL:/api/path:METHOD:params_json>>
示例:
- <<CALL:/api/ai/linkage/config:POST:{"rule_key":"kitchen_alarm_exhaust","config":{"enabled":true}}>>  开启换气扇联动
- <<CALL:/api/ai/linkage/config:GET:{}>>  查询联动配置
- <<CALL:/api/ai/context/kv:POST:{"namespace":"custom","key":"my_note","value":"备忘内容"}>>  写自定义知识
- <<CALL:/api/ai/context/kv:GET:{"namespace":"device"}>>  查设备知识

### 规则
1. 先用自然语言回复用户，再附上控制指令
2. 一个回复可以包含多个指令
3. 不确定时不要输出指令，只回复文字
4. 设备离线时不要输出控制指令
5. 门禁操作需要密码，不要自动开门
6. 用户的模糊意图（"有点暗""太热了""我想看电影"）必须先结合实时状态、设备能力和历史上下文生成可解释的设备计划，不得直接套用场景别名或执行
7. 计划必须列出具体设备、动作、依据和风险，并在助手卡片提供“确认执行”按钮；只有点击按钮或明确动作指令才可调用设备，不要求用户输入确认文字
8. 对可能表达家庭需求的短语不要只回复“没理解”；如果证据不足，先给出一份不执行的候选计划并指出依据，或只问一个最关键的澄清问题
9. 你可以调用API获取信息或修改配置，使用<<CALL:>>指令
10. 你可以往KV知识库写入自定义知识供后续对话使用
"""


def chat(msgs, context_summary: str = ""):
    global _ai_router, _LAST_AI_PROVIDER
    last_msg = extract_text_content(msgs[-1].get("content", "")) if msgs else ""
    rag_ctx = _rag.get_context(last_msg)

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

    # 设备能力描述
    dev_caps = get_device_capabilities(DEVICE_DEFS)
    cap_lines = []
    for dc in dev_caps:
        cap_strs = [f"{c['action']}({','.join(f'{k}={v}' for k,v in c.get('params',{}).items())})" for c in dc["capabilities"]]
        cap_lines.append(f"- {dc['id']}({dc['name']}): {', '.join(cap_strs)}")

    # 场景描述
    scene_lines = []
    try:
        from scenes.scene_config import SCENE_META
        for sid, meta in SCENE_META.items():
            scene_lines.append(f"- {sid}({meta['name']}): {meta['desc']}")
    except ImportError:
        scene_lines = ["- s1(回家) - s2(离家) - s3(睡眠) - s4(观影) - s5(用餐)"]

    # KV上下文引擎
    kv_ctx = _build_kv_context(last_msg)
    runtime_ctx = _build_runtime_context(last_msg)
    guard_ctx = _adaptive_guard.build_context(last_msg) if _adaptive_guard is not None else ""
    sys_msg = _SYSTEM_PROMPT + f"\n\n## 实时设备状态\n{status_ctx}\n"
    sys_msg += f"\n## 可控设备\n{''.join(cap_lines)}\n"
    sys_msg += f"\n## 可用场景\n{chr(10).join(scene_lines)}\n"
    if kv_ctx:
        sys_msg += f"\n## 知识库(KV)\n{kv_ctx}\n"
    if runtime_ctx:
        sys_msg += f"\n## 实时/历史/检索上下文\n{runtime_ctx}\n"
    sys_msg += (
        "\n## 智能判断约束\n"
        "先核对数据时间和在线状态，再判断是否需要动作；历史记录只用于趋势和习惯匹配，不能替代当前实时值。"
        "只有达到明确阈值、存在安全风险或用户明确要求时才调整设备；已是目标状态时不要重复调用。"
        "每次自动调整必须说明触发原因、设备、动作、结果和下一步建议；仅状态汇报不要求评分。\n"
    )
    if guard_ctx:
        sys_msg += f"\n{guard_ctx}\n"
    if rag_ctx:
        sys_msg += f"\n## RAG: {rag_ctx}\n"
    if context_summary:
        sys_msg += f"\n## 对话上下文\n{context_summary}\n"

    try:
        if _ai_router is None:
            _ssl_ctx = ssl.create_default_context(cafile="/data/A9/certs/cacert.pem")
            _ai_router = ProviderRouter(
                _AI_CONFIG.get("models", {}), ssl_context=_ssl_ctx,
                timeout=float(os.environ.get("AI_PROVIDER_TIMEOUT", "30")), logger=log,
            )
        preferred_provider = "offline" if _offline_model_config().get("enabled") else ""
        result = _ai_router.complete([{"role": "system", "content": sys_msg}] + msgs,
                                     preferred_provider=preferred_provider)
        _LAST_AI_PROVIDER = result.provider
        log(f"[CHAT] provider={result.provider} failovers={len(result.errors)}")
        return result.text
    except Exception as e:
        log(f"[CHAT] router_error={type(e).__name__}")
        return "（AI暂时不可用，请稍后重试）"


def _context_live_state():
    """Return a lock-safe, password-free state snapshot for prompt matching."""
    with _STATUS_LOCK:
        devices = []
        for definition in DEVICE_DEFS:
            cached = dict(_DEVICE_STATUS.get(definition["id"], {}))
            devices.append({
                "id": definition["id"], "name": definition["name"],
                "type": definition["type"], "room": definition["room"],
                "online": bool(cached.get("online", False)),
                "isOn": bool(cached.get("is_on", False)),
                "primaryValue": cached.get("primary_value"),
            })
        sensors = []
        for definition in SENSOR_DEFS:
            cached = dict(_SENSOR_STATUS.get(definition["id"], {}))
            sensors.append({
                "id": definition["id"], "name": definition["name"],
                "type": definition["type"], "room": definition["room"],
                "online": bool(cached.get("online", False)),
                "value": cached.get("value"), "unit": cached.get("unit", definition.get("unit")),
                "isAlert": bool(cached.get("is_alert", False)),
            })
        areas = dict(_AREA_ONLINE)
    known_device_ids = {item["id"] for item in devices}
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT id,name,type,room,status,is_on,primary_value FROM devices ORDER BY id"
        ).fetchall()
        conn.close()
        for row in rows:
            if row[0] not in known_device_ids:
                devices.append({
                    "id": row[0], "name": row[1], "type": row[2], "room": row[3],
                    "online": row[4] in ("online", "active"),
                    "isOn": bool(row[5]), "primaryValue": row[6],
                })
                known_device_ids.add(row[0])
    except Exception:
        pass

    if _intent_engine:
        try:
            for template in _intent_engine.list_device_templates():
                device_id = template.get("id")
                if not device_id or device_id in known_device_ids:
                    continue
                devices.append({
                    "id": device_id, "name": template.get("name", device_id),
                    "type": template.get("type", "custom"), "room": template.get("room", ""),
                    "online": False, "isOn": False, "primaryValue": None,
                    "capabilities": template.get("capabilities", []), "custom": True,
                })
                known_device_ids.add(device_id)
        except Exception:
            pass
    with _LINKAGE_LOCK:
        linkage = json.loads(json.dumps(_LINKAGE_CONFIG, ensure_ascii=False))
    return {"devices": devices, "sensors": sensors, "areas": areas, "linkage": linkage}


def _save_device_snapshots():
    """Persist the polled device cache so five-minute reports compare real state."""
    try:
        conn = _db()
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(devices)").fetchall()}
        if "id" not in columns:
            conn.close(); return
        with _STATUS_LOCK:
            snapshots = [(device_id, dict(status)) for device_id, status in _DEVICE_STATUS.items()]
        for device_id, status in snapshots:
            assignments = []
            values = []
            if "status" in columns:
                assignments.append("status=?"); values.append("online" if status.get("online") else "offline")
            if "is_on" in columns and "is_on" in status:
                assignments.append("is_on=?"); values.append(1 if status.get("is_on") else 0)
            if "primary_value" in columns and "primary_value" in status:
                assignments.append("primary_value=?"); values.append(status.get("primary_value"))
            if "updated_at" in columns:
                assignments.append("updated_at=datetime('now','+8 hours')")
            if assignments:
                conn.execute(f"UPDATE devices SET {','.join(assignments)} WHERE id=?", (*values, device_id))
        conn.commit(); conn.close()
    except Exception as exc:
        log(f"[SNAPSHOT] device state persist failed: {type(exc).__name__}")


def _record_context_event(event_type, summary, **kwargs):
    if _context_engine is None:
        return
    try:
        _context_engine.record_event(event_type, summary, **kwargs)
    except Exception as exc:
        log(f"[CONTEXT] 事件记录失败: {exc}")


def _guard_execute(action):
    """Execute only the adaptive guard's fixed device allowlist."""
    device_id = str(action.get("deviceId", ""))
    command = str(action.get("action", ""))
    params = dict(action.get("params") or {})
    if device_id == "door_01":
        return {"success": False, "error": "adaptive guard cannot operate doors"}
    if device_id not in {"ac_01", "alarm_01", "fan_02"}:
        return {"success": False, "error": "device is outside adaptive guard allowlist"}
    if command in ("on", "off"):
        return hw_toggle(device_id, command == "on")
    if device_id == "ac_01" and command in ("cool", "dry", "fan"):
        return hw_control(device_id, command, params)
    return {"success": False, "error": "action is outside adaptive guard allowlist"}


def _guard_snapshot(extra_kitchen=None):
    sensors = []
    with _STATUS_LOCK:
        for definition in SENSOR_DEFS:
            cached = dict(_SENSOR_STATUS.get(definition["id"], {}))
            sensors.append({
                "id": definition["id"], "type": definition["type"], "room": definition["room"],
                "value": cached.get("value"), "isAlert": bool(cached.get("is_alert", False)),
                "online": bool(cached.get("online", False)),
            })
    if isinstance(extra_kitchen, dict):
        sensors = [item for item in sensors if item["id"] not in {"smoke_01", "heat_01"}]
        sensors.extend([
            {"id": "smoke_01", "type": "smoke", "room": "厨房", "value": extra_kitchen.get("smoke_alarm", 0),
             "isAlert": bool(extra_kitchen.get("smoke_alarm", 0)), "online": True},
            {"id": "heat_01", "type": "heat", "room": "厨房", "value": extra_kitchen.get("temp_alarm", 0),
             "isAlert": bool(extra_kitchen.get("temp_alarm", 0)), "online": True},
        ])
    known = {item["id"] for item in sensors}
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT id,type,room,current_value,is_alert FROM sensors WHERE room IN ('客厅','卧室')"
        ).fetchall()
        conn.close()
        for row in rows:
            if row[0] not in known:
                sensors.append({"id": row[0], "type": row[1], "room": row[2], "value": row[3],
                                "isAlert": bool(row[4]), "online": True})
    except Exception:
        pass
    return {"sensors": sensors}


def _process_adaptive_guard(extra_kitchen=None):
    if _adaptive_guard is None:
        return []
    try:
        return _adaptive_guard.process_snapshot(_guard_snapshot(extra_kitchen))
    except Exception as exc:
        log(f"[GUARD] evaluation failed: {type(exc).__name__}")
        return []


def _publish_device_operation(device_id, action_text, success):
    """Expose every manual device action to the assistant feed immediately."""
    if _proactive_intelligence is None:
        return None
    try:
        return _proactive_intelligence.publish_operation(device_id, action_text, bool(success))
    except Exception as exc:
        log(f"[PROACTIVE] operation publish failed: {type(exc).__name__}")
        return None


def _apply_commanded_device_state(device_id, is_on, primary_value=None):
    """Make a successful command visible immediately; polling reconciles later."""
    with _STATUS_LOCK:
        current = dict(_DEVICE_STATUS.get(str(device_id), {}))
        current["is_on"] = bool(is_on)
        current["online"] = True
        current["ts"] = time.time()
        if primary_value is not None:
            current["primary_value"] = primary_value
        elif "primary_value" not in current:
            current["primary_value"] = 100 if bool(is_on) else 0
        _DEVICE_STATUS[str(device_id)] = current
    try:
        _save_device_snapshots()
    except Exception as exc:
        log(f"[STATE] commanded state persist failed: {type(exc).__name__}")


def _initialize_adaptive_guard():
    global _adaptive_guard, _notification_service, _proactive_intelligence
    try:
        notify_ssl = ssl.create_default_context(cafile="/data/A9/certs/cacert.pem")
    except Exception:
        notify_ssl = ssl.create_default_context()
    _notification_service = NotificationService.from_environment(logger=log, ssl_context=notify_ssl)

    def notify_async(event_type, title, message, extra=None):
        threading.Thread(
            target=_notification_service.send,
            args=(event_type, title, message, extra), daemon=True,
        ).start()
        return True

    _adaptive_guard = AdaptiveGuard(
        DB_PATH, executor=_guard_execute, speaker=_tts_speak,
        notifier=notify_async, context_recorder=_record_context_event,
    )
    _proactive_intelligence = ProactiveIntelligence(DB_PATH)
    log(f"[GUARD] initialized mode={_adaptive_guard.get_status(include_incidents=False)['mode']} "
        f"notify={_notification_service.status()['configured']}")


def _run_proactive_cycle_now(manual: bool = False):
    """执行一次与五分钟周期完全相同的状态汇总，供定时器和手动按钮共用。"""
    if _proactive_intelligence is None:
        return []
    external_items = []
    if _external_intelligence is not None:
        try:
            external_items = _external_intelligence.collect().get("items", [])
        except Exception as exc:
            log(f"[EXTERNAL] collect failed: {type(exc).__name__}")
    if manual:
        reports = _proactive_intelligence.run_cycle(external_items=external_items, force=True)
    else:
        reports = _proactive_intelligence.run_cycle(external_items=external_items)
    for report in reports:
        _record_context_event(
            "assistant_proactive", report.get("title", "主动智能报告"),
            details={"reportId": report.get("id"), "kind": report.get("kind"), "evidence": report.get("evidence", {})},
            source="proactive_intelligence", severity=report.get("severity", "info"),
        )
        if report.get("severity") == "warning":
            _tts_speak(report.get("summary", "检测到需要关注的设备行为"))
    return reports


def _proactive_cycle_thread():
    """Run deterministic proactive summaries every five minutes."""
    next_run = time.monotonic()
    while True:
        delay = max(0.0, next_run - time.monotonic())
        if delay:
            time.sleep(delay)
        next_run += 300.0
        if _proactive_intelligence is None:
            continue
        if _adaptive_guard is not None:
            try:
                guard_status = _adaptive_guard.get_status(include_incidents=False)
                if not guard_status.get("activeAiEnabled", True):
                    continue
            except Exception as exc:
                log(f"[PROACTIVE] guard status unavailable: {type(exc).__name__}")
        try:
            _run_proactive_cycle_now()
        except Exception as exc:
            log(f"[PROACTIVE] cycle failed: {type(exc).__name__}")


def _context_sync_thread():
    """Continuously capture new DB state and appended logs without blocking requests."""
    while True:
        time.sleep(30)
        if _context_engine is None:
            continue
        try:
            _context_engine.collect_database_state()
            for source, path in (
                ("gateway", LOG_PATH),
                ("gateway_stdout", ROOT / "gateway_stdout.log"),
            ):
                if path.exists():
                    _context_engine.ingest_log(path, source)
            _context_engine.rebuild_snapshot()
        except Exception as exc:
            log(f"[CONTEXT] 后台同步失败: {exc}")


# ═══════════════════════════════════════════════════════════════
# HTTP 路由处理
# ═══════════════════════════════════════════════════════════════

class H(BaseHTTPRequestHandler):
    timeout = float(os.environ.get("A9_HTTP_CONNECTION_TIMEOUT", "15"))
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

    def _mcp_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        origin = self.headers.get("Origin", "")
        if origin in MCP_ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _mcp_empty(self, status=202):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        self.end_headers()

    def _validate_mcp_origin(self):
        origin = self.headers.get("Origin", "")
        if origin and origin not in MCP_ALLOWED_ORIGINS:
            return False, {"error": "MCP Origin not allowed", "code": 403}
        return True, None

    def _require_mcp_auth(self):
        """Authenticate MCP without the legacy LAN/local-admin shortcut."""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token_info = verify_token(auth_header[7:], _TOKEN_SECRET)
                scopes = token_info.get("permissions") or token_info.get("scopes") or []
                if isinstance(scopes, str):
                    scopes = [item for item in scopes.split(",") if item]
                if not scopes and token_info.get("uid"):
                    conn = sqlite3.connect(str(_API_KEY_DB))
                    row = conn.execute(
                        "SELECT permissions FROM api_keys WHERE key_id=? AND is_active=1",
                        (token_info["uid"],),
                    ).fetchone()
                    conn.close()
                    scopes = row[0].split(",") if row else []
                if not ({"read", "write", "admin"} & set(scopes)):
                    return None, {"error": "MCP token has no usable scope", "code": 403}
                return {**token_info, "scopes": scopes, "transport": "http"}, None
            except ValueError:
                return None, {"error": "MCP bearer token invalid", "code": 401}
        api_key = self.headers.get("X-API-Key", "")
        if api_key:
            key_info = _verify_api_key(api_key, "read")
            if key_info:
                return {**key_info, "scopes": key_info.get("permissions", []), "transport": "http"}, None
            return None, {"error": "MCP API key invalid", "code": 403}
        return None, {"error": "MCP requires Bearer token or X-API-Key", "code": 401}

    def _handle_mcp_post(self):
        valid_origin, origin_error = self._validate_mcp_origin()
        if not valid_origin:
            self._mcp_json(origin_error["code"], origin_error)
            return
        auth, auth_error = self._require_mcp_auth()
        if auth_error:
            self._mcp_json(auth_error["code"], auth_error)
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._mcp_json(415, {"error": "MCP requires application/json", "code": 415})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_MCP_BODY_BYTES:
            self._mcp_json(413, {"error": "MCP body size invalid", "code": 413})
            return
        requested_version = self.headers.get("MCP-Protocol-Version", PROTOCOL_VERSION)
        if requested_version not in COMPATIBLE_VERSIONS:
            self._mcp_json(400, {"error": "Unsupported MCP protocol version", "code": 400})
            return
        try:
            message = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, ValueError):
            self._mcp_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        if not isinstance(message, dict):
            self._mcp_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
            return
        if _super_mcp is None:
            self._mcp_json(503, {"error": "MCP service unavailable", "code": 503})
            return
        response = _super_mcp.dispatch(message, auth=auth)
        if response is None:
            self._mcp_empty(202)
        else:
            self._mcp_json(200, response)

    def do_OPTIONS(self):
        self._j(200, {"ok": True})

    def log_message(self, *a):
        # A timed-out HTTP request may call log_error before request parsing
        # populated command/path; logging must never raise a second exception.
        log(f"{getattr(self, 'command', '?')} {getattr(self, 'path', '?')}")

    # ===== WebSocket 升级处理 =====
    def _handle_ws_upgrade(self):
        """处理HTTP→WebSocket升级请求"""
        if not _proto_gateway:
            self._j(503, {"error": "Protocol gateway not available"})
            return
        try:
            # 读取完整的HTTP请求头
            headers_text = f"GET {self.path} HTTP/1.1\r\n"
            for key, val in self.headers.items():
                headers_text += f"{key}: {val}\r\n"
            headers_text += "\r\n"

            # 获取原始socket
            raw_sock = self.connection
            addr = self.client_address

            # 阻止BaseHTTPRequestHandler关闭连接
            self.close_connection = False

            # 交给ProtocolGateway的WebSocket Server处理
            upgraded = _proto_gateway.handle_ws_upgrade(headers_text, raw_sock, addr)
            if not upgraded:
                self._j(400, {"error": "WebSocket upgrade failed"})
        except Exception as e:
            log(f"[WS] 升级异常: {e}")
            try:
                self._j(500, {"error": str(e)})
            except Exception:
                pass

    # ===== 认证辅助 =====
    def _get_auth(self, required_permission="read"):
        """从请求头获取并验证认证信息, 返回 (auth_info, error_response)"""
        # 1. 尝试 Bearer Token
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                token_info = verify_token(token, _TOKEN_SECRET)
                return token_info, None
            except ValueError as e:
                return None, {"error": f"Token验证失败: {e}", "code": 401}

        # 2. 尝试 API Key
        api_key = self.headers.get("X-API-Key", "")
        if api_key:
            key_info = _verify_api_key(api_key, required_permission)
            if key_info:
                return key_info, None
            return None, {"error": "API Key无效或权限不足", "code": 403}

        # 3. 本地访问免认证 (127.0.0.1 / 192.168.1.x)
        client_ip = self.client_address[0]
        if client_ip.startswith("127.") or client_ip.startswith("192.168.1."):
            return {"uid": "local", "permissions": ["read", "write", "admin", "remote"], "source": "local"}, None

        return None, {"error": "需要认证 (Bearer Token 或 X-API-Key)", "code": 401}

    def _require_auth(self, required_permission="read"):
        """要求认证, 失败直接返回错误响应. 返回 auth_info 或 None"""
        auth_info, err = self._get_auth(required_permission)
        if err:
            self._j(err.get("code", 401), err)
            return None
        return auth_info

    def _log_remote_access(self, auth_info, endpoint, status_code=200, encrypted=False):
        """记录远程访问日志（含本地访问）"""
        if auth_info:
            try:
                conn = _db()
                conn.execute(
                    "INSERT INTO remote_access_log(client_id,endpoint,method,ip_address,status_code,encrypted) VALUES(?,?,?,?,?,?)",
                    (auth_info.get("uid") or auth_info.get("key_id", "unknown"),
                     endpoint, self.command, self.client_address[0], status_code, 1 if encrypted else 0)
                )
                conn.commit(); conn.close()
            except Exception:
                pass
            _maybe_daily_log_update()

    # ===== GET 路由 =====
    def do_GET(self):
        p = self.path.split("?")[0]
        try:
            # ===== WebSocket 升级 =====
            upgrade = self.headers.get("Upgrade", "").lower()
            if upgrade == "websocket" and p == "/ws":
                self._handle_ws_upgrade()
                return

            if p == "/mcp":
                self._mcp_json(405, {"error": "Method Not Allowed", "allow": ["POST"]})
                return

            # ===== 公开接口 (无需认证) =====
            if p == "/health":
                self._j(200, {"ok": True, "v": 6, "hardware": _HW_OK, "crypto": "SM2+SM3+SM4+SM2", "intent_engine": _intent_engine is not None, "protocols": _proto_gateway.get_status() if _proto_gateway else {"http": {"port": 8080}}})

            # ===== 认证接口 =====
            elif p == "/api/auth/public-key":
                self._j(200, self._auth_public_key())

            # ===== 需要认证的接口 =====
            elif p == "/api/devices":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_devices()); self._log_remote_access(auth, p)
            elif p == "/api/sensors":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_sensors()); self._log_remote_access(auth, p)
            elif p == "/api/cameras":
                auth = self._require_auth("read")
                if auth: self._j(200, [{"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "offline"}])
            elif p == "/api/alerts":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_alerts()); self._log_remote_access(auth, p)
            elif p == "/api/user/profile":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_user()); self._log_remote_access(auth, p)
            elif p == "/api/operations":
                auth = self._require_auth("read")
                if auth:
                    qs = self.path.split("?", 1); did = None; days = 7; limit = 200
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                            if k == "device_id": did = v
                            if k == "days": days = int(v)
                            if k == "limit": limit = min(int(v), 1000)
                    self._j(200, self._get_operations(did, days, limit))
                    self._log_remote_access(auth, p)
            elif p == "/api/sensors/history":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_sensor_history()); self._log_remote_access(auth, p)
            elif p == "/api/server/status":
                auth = self._require_auth("read")
                if auth: self._j(200, self._server_status()); self._log_remote_access(auth, p)
            elif p == "/api/check":
                auth = self._require_auth("read")
                if auth: self._j(200, self._check_all()); self._log_remote_access(auth, p)
            elif p == "/api/hardware/status":
                auth = self._require_auth("read")
                if auth: self._j(200, self._hardware_check()); self._log_remote_access(auth, p)
            elif p == "/api/rag/stats":
                auth = self._require_auth("read")
                if auth: self._j(200, _rag.get_stats()); self._log_remote_access(auth, p)
            elif p == "/api/stats":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_stats()); self._log_remote_access(auth, p)
            elif p == "/api/security/events":
                auth = self._require_auth("read")
                if auth:
                    query = parse_qs(urlsplit(self.path).query)
                    try:
                        limit = max(1, min(500, int(query.get("limit", ["100"])[0])))
                    except (TypeError, ValueError):
                        limit = 100
                    self._j(200, self._security_events(limit)); self._log_remote_access(auth, p)
            elif p == "/api/security/stats":
                auth = self._require_auth("read")
                if auth: self._j(200, self._security_stats()); self._log_remote_access(auth, p)
            elif p == "/api/security/auth-status":
                auth = self._require_auth("read")
                if auth: self._j(200, self._auth_status()); self._log_remote_access(auth, p)

            # ===== AI 智能意图接口 =====
            elif p == "/api/ai/capabilities":
                auth = self._require_auth("read")
                if auth: self._j(200, get_device_capabilities(DEVICE_DEFS)); self._log_remote_access(auth, p)
            elif p == "/api/ai/anomaly":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_anomaly_events()); self._log_remote_access(auth, p)
            elif p == "/api/ai/recommendations":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_recommendations()); self._log_remote_access(auth, p)
            elif p == "/api/ai/habit/stats":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_habit_stats()); self._log_remote_access(auth, p)
            elif p == "/api/ai/energy":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_energy()); self._log_remote_access(auth, p)
            elif p == "/api/ai/energy/waste":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_energy_waste()); self._log_remote_access(auth, p)
            elif p == "/api/ai/energy/report":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_energy_report()); self._log_remote_access(auth, p)
            elif p == "/api/ai/linkage/rules":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_linkage_rules()); self._log_remote_access(auth, p)
            elif p == "/api/ai/linkage/log":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_linkage_log()); self._log_remote_access(auth, p)
            elif p == "/api/ai/linkage/config":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_linkage_config()); self._log_remote_access(auth, p)
            elif p == "/api/ai/guard/status":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_guard_status()); self._log_remote_access(auth, p)
            elif p == "/api/ai/guard/config":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_guard_config()); self._log_remote_access(auth, p)
            elif p == "/api/ai/guard/incidents":
                auth = self._require_auth("read")
                if auth:
                    query = parse_qs(urlsplit(self.path).query)
                    limit = min(200, max(1, int(query.get("limit", ["50"])[0])))
                    pending = query.get("pending", ["false"])[0].lower() in ("1", "true", "yes")
                    self._j(200, self._get_guard_incidents(limit, pending)); self._log_remote_access(auth, p)
            elif p == "/api/ai/guard/learning":
                auth = self._require_auth("read")
                if auth:
                    query = parse_qs(urlsplit(self.path).query)
                    text_query = query.get("q", [""])[0]
                    limit = min(100, max(1, int(query.get("limit", ["20"])[0])))
                    self._j(200, self._get_guard_learning(text_query, limit)); self._log_remote_access(auth, p)
            elif p == "/api/ai/assistant/feed":
                auth = self._require_auth("read")
                if auth:
                    query = parse_qs(urlsplit(self.path).query)
                    try:
                        limit = min(100, max(1, int(query.get("limit", ["30"])[0])))
                        since = int(query.get("since", ["0"])[0])
                    except (TypeError, ValueError):
                        limit, since = 30, 0
                    self._j(200, self._get_assistant_feed(limit, since)); self._log_remote_access(auth, p)
            elif p == "/api/ai/external/feed":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_external_feed()); self._log_remote_access(auth, p)
            elif p == "/api/ai/external/config":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_external_config()); self._log_remote_access(auth, p)
            elif p == "/api/ai/push/status":
                auth = self._require_auth("read")
                if auth: self._j(200, _notification_service.status() if _notification_service else {"enabled": False, "configured": False}); self._log_remote_access(auth, p)
            elif p == "/api/ai/context/kv":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_kv()); self._log_remote_access(auth, p)
            elif p == "/api/ai/context/kv/dump":
                auth = self._require_auth("read")
                if auth: self._j(200, self._kv_dump()); self._log_remote_access(auth, p)
            elif p == "/api/ai/emotion":
                # emotion分析是POST，GET返回分析器状态
                self._j(200, {"status": "available"})
            elif p == "/api/ai/context":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_context_summary()); self._log_remote_access(auth, p)
            elif p == "/api/ai/context/manifest":
                auth = self._require_auth("read")
                if auth: self._j(200, self._context_manifest()); self._log_remote_access(auth, p)
            elif p == "/api/ai/context/stats":
                auth = self._require_auth("read")
                if auth: self._j(200, self._context_stats()); self._log_remote_access(auth, p)
            elif p == "/api/ai/context/search":
                auth = self._require_auth("read")
                if auth:
                    query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
                    self._j(200, self._context_search(unquote(query)))
                    self._log_remote_access(auth, p)
            elif p == "/api/ai/context/events":
                auth = self._require_auth("read")
                if auth:
                    params = parse_qs(urlsplit(self.path).query)
                    try:
                        limit = max(1, min(int(params.get("limit", ["100"])[0]), 500))
                    except (TypeError, ValueError):
                        limit = 100
                    severity = params.get("severity", [None])[0]
                    self._j(200, self._get_recent_context_logs(limit, severity))
                    self._log_remote_access(auth, p)
            elif p == "/api/ai/radar/config":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_radar_config()); self._log_remote_access(auth, p)
            elif p == "/api/ai/devices":
                auth = self._require_auth("read")
                if auth: self._j(200, self._list_device_templates()); self._log_remote_access(auth, p)
            elif p == "/api/chat/history":
                auth = self._require_auth("read")
                if auth:
                    qs = self.path.split("?", 1); limit = 50
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                            if k == "limit": limit = min(int(v), 1000)
                    self._j(200, self._get_chat_history(limit))
                    self._log_remote_access(auth, p)

            # ===== 远程管理接口 =====
            elif p == "/api/remote/keys":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._list_api_keys()); self._log_remote_access(auth, p)
            elif p == "/api/remote/access-log":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._remote_access_log()); self._log_remote_access(auth, p)
            elif p == "/api/remote/crypto/status":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._crypto_status()); self._log_remote_access(auth, p)
            elif p == "/api/remote/crypto/self-test":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._crypto_self_test()); self._log_remote_access(auth, p)

            elif p == "/api/protocols/status":
                # 多协议网关状态
                if _proto_gateway:
                    self._j(200, _proto_gateway.get_status())
                else:
                    self._j(200, {"error": "Protocol gateway not initialized"})

            # 每日日志
            elif p == "/api/log/chart":
                auth = self._require_auth("read")
                if auth:
                    query = parse_qs(urlsplit(self.path).query)
                    days = max(1, min(30, int(query.get("days", ["7"])[0])))
                    keyword = unquote(query.get("type", ["日志统计"])[0])
                    self._j(200, self._get_log_chart(keyword, days))
                    self._log_remote_access(auth, p)
            elif p == "/api/log/daily":
                auth = self._require_auth("read")
                if auth:
                    _daily_log_update()
                    days = 7
                    qs = self.path.split("?", 1)
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            if kv.startswith("days="):
                                days = int(kv.split("=",1)[1])
                    conn = _db()
                    rows = conn.execute("SELECT * FROM daily_log ORDER BY log_date DESC LIMIT ?", (days,)).fetchall()
                    cols = [d[0] for d in conn.execute("SELECT * FROM daily_log LIMIT 0").description]
                    conn.close()
                    self._j(200, {"daily": [dict(zip(cols, r)) for r in rows]})
                    self._log_remote_access(auth, p)
            elif p == "/api/log/today":
                auth = self._require_auth("read")
                if auth:
                    _daily_log_update()  # 强制刷新
                    conn = _db()
                    today = _cst_today_str()
                    row = conn.execute("SELECT * FROM daily_log WHERE log_date=?", (today,)).fetchone()
                    cols = [d[0] for d in conn.execute("SELECT * FROM daily_log LIMIT 0").description]
                    # 附加实时统计
                    with _STATUS_LOCK:
                        online_devices = sum(1 for d in DEVICE_DEFS if _DEVICE_STATUS.get(d["id"], {}).get("online"))
                        online_sensors = sum(1 for s in SENSOR_DEFS if _SENSOR_STATUS.get(s["id"], {}).get("online"))
                    realtime = {
                        "online_devices": online_devices,
                        "total_devices": len(DEVICE_DEFS),
                        "online_sensors": online_sensors,
                        "total_sensors": len(SENSOR_DEFS),
                        "ws_clients": len(_proto_gateway.ws.clients) if _proto_gateway else 0,
                        "mqtt_clients": len(_proto_gateway.mqtt.clients) if _proto_gateway else 0,
                    }
                    conn.close()
                    self._j(200, {"today": dict(zip(cols, row)) if row else {"log_date": today}, "realtime": realtime})
                    self._log_remote_access(auth, p)

            # TTS 代理
            elif p == "/api/tts/config":
                self._j(200, _public_tts_config())
            elif p == "/api/voice/config":
                auth = self._require_auth("read")
                if auth:
                    self._j(200, _voice_config())
                    self._log_remote_access(auth, p)
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
                self._j(200, _public_ai_config())
            elif p == "/api/ai/offline/config":
                auth = self._require_auth("read")
                if auth:
                    self._j(200, {"success": True, **_offline_model_config()})
                    self._log_remote_access(auth, p)
            else:
                self._j(404, {"error": "nf"})
        except Exception as e:
            self._j(500, {"error": str(e)})

    # ===== POST 路由 =====
    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/mcp":
            try:
                self._handle_mcp_post()
            except Exception as exc:
                log(f"[MCP] HTTP处理失败: {exc}")
                self._mcp_json(500, {"error": "MCP internal error", "code": 500})
            return
        body = self._b()
        try:
            # ===== 认证接口 (无需认证) =====
            if p == "/api/auth/token":
                self._j(200, self._auth_token(body))
                return
            elif p == "/api/auth/refresh":
                auth = self._require_auth("read")
                if auth: self._j(200, self._auth_refresh(auth))
                return

            # ===== 加密通信接口 =====
            elif p == "/api/secure/call":
                self._j(200, self._secure_call(body))
                return

            # ===== 业务接口 (需认证) =====
            elif p == "/api/chat/send":
                auth = self._require_auth("write")
                if auth: self._j(200, self._chat(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/plan/confirm":
                auth = self._require_auth("write")
                if auth: self._j(200, self._confirm_assistant_plan(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/plan/cancel":
                auth = self._require_auth("write")
                if auth: self._j(200, self._cancel_assistant_plan(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/status/check":
                auth = self._require_auth("write")
                if auth:
                    reports = _run_proactive_cycle_now(manual=True)
                    self._j(200, {"success": True, "manual": True, "reports": reports,
                                  "message": "已完成一次实时状态检测，结果已写入助手和上下文"})
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/external/config":
                auth = self._require_auth("write")
                if auth: self._j(200, self._update_external_config(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/offline/config":
                auth = self._require_auth("write")
                if auth:
                    result = _set_offline_model_enabled(bool(body.get("enabled", False)))
                    self._j(200, result)
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/voice/input":
                auth = self._require_auth("write")
                if auth: self._j(200, self._voice_input(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/voice/config":
                auth = self._require_auth("write")
                if auth:
                    enabled = bool(body.get("enabled", False))
                    result = _set_voice_enabled(enabled, body.get("serialPort", body.get("serial_port")))
                    self._j(200 if result.get("success") else 400, result)
                    self._log_remote_access(auth, p, 200 if result.get("success") else 400)
                return
            elif p == "/api/door/control":
                auth = self._require_auth("write")
                if auth: self._j(200, self._door_control(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/security/door-password-verify":
                auth = self._require_auth("read")
                if auth: self._j(200, self._door_password_verify(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/user/profile":
                auth = self._require_auth("write")
                if auth: self._j(200, self._update_user(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/rag/search":
                auth = self._require_auth("read")
                if auth: self._j(200, {"results": _rag.search(body.get("query", ""), n=body.get("n_results", 5))})
                return

            # ===== AI 智能意图接口 (POST) =====
            elif p == "/api/ai/intent":
                auth = self._require_auth("write")
                if auth: self._j(200, self._parse_intent(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/execute":
                auth = self._require_auth("write")
                if auth: self._j(200, self._execute_intent_api(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/recommendation/accept":
                auth = self._require_auth("write")
                if auth: self._j(200, self._accept_recommendation(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/recommendation/dismiss":
                auth = self._require_auth("write")
                if auth: self._j(200, self._dismiss_recommendation(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/emotion":
                auth = self._require_auth("read")
                if auth: self._j(200, self._analyze_emotion(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/device/register":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._register_device(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/device/unregister":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._unregister_device(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/context/clear":
                auth = self._require_auth("write")
                if auth: self._j(200, self._clear_context()); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/linkage/config":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._update_linkage_config(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/guard/config":
                auth = self._require_auth("admin")
                if auth:
                    try:
                        self._j(200, self._update_guard_config(body))
                    except ValueError as exc:
                        self._j(400, {"success": False, "error": str(exc), "code": 400})
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/guard/feedback":
                auth = self._require_auth("write")
                if auth:
                    try:
                        self._j(200, self._submit_guard_feedback(body))
                    except (TypeError, ValueError) as exc:
                        self._j(400, {"success": False, "error": str(exc), "code": 400})
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/assistant/feedback":
                auth = self._require_auth("write")
                if auth:
                    try:
                        self._j(200, self._submit_assistant_feedback(body))
                    except (TypeError, ValueError) as exc:
                        self._j(400, {"success": False, "error": str(exc), "code": 400})
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/app/telemetry":
                auth = self._require_auth("write")
                if auth:
                    try:
                        self._j(200, self._record_app_telemetry(body))
                    except ValueError as exc:
                        self._j(400, {"success": False, "error": str(exc), "code": 400})
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/context/kv":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._set_kv(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/context/kv/sync":
                auth = self._require_auth("admin")
                if auth:
                    _sync_kv_from_code()
                    self._j(200, {"success": True, "message": "KV已从代码定义同步"})
                    self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/context/search":
                auth = self._require_auth("read")
                if auth: self._j(200, self._context_search(body.get("query", ""))); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/context/rebuild":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._context_rebuild()); self._log_remote_access(auth, p)
                return
            elif p == "/api/ai/radar/config":
                auth = self._require_auth("admin")
                if auth:
                    if not isinstance(body.get("enabled"), bool):
                        self._j(400, {"success": False, "error": "enabled 必须是布尔值", "code": 400})
                    else:
                        self._j(200, self._set_radar_enabled(body["enabled"]))
                    self._log_remote_access(auth, p)
                return

            # ===== 远程管理接口 =====
            elif p == "/api/remote/keys/create":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._create_api_key(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/remote/keys/revoke":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._revoke_api_key(body)); self._log_remote_access(auth, p)
                return
            elif p == "/api/remote/crypto/rotate-sm4":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._rotate_sm4_key()); self._log_remote_access(auth, p)
                return
            elif p == "/api/remote/crypto/register-pubkey":
                auth = self._require_auth("admin")
                if auth: self._j(200, self._register_remote_pubkey(body)); self._log_remote_access(auth, p)
                return

            # 自定义设备注册（设备页添加入口使用）
            if p == "/api/devices":
                auth = self._require_auth("write")
                if auth:
                    self._j(200, self._register_device(body)); self._log_remote_access(auth, p)
                return

            # 设备控制 (RESTful)
            m = re.match(r"^/api/devices/([\w_]+)/control$", p)
            if m:
                auth = self._require_auth("write")
                if auth: self._j(200, self._control_device(m.group(1), body)); self._log_remote_access(auth, p)
                return
            m = re.match(r"^/api/devices/([\w_]+)/toggle$", p)
            if m:
                auth = self._require_auth("write")
                if auth: self._j(200, self._toggle_device(m.group(1), body)); self._log_remote_access(auth, p)
                return

            # TTS/AI 代理
            if p == "/api/tts/speak":
                text = str(body.get("text", "")).strip()
                if not text:
                    self._j(400, {"ok": False, "error": "text is required"})
                else:
                    queued = _tts_speak(text, category=str(body.get("category", "default")))
                    self._j(200, {"ok": True, "played": queued, "queued": queued,
                                 "suppressed": not queued, "speechText": _voice_summary(text),
                                 "speechMode": "summary"})
            elif p in ("/api/tts/config", "/api/tts/test",
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

    # ═══════════════════════════════════════════════════════════════
    # 认证接口实现
    # ═══════════════════════════════════════════════════════════════

    def _auth_public_key(self):
        """返回设备 SM2 公钥 + SM4 密钥指纹 (供远程服务器注册)"""
        return {
            "device_id": "harmony_a9",
            "sm2_public_key": _SM2_KEYPAIR.public_key_hex,
            "sm4_key_fingerprint": sm3_hash(_SM4_KEY).hex()[:16],
            "supported_algorithms": ["SM3", "SM4-CBC", "SM2"],
            "envelope_version": 1,
        }

    def _auth_token(self, body):
        """签发 Token (需要 API Key 或管理员凭证)"""
        api_key = body.get("api_key", "")
        key_info = _verify_api_key(api_key, "read")
        if not key_info:
            _log_security_auth("auth.token_failed", api_key[:8], "API Key无效")
            return {"error": "API Key无效", "code": 403}

        # 根据权限决定 Token 有效期
        perms = key_info.get("permissions", [])
        if "admin" in perms:
            expiry = 86400  # 管理员 24 小时
        elif "write" in perms:
            expiry = 28800  # 写权限 8 小时
        else:
            expiry = 3600   # 只读 1 小时

        token = generate_token(key_info["key_id"], _TOKEN_SECRET, expiry)
        return {
            "token": token,
            "expires_in": expiry,
            "permissions": perms,
            "key_id": key_info["key_id"],
        }

    def _auth_refresh(self, auth_info):
        """刷新 Token"""
        uid = auth_info.get("uid", "")
        if uid == "local":
            return {"error": "本地访问无需刷新Token"}
        token = generate_token(uid, _TOKEN_SECRET, 3600)
        return {"token": token, "expires_in": 3600}

    # ═══════════════════════════════════════════════════════════════
    # 加密通信接口
    # ═══════════════════════════════════════════════════════════════

    def _secure_call(self, body):
        """
        加密远程调用入口

        请求体: SecureEnvelope 格式
        {
            "version": 1,
            "timestamp": ...,
            "nonce": "...",
            "sm4_iv": "...",
            "payload": "...",  (SM4加密后的业务数据)
            "signature": "...", (SM2签名)
            "signer_pubkey": "..." (调用方SM2公钥)
        }

        响应: 同样是 SecureEnvelope 格式
        """
        try:
            # 解封
            inner_data = _envelope.unseal(body, verify_signature=True, max_age_seconds=300, check_nonce=True)
        except ValueError as e:
            _log_security_auth("secure.unseal_failed", str(e)[:200], str(e))
            self._j(400, {"error": f"解封失败: {e}", "code": 400})
            return

        # 提取业务请求
        action = inner_data.get("action", "")
        params = inner_data.get("params", {})

        # 执行业务逻辑
        result = self._dispatch_secure_action(action, params)

        # 封装响应
        response_envelope = _envelope.seal(result)
        response_envelope["action"] = action
        return response_envelope

    def _dispatch_secure_action(self, action, params):
        """分发加密请求到业务逻辑"""
        # 设备控制
        if action == "device.toggle":
            return self._toggle_device(params.get("device_id", ""), params)
        elif action == "device.control":
            return self._control_device(params.get("device_id", ""), params)
        elif action == "device.list":
            return self._get_devices()
        elif action == "device.status":
            device_id = params.get("device_id", "")
            with _STATUS_LOCK:
                return _DEVICE_STATUS.get(device_id, {"online": False})
        # 传感器
        elif action == "sensor.list":
            return self._get_sensors()
        elif action == "sensor.history":
            return self._get_sensor_history()
        # 场景
        elif action == "scene.activate":
            return self._activate_scene(params)
        elif action == "scene.list":
            return self._list_scenes()
        # 门禁
        elif action == "door.control":
            return self._door_control(params)
        # 空调
        elif action == "ac.control":
            return self._ac_control(params)
        # 状态
        elif action == "status.all":
            return self._get_stats()
        elif action == "status.check":
            return self._check_all()
        # AI
        elif action == "chat.send":
            return self._chat(params)
        # 安全
        elif action == "security.events":
            return self._security_events()
        elif action == "security.stats":
            return self._security_stats()
        # AI 意图
        elif action == "ai.intent":
            return self._parse_intent(params)
        elif action == "ai.execute":
            return self._execute_intent_api(params)
        elif action == "ai.capabilities":
            return get_device_capabilities(DEVICE_DEFS)
        elif action == "ai.anomaly":
            return self._get_anomaly_events()
        elif action == "ai.recommendations":
            return self._get_recommendations()
        elif action == "ai.energy":
            return self._get_energy()
        elif action == "ai.energy.waste":
            return self._get_energy_waste()
        elif action == "ai.energy.report":
            return self._get_energy_report()
        elif action == "ai.linkage":
            return self._get_linkage_rules()
        elif action == "ai.linkage.config":
            return self._get_linkage_config()
        elif action == "ai.guard.status":
            return self._get_guard_status()
        elif action == "ai.guard.config":
            return self._get_guard_config()
        elif action == "ai.guard.incidents":
            return self._get_guard_incidents(int(params.get("limit", 50)), bool(params.get("pending", False)))
        elif action == "ai.guard.learning":
            return self._get_guard_learning(params.get("query", ""), int(params.get("limit", 20)))
        elif action == "ai.guard.feedback":
            return self._submit_guard_feedback(params)
        elif action == "ai.context.kv":
            return self._get_kv(params)
        elif action == "ai.context.kv.dump":
            return self._kv_dump()
        elif action == "ai.emotion":
            return self._analyze_emotion(params)
        elif action == "ai.context":
            return self._get_context_summary()
        elif action == "ai.device.register":
            return self._register_device(params)
        elif action == "ai.device.unregister":
            return self._unregister_device(params)
        else:
            return {"error": f"Unknown action: {action}", "code": 404}

    # ═══════════════════════════════════════════════════════════════
    # 业务逻辑实现 (与 v5 一致 + 新增)
    # ═══════════════════════════════════════════════════════════════

    def _get_devices(self):
        result = []
        with _STATUS_LOCK:
            for d in DEVICE_DEFS:
                if d["id"] == "voice_01":
                    voice = _voice_config()
                    result.append({
                        "id": d["id"], "name": d["name"], "type": d["type"],
                        "status": "online" if voice.get("running") else "offline",
                        "room": d["room"], "icon": d["icon"],
                        "isOn": bool(voice.get("enabled")),
                        "primaryValue": int(voice.get("frames", 0)),
                    })
                    continue
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
                    entry = {
                        "id": d["id"], "name": d["name"], "type": d["type"],
                        "status": "offline", "room": d["room"], "icon": d["icon"],
                        "isOn": False, "primaryValue": None,
                    }
                result.append(entry)
        existing_ids = {item["id"] for item in result}
        try:
            conn = _db()
            rows = conn.execute(
                "SELECT id,name,type,status,room,icon,primary_value,is_on,mode,battery,protocol "
                "FROM devices ORDER BY id"
            ).fetchall()
            conn.close()
            for row in rows:
                if row[0] in existing_ids:
                    continue
                result.append({
                    "id": row[0], "name": row[1], "type": row[2],
                    "status": row[3], "room": row[4], "icon": row[5],
                    "primaryValue": row[6], "isOn": bool(row[7]),
                    "mode": row[8], "battery": row[9], "protocol": row[10],
                    "custom": False,
                })
                existing_ids.add(row[0])
        except Exception:
            pass
        if _intent_engine:
            try:
                for template in _intent_engine.list_device_templates():
                    device_id = template.get("id")
                    if not device_id or device_id in existing_ids:
                        continue
                    result.append({
                        "id": device_id, "name": template.get("name", device_id),
                        "type": template.get("type", "custom"),
                        "room": template.get("room", ""), "status": "registered",
                        "isOn": False, "primaryValue": None, "custom": True,
                        "aliases": template.get("aliases", []),
                        "capabilities": template.get("capabilities", []),
                    })
                    existing_ids.add(device_id)
            except Exception:
                pass
        return _visible_devices(result)

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
                    entry = {
                        "id": s["id"], "name": s["name"], "type": s["type"],
                        "group": s["group"], "room": s["room"], "icon": s["icon"],
                        "current": None, "isAlert": False,
                    }
                if "thresholdMax" in s:
                    entry["thresholdMax"] = s["thresholdMax"]
                result.append(entry)
        existing_sensor_ids = {item["id"] for item in result}
        try:
            conn = _db()
            rows = conn.execute(
                "SELECT id,name,type,sensor_group,room,icon,current_value,unit,threshold_min,threshold_max,protocol,is_alert "
                "FROM sensors ORDER BY id"
            ).fetchall()
            conn.close()
            for row in rows:
                if row[0] in existing_sensor_ids:
                    continue
                entry = {
                    "id": row[0], "name": row[1], "type": row[2],
                    "group": row[3], "room": row[4], "icon": row[5],
                    "current": {"value": row[6], "unit": row[7]},
                    "protocol": row[10], "isAlert": bool(row[11]),
                    "source": "database",
                }
                if row[8] is not None:
                    entry["thresholdMin"] = row[8]
                if row[9] is not None:
                    entry["thresholdMax"] = row[9]
                result.append(entry)
                existing_sensor_ids.add(row[0])
        except Exception:
            pass
        return result

    def _get_alerts(self):
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

    def _get_operations(self, device_id=None, days=7, limit=200):
        conn = _db()
        days = int(days)
        time_filter = f"datetime('now','+8 hours','-{days} days')"
        if device_id:
            if days > 0:
                total = conn.execute(f"SELECT COUNT(*) FROM device_operations WHERE device_id=? AND created_at>={time_filter}", (device_id,)).fetchone()[0]
                rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE device_id=? AND created_at>={time_filter} ORDER BY created_at DESC LIMIT ?", (device_id, limit)).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) FROM device_operations WHERE device_id=?", (device_id,)).fetchone()[0]
                rows = conn.execute("SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE device_id=? ORDER BY id DESC LIMIT ?", (device_id, limit)).fetchall()
        else:
            if days > 0:
                total = conn.execute(f"SELECT COUNT(*) FROM device_operations WHERE created_at>={time_filter}").fetchone()[0]
                rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE created_at>={time_filter} ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) FROM device_operations").fetchone()[0]
                rows = conn.execute("SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return {"operations": [{"device_id": r[0], "action": r[1], "params": r[2], "result": r[3], "source": r[4], "scene_id": r[5], "timestamp": r[6]} for r in rows], "total": total, "limit": limit}

    def _get_log_chart(self, keyword="日志统计", days=7):
        """Return deterministic live charts consumed by the on-device data center."""
        days = max(1, min(30, int(days)))
        _daily_log_update()
        conn = _db()
        rows = conn.execute(
            "SELECT log_date,total_requests,total_chat,total_device_ops,total_security_events "
            "FROM daily_log ORDER BY log_date DESC LIMIT ?", (days,),
        ).fetchall()
        conn.close()
        rows = list(reversed(rows))
        dates = [row[0] for row in rows]
        with _STATUS_LOCK:
            online_devices = sum(1 for definition in DEVICE_DEFS if _DEVICE_STATUS.get(definition["id"], {}).get("online"))
            online_sensors = sum(1 for definition in SENSOR_DEFS if _SENSOR_STATUS.get(definition["id"], {}).get("online"))
        latest = rows[-1] if rows else (_cst_today_str(), 0, 0, 0, 0)
        return {
            "chart_type": "live_log_dashboard",
            "keyword": str(keyword)[:80],
            "kimi_used": False,
            "days": days,
            "charts": [
                {
                    "id": "daily_activity",
                    "title": f"最近{days}天日志趋势",
                    "type": "bar",
                    "xAxis": {"type": "category", "data": dates},
                    "series": [
                        {"name": "请求", "type": "bar", "data": [int(row[1] or 0) for row in rows]},
                        {"name": "对话", "type": "line", "data": [int(row[2] or 0) for row in rows]},
                        {"name": "设备操作", "type": "line", "data": [int(row[3] or 0) for row in rows]},
                        {"name": "安全事件", "type": "line", "data": [int(row[4] or 0) for row in rows]},
                    ],
                },
                {
                    "id": "today_realtime",
                    "title": "今日实时状态",
                    "type": "gauge",
                    "data": {
                        "date": latest[0],
                        "total_requests": int(latest[1] or 0),
                        "total_chat": int(latest[2] or 0),
                        "total_device_ops": int(latest[3] or 0),
                        "total_security_events": int(latest[4] or 0),
                        "online_devices": online_devices,
                        "total_devices": len(DEVICE_DEFS),
                        "online_sensors": online_sensors,
                        "total_sensors": len(SENSOR_DEFS),
                    },
                },
            ],
        }

    def _chat_chart_data(self, keyword="对话实时态势"):
        """Attach several non-empty live views to every assistant turn."""
        dashboard = self._get_log_chart(keyword, 7)
        hidden_for_surface = {"alarm_01", "camera_01", "nfc_01", "radar_01"}
        devices = [item for item in self._get_devices() if str(item.get("id", "")) not in hidden_for_surface]
        type_counts = {}
        online_count = 0
        on_count = 0
        for device in devices:
            kind = str(device.get("type", "设备"))
            type_counts[kind] = type_counts.get(kind, 0) + 1
            if str(device.get("status", "")).lower() in {"online", "active", "connected"}:
                online_count += 1
            if bool(device.get("isOn", False)):
                on_count += 1
        labels = list(type_counts.keys()) or ["暂无设备"]
        values = [int(type_counts[label]) for label in labels] or [0]
        total = max(1, len(devices))
        dashboard["chart_type"] = "chat_multi_dashboard"
        dashboard["charts"].append({
            "id": "device_mix", "title": "当前设备构成", "type": "pie",
            "xAxis": {"type": "category", "data": labels},
            "series": [{"name": "设备数", "type": "pie", "data": values}],
        })
        dashboard["charts"].append({
            "id": "home_pulse", "title": "当前家庭脉搏", "type": "radar",
            "radar": {"indicator": [
                {"name": "在线", "max": total}, {"name": "开启", "max": total},
                {"name": "服务", "max": max(1, int(dashboard.get("days", 7)))},
            ]},
            "series": [{"name": "实时", "type": "radar",
                        "data": [{"name": "当前", "value": [online_count, on_count, 1]}]}],
        })
        return dashboard

    def _get_chat_history(self, limit=50):
        """查询聊天历史，返回分页结果"""
        conn = _db()
        try:
            total = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
            rows = conn.execute(
                "SELECT id, user_id, role, content, intent_json, emotion, source, created_at "
                "FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            messages = []
            for r in rows:
                msg = {
                    "id": r[0],
                    "user_id": r[1],
                    "role": r[2],
                    "content": r[3],
                    "timestamp": r[7],
                }
                if r[4]: msg["intent"] = r[4]
                if r[5]: msg["emotion"] = r[5]
                if r[6]: msg["source"] = r[6]
                # 标记AI上游错误
                if r[2] == "assistant" and r[3] and "暂时不可用" in str(r[3]):
                    msg["error"] = True
                messages.append(msg)
            return {"messages": messages, "total": total, "limit": limit}
        except Exception as e:
            conn.close()
            return {"messages": [], "total": 0, "limit": limit, "error": str(e)}

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

    def _server_status(self):
        # 动态获取真实IP
        local_ip = "0.0.0.0"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass
        return {
            "host": local_ip, "port": PORT, "isOnline": True,
            "protocol": "wifi", "version": "v6",
            "hardware": _HW_OK,
            "crypto": {"sm3": True, "sm4": True, "sm2": True, "envelope_version": 1},
            "pollIntervalKitchen": _KITCHEN_POLL_INTERVAL,
            "pollIntervalOther": _OTHER_POLL_INTERVAL,
        }

    def _get_stats(self):
        stats = {"timestamp": datetime.now().isoformat(), "version": "v6"}
        with _STATUS_LOCK:
            total_devices = len(DEVICE_DEFS)
            online_devices = sum(1 for d in DEVICE_DEFS if _DEVICE_STATUS.get(d["id"], {}).get("online"))
            stats["device_online_rate"] = {"total": total_devices, "online": online_devices, "offline": total_devices - online_devices, "rate": round(online_devices / total_devices * 100, 1) if total_devices else 0}
            stats["area_connectivity"] = {}
            for area_id, area_info in AREA_DEFS.items():
                online = _AREA_ONLINE.get(area_id, False)
                stats["area_connectivity"][area_id] = {"name": area_info["name"], "ip": area_info["ip"], "port": area_info["port"], "online": online}
            temp_cached = _SENSOR_STATUS.get("temp_01", {})
            stats["living_temperature"] = {"value": temp_cached.get("raw_temp") if temp_cached.get("online") else None, "unit": "°C", "online": temp_cached.get("online", False)}
            humid_cached = _SENSOR_STATUS.get("humid_01", {})
            stats["living_humidity"] = {"value": humid_cached.get("raw_humidity") if humid_cached.get("online") else None, "unit": "%RH", "online": humid_cached.get("online", False)}
            smoke_cached = _SENSOR_STATUS.get("smoke_01", {})
            stats["kitchen_smoke"] = {"smoke_alarm": smoke_cached.get("is_alert") if smoke_cached.get("online") else None, "online": smoke_cached.get("online", False)}
            heat_cached = _SENSOR_STATUS.get("heat_01", {})
            stats["kitchen_thermal"] = {"thermal_mv": heat_cached.get("thermal_mv") if heat_cached.get("online") else None, "online": heat_cached.get("online", False)}
            stats["alarm_linkage"] = {"last_kitchen_alarm": _last_kitchen_alarm, "udp_listening": _UDP_LISTENING}
        linkage_view = self._get_linkage_config().get("rules", {})
        stats["linkage_config"] = {
            k: bool(v.get("effective_enabled", v.get("enabled", False)))
            for k, v in linkage_view.items()
        }
        return stats

    def _check_all(self):
        check_result = {"timestamp": datetime.now().isoformat(), "areas": [], "online_count": 0, "offline_count": 0}
        with _STATUS_LOCK:
            for area_id, area_info in AREA_DEFS.items():
                online = _AREA_ONLINE.get(area_id, False)
                check_result["areas"].append({"id": area_id, "name": area_info["name"], "ip": area_info["ip"], "online": online})
                if online:
                    check_result["online_count"] += 1
                else:
                    check_result["offline_count"] += 1
        return check_result

    def _hardware_check(self):
        return {"hardware_available": _HW_OK, "auth_status": get_auth_status(), "devices": len(DEVICE_DEFS), "sensors": len(SENSOR_DEFS)}

    def _toggle_device(self, device_id, body):
        is_on = body.get("isOn", body.get("is_on", True))
        if device_id == "voice_01":
            result = _set_voice_enabled(bool(is_on), body.get("serialPort", body.get("serial_port")))
            try:
                conn = _db()
                conn.execute("INSERT INTO device_operations(device_id,action,params_json,result,source) VALUES(?,?,?,?,?)",
                             (device_id, "toggle", json.dumps({"isOn": bool(is_on)}, ensure_ascii=False),
                              "ok" if result.get("success") else "failed", "api"))
                conn.commit(); conn.close()
            except Exception:
                pass
            message = "语音控制已开启" if result.get("success") and is_on else ("语音控制已关闭" if result.get("success") else result.get("error", "语音控制未改变"))
            _tts_speak(message, category="voice")
            return {"success": bool(result.get("success")), "enabled": bool(result.get("config", {}).get("enabled", False)),
                    "message": message, "config": result.get("config", _voice_config()), "error": result.get("error", "")}
        door_password = body.get("doorPassword", body.get("door_password"))
        r = hw_toggle(device_id, is_on, door_password=door_password)
        # 记录操作
        try:
            conn = _db()
            conn.execute("INSERT INTO device_operations(device_id,action,params_json,result,source) VALUES(?,?,?,?,?)",
                         (device_id, "toggle", json.dumps({"isOn": is_on}, ensure_ascii=False), "ok" if r["success"] else "failed", "api"))
            conn.commit(); conn.close()
        except Exception:
            pass
        # 多协议广播
        if _proto_gateway and r.get("success"):
            _proto_gateway.broadcast_event("device_toggled", {"device_id": device_id, "isOn": is_on, "result": r})
        _record_context_event(
            "device_operation",
            f"Device {device_id} toggle {'succeeded' if r.get('success') else 'failed'}",
            details={"action": "toggle", "isOn": bool(is_on), "success": bool(r.get("success"))},
            entity_type="device", entity_id=device_id, source="api",
            severity="info" if r.get("success") else "warning",
        )
        action_text = "开启" if bool(is_on) else "关闭"
        device_name = _DEVICE_NAMES.get(device_id, device_id)
        if r.get("success"):
            commanded_value = 24 if device_id == "ac_01" else (100 if bool(is_on) else 0)
            _apply_commanded_device_state(device_id, bool(is_on), commanded_value)
        _publish_device_operation(device_id, action_text, bool(r.get("success")))
        _tts_speak(f"{device_name}{action_text}{'成功' if r.get('success') else '失败'}",
                   category=f"device:{device_id}")
        # Manual device operations are context-only; they are logged and surfaced in the next analysis.
        return r

    def _control_device(self, device_id, body):
        action = body.get("action", "set_brightness")
        if isinstance(body.get("params"), dict):
            params = dict(body["params"])
        else:
            params = {
                key: value for key, value in body.items()
                if key not in {"action", "password", "doorPassword", "door_password"}
            }
        door_password = body.get("doorPassword", body.get("door_password"))
        r = hw_control(device_id, action, params, door_password=door_password)
        try:
            conn = _db()
            conn.execute("INSERT INTO device_operations(device_id,action,params_json,result,source) VALUES(?,?,?,?,?)",
                         (device_id, action, json.dumps(params, ensure_ascii=False), "ok" if r["success"] else "failed", "api"))
            conn.commit(); conn.close()
        except Exception:
            pass
        # 多协议广播
        if _proto_gateway and r.get("success"):
            _proto_gateway.broadcast_event("device_controlled", {"device_id": device_id, "action": action, "result": r})
        _record_context_event(
            "device_operation",
            f"Device {device_id} action {action} {'succeeded' if r.get('success') else 'failed'}",
            details={"action": action, "params": params, "success": bool(r.get("success"))},
            entity_type="device", entity_id=device_id, source="api",
            severity="info" if r.get("success") else "warning",
        )
        action_names = {
            "set_brightness": "调整亮度", "brightness": "调整亮度", "set_temp": "设置温度",
            "set_temperature": "设置温度", "preset": "切换模式", "cool": "开启制冷",
            "dry": "开启除湿", "fan": "开启送风", "set_speed": "调整风速",
            "set_position": "调整位置", "stop": "停止",
        }
        action_text = action_names.get(str(action), str(action))
        device_name = _DEVICE_NAMES.get(device_id, device_id)
        if r.get("success"):
            commanded_value = params.get("value")
            commanded_on = None
            if action in {"set_brightness", "brightness", "set_speed", "set_position"} and commanded_value is not None:
                try:
                    commanded_on = float(commanded_value) > 0
                except (TypeError, ValueError):
                    commanded_on = None
            elif device_id == "ac_01" and action in {"preset", "cool", "dry", "fan", "set_mode", "set_fan"}:
                commanded_on = True
            if commanded_on is not None:
                _apply_commanded_device_state(device_id, commanded_on, commanded_value)
        _publish_device_operation(device_id, action_text, bool(r.get("success")))
        _tts_speak(f"{device_name}{action_text}{'成功' if r.get('success') else '失败'}",
                   category=f"device:{device_id}")
        # Manual device operations are context-only; they are logged and surfaced in the next analysis.
        return r

    def _chat(self, body):
        msgs = body.get("messages", [])
        if not msgs:
            user_text = body.get("message", body.get("content", ""))
            if user_text:
                msgs = [{"role": "user", "content": user_text}]
        if not msgs:
            return {"reply": "请输入消息", "role": "assistant"}

        plan_scope = _plan_scope(body)
        plan_nonce = str(body.get("planNonce", "") or "")
        pending_plan_nonce = ""
        pending_plan_digest = ""

        # 安全护栏
        last_text = extract_text_content(msgs[-1].get("content", ""))
        shield_result = _shield.check(last_text)
        if shield_result.blocked:
            _log_security(shield_result, last_text, "chat")
            return _security_block_reply(shield_result)

        is_plan_cancellation = bool(re.search(r"^(取消计划|取消执行|不执行|暂不执行)$", last_text.strip()))
        if is_plan_cancellation:
            pending_entry = _get_pending_plan(plan_scope, plan_nonce)
            if pending_entry:
                _clear_pending_plan(plan_scope)
                _record_context_event(
                    "plan_decision", "用户取消了待执行计划",
                    details={"decision": "cancelled", "planNonce": plan_nonce,
                             "plan": pending_entry.get("payload", {})},
                    source="chat", severity="info",
                )
                return {
                    "reply": "计划已取消，没有执行任何设备操作。",
                    "role": "assistant",
                    "source": "cancelled_plan",
                    "voiceSequence": [_vs_entry("计划已取消")],
                    "chartData": self._chat_chart_data(last_text),
                }
            return {
                "reply": "当前没有可取消的待执行计划。",
                "role": "assistant",
                "source": "cancelled_plan",
                "chartData": self._chat_chart_data(last_text),
            }

        automatic_context = build_turn_context(
            _context_engine,
            last_text,
            messages=msgs,
            body=body,
            live_state=_context_live_state(),
        )
        if _context_engine is not None:
            _record_context_event(
                "ai_context_match",
                "AI turn context matched",
                details={
                    "queryHash": hashlib.sha256(last_text.encode("utf-8")).hexdigest(),
                    "queryLength": len(last_text),
                    "contextChars": len(automatic_context),
                    "openingGreetingSkipped": not bool(automatic_context),
                },
                source="chat",
            )

        # ===== 意图引擎三层解析 =====
        if _intent_engine:
            # 意图执行器
            def _exec_intent(intent):
                return self._execute_intent(intent)

            is_confirmation = bool(re.search(r"^(确认执行|执行|可以执行|开始执行|同意)$", last_text.strip()))
            pending_entry = _get_pending_plan(plan_scope, plan_nonce)
            pending_plan = dict(pending_entry.get("payload") or {}) if pending_entry else None
            if is_confirmation and pending_plan:
                if pending_plan.get("kind") == "ai_commands":
                    results = []
                    for command in _safe_plan_commands(pending_plan.get("commands", [])):
                        result_item = self._execute_ai_command(command)
                        if result_item is not None:
                            results.append(result_item)
                    execution = {"success": all(bool(item) for item in results), "results": results}
                else:
                    execution = self._execute_intent(pending_plan)
                result = {
                    "source": "confirmed_plan", "intent": pending_plan,
                    "executed": bool(execution and execution.get("success", True)),
                    "reply": f"已按确认计划执行。结果：{json.dumps(execution, ensure_ascii=False)[:600]}",
                }
                _record_context_event(
                    "plan_decision", "用户确认并执行了待执行计划",
                    details={"decision": "confirmed", "planNonce": plan_nonce,
                             "plan": pending_plan, "execution": execution},
                    source="chat", severity="info",
                )
                _clear_pending_plan(plan_scope)
            else:
                direct_intent = _direct_device_intent(last_text) if is_explicit_execution_request(last_text) else None
                if direct_intent is not None:
                    direct_execution = _exec_intent(direct_intent) if is_explicit_execution_request(last_text) else None
                    result = {
                        "source": "fast", "intent": direct_intent,
                        "executed": bool(direct_execution and direct_execution.get("success", True)),
                        "result": direct_execution,
                        "reply": f"已{'开启' if direct_intent.get('isOn') else '关闭'}{_DEVICE_NAMES.get(direct_intent.get('device_id'), direct_intent.get('device_id'))}",
                        "voice_text": f"{_DEVICE_NAMES.get(direct_intent.get('device_id'), direct_intent.get('device_id'))}{'已开启' if direct_intent.get('isOn') else '已关闭'}",
                    }
                else:
                    result = _intent_engine.parse(
                        last_text, execute=is_explicit_execution_request(last_text), executor=_exec_intent
                    )

            if result["source"] in ("fast", "fuzzy", "confirmed_plan") and result.get("reply"):
                # 快速匹配或模糊推理命中
                intent = result.get("intent") or {}
                mutating_intent = str(intent.get("type", "")).lower() in {"scene", "device_toggle", "device_control"}
                needs_plan = bool(_plan_confirmation_enabled() and mutating_intent and not is_explicit_execution_request(last_text))
                pending_plan_nonce = ""
                pending_plan_digest = ""
                if needs_plan:
                    pending_entry = _put_pending_plan(plan_scope, dict(intent))
                    pending_plan_nonce = str(pending_entry.get("planNonce", ""))
                    pending_plan_digest = str(pending_entry.get("planDigest", ""))
                    reply_text = _format_intent_plan(intent)
                    result["executed"] = False
                else:
                    reply_text = result["reply"]
                voice_text = result.get("voice_text", reply_text)

                # 记录对话（含意图详情）
                try:
                    conn = _db()
                    intent_j = json.dumps(result.get("intent"), ensure_ascii=False)[:1000] if result.get("intent") else None
                    emotion_j = json.dumps(result.get("emotion"), ensure_ascii=False)[:500] if result.get("emotion") else None
                    conn.execute("INSERT INTO chat_history(user_id,role,content,intent_json,emotion,source) VALUES(?,?,?,?,?,?)",
                                 ("u001", "user", last_text[:500], None, None, result["source"]))
                    conn.execute("INSERT INTO chat_history(user_id,role,content,intent_json,emotion,source) VALUES(?,?,?,?,?,?)",
                                 ("u001", "assistant", reply_text[:500], intent_j, emotion_j, result["source"]))
                    conn.commit(); conn.close()
                except Exception:
                    pass

                response = {
                    "reply": reply_text,
                    "role": "assistant",
                    "intent": result.get("intent"),
                    "executed": result.get("executed", False),
                    "source": result["source"],
                    "voiceSequence": [_vs_entry(voice_text)],
                    "chartData": self._chat_chart_data(last_text),
                }
                # 附加情感和指代消解信息
                if result.get("emotion"):
                    response["emotion"] = result["emotion"]
                if result.get("context_resolved"):
                    response["context_resolved"] = result["context_resolved"]
                if pending_plan_nonce:
                    response["planNonce"] = pending_plan_nonce
                    response["planDigest"] = pending_plan_digest
                    _record_context_event(
                        "plan_decision", "系统生成了待确认设备计划",
                        details={"decision": "proposed", "planNonce": pending_plan_nonce,
                                 "plan": intent},
                        source="chat", severity="info",
                    )
                # 广播AI对话事件
                if _proto_gateway:
                    _proto_gateway.broadcast_event("chat_message", {"user": last_text[:200], "reply": reply_text[:200], "source": result["source"], "intent": result.get("intent")})
                return response

        # AI 大模型兜底
        # 获取对话上下文摘要，增强AI prompt
        context_summary = ""
        if _intent_engine:
            context_summary = _intent_engine.get_context_summary()
        context_summary = merge_context_summaries(context_summary, automatic_context)

        safe_msgs = _context_engine.redact_sensitive(msgs) if _context_engine else msgs
        reply = chat(safe_msgs, context_summary=context_summary)
        reply = _normalize_ambiguous_ai_reply(last_text, reply)

        # 解析 AI 回复中的控制指令
        commands = parse_ai_commands(reply)
        exec_results = []
        pending_plan_nonce = ""
        pending_plan_digest = ""
        if commands:
            safe_commands = _safe_plan_commands(commands)
            if is_explicit_execution_request(last_text):
                for cmd in safe_commands:
                    try:
                        r = self._execute_ai_command(cmd)
                        if r:
                            exec_results.append(r)
                    except Exception as e:
                        log(f"[INTENT] AI指令执行失败: {e}")
            elif safe_commands:
                pending_entry = _put_pending_plan(
                    plan_scope, {"kind": "ai_commands", "commands": safe_commands}
                )
                pending_plan_nonce = str(pending_entry.get("planNonce", ""))
                pending_plan_digest = str(pending_entry.get("planDigest", ""))
                reply = _format_command_plan(safe_commands)
                commands = []
                _record_context_event(
                    "plan_decision", "系统生成了待确认 AI 操作计划",
                    details={"decision": "proposed", "planNonce": pending_plan_nonce,
                             "plan": {"kind": "ai_commands", "commands": safe_commands}},
                    source="chat", severity="info",
                )
            else:
                reply = strip_ai_commands(reply).strip()
                reply = (reply + "\n配置变更没有执行，请在设置页单独确认。").strip()
                commands = []

        # 移除指令标记，只保留自然语言
        clean_reply = strip_ai_commands(reply)

        # 语音播报
        if clean_reply:
            _tts_speak(clean_reply)

        # 记录对话（含AI指令详情）
        try:
            conn = _db()
            commands_j = json.dumps(exec_results[:5], ensure_ascii=False)[:1000] if exec_results else None
            conn.execute("INSERT INTO chat_history(user_id,role,content,intent_json,source) VALUES(?,?,?,?,?)",
                         ("u001", "user", last_text[:500], None, "ai"))
            conn.execute("INSERT INTO chat_history(user_id,role,content,intent_json,source) VALUES(?,?,?,?,?)",
                         ("u001", "assistant", clean_reply[:500], commands_j, "ai"))
            conn.commit(); conn.close()
        except Exception:
            pass

        # 记录到习惯学习器 + 对话记忆
        if _intent_engine:
            for cmd in commands:
                if cmd["type"] == "scene":
                    _intent_engine.record_habit("scene", cmd.get("scene_id", ""))
                elif cmd["type"] == "device":
                    _intent_engine.record_habit("device_control", cmd.get("device_id", ""), cmd.get("params"))
            # 记录AI回复到对话记忆
            _intent_engine.add_assistant_reply(clean_reply or reply, None)

        response = {
            "reply": clean_reply or reply,
            "role": "assistant",
            "source": "ai",
            "voiceSequence": [_vs_entry(clean_reply if clean_reply else reply)],
            "chartData": self._chat_chart_data(last_text),
        }
        if exec_results:
            response["executed_commands"] = exec_results
        if pending_plan_nonce:
            response["planNonce"] = pending_plan_nonce
            response["planDigest"] = pending_plan_digest
        # 广播AI对话事件
        if _proto_gateway:
            _proto_gateway.broadcast_event("chat_message", {"user": last_text[:200], "reply": (clean_reply or reply)[:200], "source": "ai", "commands": len(commands)})
        return response

    def _execute_intent(self, intent: dict) -> dict:
        """执行意图引擎解析出的意图"""
        itype = intent.get("type", "")

        if itype == "scene":
            scene_id = intent.get("scene_id", "")
            return self._activate_scene({"scene_id": scene_id})

        elif itype == "device_toggle":
            device_id = intent.get("device_id", "")
            is_on = intent.get("isOn", True)
            return self._toggle_device(device_id, {"isOn": is_on})

        elif itype == "device_control":
            device_id = intent.get("device_id", "")
            action = intent.get("action", "set_brightness")
            params = intent.get("params", {})
            return self._control_device(device_id, {"action": action, "params": params})

        elif itype == "door":
            door_action = intent.get("door_action", "query")
            return self._door_control({"action": door_action})

        elif itype == "query":
            query_type = intent.get("query_type", "all")
            if query_type == "temperature":
                with _STATUS_LOCK:
                    temp = _SENSOR_STATUS.get("temp_01", {})
                    return {"value": temp.get("raw_temp"), "unit": "°C", "online": temp.get("online", False)}
            elif query_type == "humidity":
                with _STATUS_LOCK:
                    humid = _SENSOR_STATUS.get("humid_01", {})
                    return {"value": humid.get("raw_humidity"), "unit": "%RH", "online": humid.get("online", False)}
            elif query_type == "safety":
                return self._get_alerts()
            elif query_type == "kitchen":
                return hw_kitchen_status()
            elif query_type == "door":
                return hw_living_status("door")
            elif query_type == "energy":
                return self._get_energy()
            elif query_type == "energy_waste":
                return self._get_energy_waste()
            else:
                return self._get_stats()

        return {"error": f"未知意图类型: {itype}"}

    def _execute_ai_command(self, cmd: dict) -> dict | None:
        """执行 AI 回复中解析出的控制指令"""
        ctype = cmd.get("type", "")
        if ctype == "device":
            dev_id = cmd.get("device_id", "")
            action = cmd.get("action", "")
            params = cmd.get("params", {})
            if action in ("on", "off"):
                return self._toggle_device(dev_id, {"isOn": action == "on"})
            else:
                return self._control_device(dev_id, {"action": action, "params": params})
        elif ctype == "scene":
            return self._activate_scene({"scene_id": cmd.get("scene_id", "")})
        elif ctype == "query":
            return self._execute_intent({"type": "query", "query_type": cmd.get("query_type", "all")})
        elif ctype == "call":
            return self._internal_api_call(cmd.get("api_path", ""), cmd.get("method", "GET"), cmd.get("params", {}))
        return None

    def _internal_api_call(self, path: str, method: str, params: dict) -> dict:
        """AI自调用: 不走HTTP，直接调用内部方法"""
        API_MAP = {
            "/api/ai/linkage/config": {
                "GET": self._get_linkage_config,
                "POST": self._update_linkage_config,
            },
            "/api/ai/linkage/rules": {"GET": self._get_linkage_rules},
            "/api/ai/linkage/log": {"GET": self._get_linkage_log},
            "/api/ai/guard/status": {"GET": self._get_guard_status},
            "/api/ai/guard/config": {"GET": self._get_guard_config, "POST": self._update_guard_config},
            "/api/ai/guard/incidents": {"GET": self._get_guard_incidents},
            "/api/ai/guard/learning": {"GET": self._get_guard_learning},
            "/api/ai/guard/feedback": {"POST": self._submit_guard_feedback},
            "/api/ai/assistant/feed": {"GET": self._get_assistant_feed},
            "/api/ai/external/feed": {"GET": self._get_external_feed},
            "/api/ai/external/config": {"GET": self._get_external_config, "POST": self._update_external_config},
            "/api/ai/plan/confirm": {"POST": self._confirm_assistant_plan},
            "/api/ai/plan/cancel": {"POST": self._cancel_assistant_plan},
            "/api/ai/assistant/feedback": {"POST": self._submit_assistant_feedback},
            "/api/devices": {"GET": self._list_devices},
            "/api/sensors": {"GET": self._list_sensors},
            "/api/hardware/status": {"GET": self._hardware_status},
            "/api/ai/context/kv": {"GET": self._get_kv, "POST": self._set_kv, "DELETE": self._del_kv},
            "/api/ai/context/kv/dump": {"GET": self._kv_dump},
            "/api/ai/context/kv/sync": {"POST": lambda p={}: _sync_kv_from_code() or {"success": True, "message": "KV已同步"}},
        }
        handlers = API_MAP.get(path, {})
        handler = handlers.get(method)
        if not handler:
            return {"success": False, "error": f"不支持 {method} {path}", "available": list(API_MAP.keys())}
        try:
            if method == "GET":
                return handler()
            else:
                return handler(params)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _voice_input(self, body):
        # The serial voice bridge sends already-recognized text through the
        # central controller.  Accept the common transcript aliases here so
        # clients do not silently lose a valid recognition result.
        text = body.get("text", body.get("transcript", body.get("message", body.get("voice_text", ""))))
        if not text:
            if body.get("audio_base64"):
                return {"success": False, "error": "当前网关不提供音频转写；请让中控语音桥先完成识别后提交 text", "role": "assistant"}
            return {"success": False, "reply": "未识别到语音内容", "role": "assistant"}
        return self._chat({"message": text})

    def _door_control(self, body):
        action = body.get("action", "query")
        password = body.get("password", body.get("doorPassword"))
        if action == "query":
            return hw_living_status("door")
        if action not in ("open", "close"):
            return {"error": "门禁 action 仅支持 query/open/close", "code": 400}
        if action in ("open", "close") and not password:
            return {"error": "门禁操作需要密码", "code": 403}
        r = hw_toggle("door_01", action == "open", door_password=password)
        _record_context_event(
            "door_operation",
            f"Door {action} {'succeeded' if r.get('success') else 'failed'}",
            details={"action": action, "passwordProvided": True, "success": bool(r.get("success"))},
            entity_type="device",
            entity_id="door_01",
            source="api",
            severity="info" if r.get("success") else "warning",
        )
        return r

    def _door_password_verify(self, body):
        password = body.get("password", "")
        verified, err = verify_door_password_api(password)
        return {"verified": verified, "error": err}

    def _update_user(self, body):
        conn = _db()
        if body.get("nickname"): conn.execute("UPDATE users SET nickname=? WHERE id='u001'", (body["nickname"],))
        if body.get("homeName"): conn.execute("UPDATE users SET home_name=? WHERE id='u001'", (body["homeName"],))
        if body.get("memberCount"): conn.execute("UPDATE users SET member_count=? WHERE id='u001'", (body["memberCount"],))
        r = conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        conn.commit(); conn.close()
        return {"id": r[0], "nickname": r[1], "homeName": r[2], "memberCount": r[3]}

    def _activate_scene(self, body):
        scene_id = body.get("scene_id", body.get("sceneId", ""))
        scene_name = body.get("name", "")
        if scene_name and not scene_id:
            from scenes.scene_config import get_scene_id_by_name
            scene_id = get_scene_id_by_name(scene_name)
        if not scene_id:
            return {"error": "需要 scene_id 或 name"}
        from scenes.scene_config import SCENE_ACTIONS, SCENE_META
        actions = SCENE_ACTIONS.get(scene_id, [])
        if not actions:
            return {"error": f"场景 {scene_id} 不存在"}
        blocked_door_actions = [action for action in actions if action[0] == "door_01"]
        actions = [action for action in actions if action[0] != "door_01"]
        results = hw_scene_execute(actions)
        # 更新数据库
        try:
            conn = _db()
            conn.execute("UPDATE scenes SET is_active=0")
            conn.execute("UPDATE scenes SET is_active=1, updated_at=datetime('now','+8 hours') WHERE id=?", (scene_id,))
            for dev_id, is_on, pv in actions:
                conn.execute("INSERT INTO device_operations(device_id,action,params_json,result,source,scene_id) VALUES(?,?,?,?,?,?)",
                             (dev_id, "scene_toggle", json.dumps({"isOn": bool(is_on), "primaryValue": pv}), "ok", "scene", scene_id))
            conn.commit(); conn.close()
        except Exception:
            pass
        meta = SCENE_META.get(scene_id, {})
        # Manual scene operations are context-only; the next summary may recommend adjustments.
        # 广播场景激活事件
        if _proto_gateway:
            _proto_gateway.broadcast_event("scene_activated", {"scene_id": scene_id, "name": meta.get("name", ""), "results_count": len(results)})
        _record_context_event(
            "scene_operation", f"Scene {scene_id} activated",
            details={"sceneId": scene_id, "resultCount": len(results), "doorActionsBlocked": len(blocked_door_actions)},
            entity_type="scene", entity_id=scene_id, source="api",
        )
        return {"success": True, "scene_id": scene_id, "name": meta.get("name", ""), "results": results, "door_actions_blocked": len(blocked_door_actions)}

    def _list_scenes(self):
        from scenes.scene_config import SCENE_META, SCENE_ACTIONS
        scenes = []
        for sid, meta in SCENE_META.items():
            actions = SCENE_ACTIONS.get(sid, [])
            scenes.append({
                "id": sid, "name": meta["name"], "icon": meta["icon"],
                "color": meta["color"], "description": meta["desc"],
                "device_count": len(actions),
            })
        return scenes

    def _ac_control(self, body):
        action = body.get("action", "query")
        if action == "on":
            r = hw_toggle("ac_01", True)
        elif action == "off":
            r = hw_toggle("ac_01", False)
        elif action in ("set_temp", "set_mode", "set_fan", "set_swing"):
            r = hw_control("ac_01", action, body)
        else:
            r = hw_living_status("ac")
        return r

    def _security_events(self, limit=100):
        conn = _db()
        rows = conn.execute("SELECT id,rule_id,severity,category,input_text,matched_text,reason,source,blocked,created_at FROM security_events ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
        conn.close()
        return [{"id": r[0], "rule_id": r[1], "severity": r[2], "category": r[3], "input_text": (r[4] or "")[:100], "matched_text": r[5], "reason": r[6], "source": r[7], "blocked": bool(r[8]), "timestamp": r[9]} for r in rows]

    def _security_stats(self):
        conn = _db()
        total = int(conn.execute("SELECT COUNT(*) FROM security_events").fetchone()[0])
        today = int(conn.execute(
            "SELECT COUNT(*) FROM security_events WHERE date(created_at,'+8 hours')=date('now','+8 hours')"
        ).fetchone()[0])
        rows = conn.execute(
            "SELECT lower(COALESCE(severity,'Low')), COUNT(*) FROM security_events GROUP BY severity"
        ).fetchall()
        conn.close()
        counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for severity, count in rows:
            key = str(severity or "low").capitalize()
            counts[key if key in counts else "Low"] += int(count or 0)
        return {"today": today, "total": total, "bySeverity": counts, "by_severity": counts}

    def _auth_status(self):
        return get_auth_status()

    # ═══════════════════════════════════════════════════════════════
    # AI 智能意图接口实现
    # ═══════════════════════════════════════════════════════════════

    def _parse_intent(self, body):
        """解析意图(不执行)"""
        text = body.get("message", body.get("text", ""))
        if not text:
            return {"error": "需要 message 参数"}
        if _intent_engine:
            result = _intent_engine.parse(text, execute=False)
            return result
        return {"error": "意图引擎未初始化"}

    def _execute_intent_api(self, body):
        """解析+执行意图"""
        text = body.get("message", body.get("text", ""))
        if not text:
            return {"error": "需要 message 参数"}
        if _intent_engine:
            def _exec(intent):
                return self._execute_intent(intent)
            result = _intent_engine.parse(text, execute=True, executor=_exec)
            return result
        return {"error": "意图引擎未初始化"}

    def _get_anomaly_events(self):
        """获取异常事件列表"""
        if _intent_engine:
            return _intent_engine.get_anomaly_events()
        return []

    def _get_recommendations(self):
        """获取推荐列表"""
        if _intent_engine:
            return _intent_engine.get_recommendations()
        return []

    def _get_habit_stats(self):
        """获取习惯学习统计"""
        if _intent_engine:
            return _intent_engine.get_habit_stats()
        return {}

    def _accept_recommendation(self, body):
        """接受推荐"""
        rec_id = body.get("id", body.get("rec_id", 0))
        if _intent_engine:
            ok = _intent_engine.accept_recommendation(int(rec_id))
            return {"success": ok, "id": rec_id}
        return {"success": False}

    def _dismiss_recommendation(self, body):
        """忽略推荐"""
        rec_id = body.get("id", body.get("rec_id", 0))
        if _intent_engine:
            ok = _intent_engine.dismiss_recommendation(int(rec_id))
            return {"success": ok, "id": rec_id}
        return {"success": False}

    # ===== 新增: 节能顾问接口 =====
    def _get_energy(self):
        """获取当前能耗"""
        if _intent_engine:
            return _intent_engine.get_energy_consumption()
        return {}

    def _get_energy_waste(self):
        """获取浪费分析"""
        if _intent_engine:
            return _intent_engine.get_energy_waste()
        return []

    def _get_energy_report(self):
        """获取每日能耗报告"""
        if _intent_engine:
            return _intent_engine.get_energy_report()
        return {}

    # ===== 新增: 联动引擎接口 =====
    def _get_linkage_rules(self):
        """获取联动规则"""
        if _intent_engine:
            return _intent_engine.get_linkage_rules()
        return []

    def _get_linkage_log(self):
        """获取联动执行日志"""
        if _intent_engine:
            return _intent_engine.get_linkage_log()
        return []

    # ===== KV上下文引擎接口 =====
    def _get_kv(self, params=None):
        """查询KV"""
        try:
            conn = _db()
            if params and isinstance(params, dict):
                ns = params.get("namespace", "")
                key = params.get("key", "")
                if ns and key:
                    row = conn.execute("SELECT namespace,key,value,priority,auto_sync,updated_at FROM ai_context_kv WHERE namespace=? AND key=?", (ns, key)).fetchone()
                    conn.close()
                    if row:
                        return {"namespace": row[0], "key": row[1], "value": json.loads(row[2]), "priority": row[3], "auto_sync": row[4], "updated_at": row[5]}
                    return {"error": "not found"}
                elif ns:
                    rows = conn.execute("SELECT key,value,priority,updated_at FROM ai_context_kv WHERE namespace=? ORDER BY key", (ns,)).fetchall()
                    conn.close()
                    return {"namespace": ns, "items": [{"key": r[0], "value": json.loads(r[1]), "priority": r[2], "updated_at": r[3]} for r in rows]}
            # 无参数返回全部namespace统计
            rows = conn.execute("SELECT namespace, COUNT(*) as cnt FROM ai_context_kv GROUP BY namespace ORDER BY namespace").fetchall()
            conn.close()
            return {"namespaces": [{"name": r[0], "count": r[1]} for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    def _set_kv(self, body):
        """写入/更新KV"""
        ns = body.get("namespace", "")
        key = body.get("key", "")
        value = body.get("value", "")
        priority = body.get("priority", 0)
        if not ns or not key:
            return {"success": False, "error": "需要 namespace 和 key"}
        try:
            val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            conn = _db()
            conn.execute("INSERT OR REPLACE INTO ai_context_kv(namespace,key,value,priority,auto_sync,updated_at) VALUES(?,?,?,?,'custom',datetime('now','+8 hours'))",
                         (ns, key, val_str, priority))
            conn.commit()
            conn.close()
            log(f"[KV] 写入 {ns}.{key} priority={priority}")
            return {"success": True, "namespace": ns, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _del_kv(self, body):
        """删除KV"""
        ns = body.get("namespace", "")
        key = body.get("key", "")
        if not ns or not key:
            return {"success": False, "error": "需要 namespace 和 key"}
        # 不允许删除auto_sync的KV
        try:
            conn = _db()
            row = conn.execute("SELECT auto_sync FROM ai_context_kv WHERE namespace=? AND key=?", (ns, key)).fetchone()
            if row and row[0] and row[0] not in ("", "custom", "realtime"):
                conn.close()
                return {"success": False, "error": f"不能删除自动同步的KV(auto_sync={row[0]})"}
            conn.execute("DELETE FROM ai_context_kv WHERE namespace=? AND key=?", (ns, key))
            conn.commit()
            conn.close()
            return {"success": True, "deleted": f"{ns}.{key}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _kv_dump(self):
        """导出全部KV"""
        try:
            conn = _db()
            rows = conn.execute("SELECT namespace,key,value,priority,auto_sync,updated_at FROM ai_context_kv ORDER BY namespace,key").fetchall()
            conn.close()
            result = {}
            for r in rows:
                ns = r[0]
                result.setdefault(ns, {})[r[1]] = {"value": json.loads(r[2]), "priority": r[3], "auto_sync": r[4], "updated_at": r[5]}
            return {"total": len(rows), "data": result}
        except Exception as e:
            return {"error": str(e)}

    # ===== 联动配置接口 =====
    def _get_linkage_config(self):
        """获取所有联动规则配置及执行状态"""
        import copy
        result = {}
        with _LINKAGE_LOCK:
            for key, cfg in _LINKAGE_CONFIG.items():
                result[key] = copy.deepcopy(cfg)
        guard_config = _adaptive_guard.get_config() if _adaptive_guard is not None else {}
        master_enabled = _linkage_master_enabled()
        kitchen_config = guard_config.get("kitchenAlarm", {}) if isinstance(guard_config, dict) else {}
        temperature_config = guard_config.get("highTemperature", {}) if isinstance(guard_config, dict) else {}
        humidity_config = guard_config.get("highHumidity", {}) if isinstance(guard_config, dict) else {}
        if "temp_humidity_ac" in result:
            result["temp_humidity_ac"]["effective_enabled"] = bool(
                master_enabled and (temperature_config.get("enabled", result["temp_humidity_ac"].get("enabled", False))
                                    or humidity_config.get("enabled", result["temp_humidity_ac"].get("enabled", False)))
            )
        if "kitchen_alarm_buzzer" in result:
            result["kitchen_alarm_buzzer"]["effective_enabled"] = bool(
                master_enabled and kitchen_config.get("enabled", result["kitchen_alarm_buzzer"].get("enabled", True))
                and kitchen_config.get("buzzer", result["kitchen_alarm_buzzer"].get("enabled", True))
            )
        if "kitchen_alarm_exhaust" in result:
            result["kitchen_alarm_exhaust"]["effective_enabled"] = bool(
                master_enabled and kitchen_config.get("enabled", True)
                and kitchen_config.get("exhaust", result["kitchen_alarm_exhaust"].get("enabled", True))
            )
        if "living_light_auto" in result:
            result["living_light_auto"]["effective_enabled"] = bool(
                master_enabled and result["living_light_auto"].get("enabled", True)
            )
        # 附加最近执行日志
        try:
            conn = _db()
            rows = conn.execute(
                "SELECT rule_key, trigger_event, action_taken, result, created_at FROM linkage_log ORDER BY id DESC LIMIT 20"
            ).fetchall()
            conn.close()
            recent_log = [
                {"rule_key": r[0], "trigger_event": r[1], "action_taken": r[2], "result": r[3], "time": r[4]}
                for r in rows
            ]
        except Exception:
            recent_log = []
        return {
            "rules": result,
            "recent_log": recent_log,
            "alarm_state": {
                "kitchen_alarm": _last_kitchen_alarm,
                "buzzer_on": _DEVICE_STATUS.get("alarm_01", {}).get("is_on", False),
                "exhaust_on": _DEVICE_STATUS.get("fan_02", {}).get("is_on", False),
                "temp": _SENSOR_STATUS.get("temp_01", {}).get("value"),
                "humidity": _SENSOR_STATUS.get("humid_01", {}).get("value"),
            }
        }

    def _update_linkage_config(self, body):
        """更新联动规则配置 (运行时生效 + SQLite持久化)"""
        rule_key = body.get("rule_key", "")
        updates = body.get("config", {})
        if not rule_key:
            return {"success": False, "error": "需要 rule_key 参数"}
        if rule_key not in _LINKAGE_CONFIG:
            return {"success": False, "error": f"未知联动规则: {rule_key}", "available": list(_LINKAGE_CONFIG.keys())}
        with _LINKAGE_LOCK:
            _LINKAGE_CONFIG[rule_key].update(updates)
            _save_linkage_config()
        hardware_result = None
        if rule_key == "living_light_auto":
            hardware_result = _apply_living_light_auto_linkage(announce=True)
        log(f"[LINKAGE] 配置更新: {rule_key} = {updates}")
        # 记录配置变更
        try:
            conn = _db()
            conn.execute("INSERT INTO linkage_log(rule_key,trigger_event,action_taken,result,detail_json) VALUES(?,?,?,?,?)",
                         (rule_key, "config_update", json.dumps(updates, ensure_ascii=False), "ok", json.dumps({"rule_key": rule_key, "updates": updates})))
            conn.commit(); conn.close()
        except Exception:
            pass
        _record_context_event(
            "linkage_config", f"Linkage {rule_key} updated",
            details={"ruleKey": rule_key, "updates": updates},
            entity_type="rule", entity_id=rule_key, source="api",
        )
        if _context_engine is not None:
            _context_engine.upsert_entity(
                "rule", rule_key, name=_LINKAGE_CONFIG[rule_key].get("description", rule_key),
                capabilities={"configurable": True}, state=_LINKAGE_CONFIG[rule_key],
                source="linkage_config", enabled=bool(_LINKAGE_CONFIG[rule_key].get("enabled", True)),
            )
            _context_engine.rebuild_snapshot()
        result = {"success": True, "rule_key": rule_key, "config": _LINKAGE_CONFIG[rule_key]}
        if hardware_result is not None:
            result["hardware"] = hardware_result
        return result

    # ===== 自适应警戒、评分与App遥测 =====
    def _get_guard_status(self):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable"}
        status = _adaptive_guard.get_status()
        status["planConfirmationEnabled"] = bool(
            _adaptive_guard.get_config().get("planConfirmation", {}).get("enabled", True)
        )
        return {"success": True, **status}

    def _get_guard_config(self):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable"}
        return {"success": True, "config": _adaptive_guard.get_config(),
                "notification": _notification_service.status() if _notification_service else {"enabled": False, "configured": False}}

    def _update_guard_config(self, body):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable"}
        updates = body.get("config", body)
        if "planConfirmationEnabled" in updates:
            updates = dict(updates)
            updates["planConfirmation"] = {"enabled": bool(updates.pop("planConfirmationEnabled"))}
        previous = _adaptive_guard.get_config()
        config = _adaptive_guard.update_config(updates)
        _apply_living_light_auto_linkage(announce=("enabled" in updates))
        _record_context_event(
            "guard_config", "Adaptive guard configuration updated",
            details={"updates": updates}, source="api", severity="info",
        )
        if _context_engine is not None:
            _context_engine.upsert_entity(
                "rule", "adaptive_guard", name="自适应主动警戒",
                aliases=["联动自动管理", "主动智能", "被动智能"],
                capabilities={"feedback": "0-10", "persistentLearning": True},
                state=_adaptive_guard.get_status(include_incidents=False), source="adaptive_guard", enabled=bool(config.get("enabled")),
            )
            _context_engine.rebuild_snapshot()
        # A setting change is itself a user-visible system event. Announce it
        # once so enabling a mode does not appear to do nothing on the device.
        announcements = []
        labels = {
            "enabled": "联动自动管理",
            "activeAiEnabled": "主动 AI 警戒",
            "feedbackAutomation": "评分自动触发",
        }
        for key, label in labels.items():
            if key in updates:
                old_value = previous.get(key, False)
                new_value = config.get(key, False)
                if isinstance(old_value, dict):
                    old_value = old_value.get("enabled", False)
                if isinstance(new_value, dict):
                    new_value = new_value.get("enabled", False)
                if bool(old_value) != bool(new_value):
                    announcements.append(f"{label}{'已开启' if new_value else '已关闭'}")
        if "planConfirmation" in updates:
            old_plan = bool((previous.get("planConfirmation") or {}).get("enabled", True))
            new_plan = bool((config.get("planConfirmation") or {}).get("enabled", True))
            if old_plan != new_plan:
                announcements.append(f"计划确认后执行{'已开启' if new_plan else '已关闭'}")
        if announcements:
            _tts_speak("，".join(announcements))
        return {"success": True, "config": config}

    def _get_guard_incidents(self, limit=50, pending_only=False):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable", "incidents": []}
        incidents = _adaptive_guard.list_incidents(limit=limit, pending_only=pending_only)
        return {"success": True, "incidents": incidents, "total": len(incidents), "pendingOnly": bool(pending_only)}

    def _get_guard_learning(self, query="", limit=20):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable"}
        return {"success": True, **_adaptive_guard.get_learning(query, limit)}

    def _submit_guard_feedback(self, body):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable"}
        incident_id = int(body.get("incidentId", body.get("incident_id", 0)))
        incident = next((item for item in _adaptive_guard.list_incidents(limit=500)
                         if int(item.get("id", 0)) == incident_id), None)
        if not incident or not incident.get("executedActions"):
            return {"success": False, "error": "没有实际执行设备调整的警戒事件不需要评分"}
        score = body.get("score")
        result = _adaptive_guard.submit_feedback(
            incident_id, score,
            body.get("betterAction", body.get("better_action", "")), body.get("notes", ""),
        )
        if _context_engine is not None:
            _context_engine.collect_database_state()
            _context_engine.rebuild_snapshot()
        return result

    def _get_assistant_feed(self, limit=30, since=0):
        if _proactive_intelligence is None:
            return {"success": False, "items": []}
        items = _proactive_intelligence.list_feed(since=since, limit=limit)
        feedback_enabled = bool(
            _adaptive_guard and _adaptive_guard.get_config().get("feedbackAutomation", {}).get("enabled", False)
        )
        for feed_item in items:
            evidence = feed_item.get("evidence") or {}
            adjustment_count = int(evidence.get("adjustmentCount", 0) or 0) if isinstance(evidence, dict) else 0
            feed_item["feedbackEnabled"] = bool(
                feedback_enabled and adjustment_count > 0
            )
        # 将安全警戒事件统一投影到助手流；负 ID 避免与主动报告冲突。
        if _adaptive_guard is not None:
            conversation_cutoff = _proactive_intelligence.conversation_clear_ts()
            guard_candidates = [
                incident for incident in _adaptive_guard.list_incidents(limit=limit)
                if incident.get("needsFeedback") and not incident.get("feedbackReceived")
                and float(incident.get("createdTs", incident.get("created_ts", 0)) or 0) > conversation_cutoff
            ]
            for incident in guard_candidates[:1]:
                incident_id = -int(incident["id"])
                if since and incident_id <= since:
                    continue
                rule_key = incident.get("ruleKey", "guard_incident")
                summaries = {
                    "kitchen_smoke_or_heat_alarm": "厨房检测到烟雾或热敏报警，安全联动已经执行。",
                    "environment_high_temperature": "温度超过阈值，空调调节已经执行。",
                    "environment_high_humidity": "湿度超过阈值，除湿调节已经执行。",
                    "door_event_monitor": "门禁状态发生变化，事件已经记录并播报。",
                }
                incident_created_at = incident.get("createdAt", incident.get("created_at", ""))
                incident_created_ts = incident.get("createdTs", incident.get("created_ts", 0))
                items.append({
                    "id": incident_id,
                    "kind": "guard_incident",
                    "title": rule_key,
                    "summary": summaries.get(rule_key, "系统检测到需要主人确认的安全事件。"),
                    "severity": "danger" if int(incident.get("guardLevel", 0)) >= 8 else "warning",
                    "evidence": incident.get("evidence", {}),
                    "operations": incident.get("executedActions", []),
                    "chart": {},
                    "feedback": None if not incident.get("feedbackReceived") else {"score": 0, "choice": "", "note": ""},
                    "feedbackEnabled": bool(feedback_enabled and incident.get("executedActions")),
                    "createdAt": incident_created_at,
                    "createdTs": incident_created_ts,
                })
        items.sort(key=lambda item: (float(item.get("createdTs") or 0), abs(int(item.get("id", 0)))), reverse=True)
        return {"success": True, "items": items[:max(1, min(int(limit), 100))]}

    def _submit_assistant_feedback(self, body):
        if _proactive_intelligence is None:
            return {"success": False, "error": "proactive intelligence unavailable"}
        event_id = int(body.get("eventId", body.get("event_id", 0)))
        score = body.get("score")
        if event_id < 0 and _adaptive_guard is not None:
            incident = next((item for item in _adaptive_guard.list_incidents(limit=500)
                             if int(item.get("id", 0)) == abs(event_id)), None)
            if not incident or not incident.get("executedActions"):
                return {"success": False, "error": "没有实际执行设备调整的警戒事件不需要评分"}
            return _adaptive_guard.submit_feedback(
                abs(event_id), score, body.get("choice", body.get("betterAction", "")), body.get("note", body.get("notes", "")),
            )
        try:
            result = _proactive_intelligence.submit_feedback(
                event_id, score, body.get("choice", ""), body.get("note", body.get("notes", "")),
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        _record_context_event(
            "assistant_feedback", f"Assistant event {event_id} rated {result['score']}/10",
            details=result, source="assistant", severity="info",
        )
        return {"success": True, **result}

    def _get_external_feed(self):
        """Return a five-minute cached external digest; never blocks device APIs."""
        global _external_digest_cache, _external_digest_at
        if _external_intelligence is None:
            return {"success": False, "items": [], "categories": [], "error": "外部信息服务未初始化"}
        now = time.time()
        with _external_digest_lock:
            if now - _external_digest_at < 300 and _external_digest_cache.get("success"):
                return _external_digest_cache
        try:
            result = _external_intelligence.collect()
        except Exception as exc:
            result = {"success": False, "items": [], "categories": [], "error": str(exc)[:180]}
        with _external_digest_lock:
            _external_digest_cache = result
            _external_digest_at = now
        return result

    def _get_external_config(self):
        if _external_intelligence is None:
            return {"success": False, "error": "外部信息服务未初始化"}
        return {"success": True, **_external_intelligence.get_config()}

    def _update_external_config(self, body):
        if _external_intelligence is None:
            return {"success": False, "error": "外部信息服务未初始化"}
        try:
            result = _external_intelligence.update_config(body if isinstance(body, dict) else {})
        except (TypeError, ValueError) as exc:
            return {"success": False, "error": str(exc)}
        global _external_digest_at
        with _external_digest_lock:
            _external_digest_at = 0.0
        _record_context_event("external_config", "外部信息采集设置已更新",
                              details={"enabled": result.get("enabled"), "locationName": result.get("locationName"),
                                       "hasCoordinates": bool(result.get("latitude") and result.get("longitude"))},
                              source="settings", severity="info")
        _tts_speak("外部信息采集已开启" if result.get("enabled") else "外部信息采集已关闭", category="settings")
        return {"success": True, **result}

    def _confirm_assistant_plan(self, body):
        scope = _plan_scope(body)
        nonce = str(body.get("planNonce", body.get("plan_nonce", "")) or "")
        digest = str(body.get("planDigest", body.get("plan_digest", "")) or "")
        if not nonce:
            return {"success": False, "error": "缺少计划确认令牌"}
        entry = _claim_pending_plan(scope, nonce, digest)
        if not entry:
            return {"success": False, "error": "计划不存在、已过期或校验不一致"}
        if entry.get("status") == "completed":
            return entry.get("result", {"success": False, "error": "计划已处理"})
        if entry.get("status") == "claimed" and not entry.get("_claimed_here", False):
            return {"success": False, "error": "计划正在处理，请稍候", "status": "claimed"}
        if entry.get("status") == "claimed":
            payload = dict(entry.get("payload") or {})
            if payload.get("type") == "device_toggle" and payload.get("device_id") == "door_01":
                result = {"success": False, "error": "门禁不能从计划卡执行，必须手动输入密码"}
            elif payload.get("type") == "ai_commands":
                results = []
                for command in _safe_plan_commands(payload.get("commands", [])):
                    results.append(self._execute_ai_command(command))
                result = {"success": all(bool(item and item.get("success", False)) for item in results), "actions": results}
            else:
                result = self._execute_intent(payload)
            with _PENDING_PLAN_LOCK:
                current = _PENDING_INTENT_PLANS.get(scope)
                if current and current.get("planNonce") == nonce:
                    current["status"] = "completed"
                    current["result"] = result
                    current["completedAt"] = time.time()
            _record_context_event("plan_confirmed", "助手计划卡已确认", details={"planDigest": entry.get("planDigest"), "result": result}, source="assistant", severity="info")
            return {"success": bool(result.get("success", False)), "planDigest": entry.get("planDigest"), "result": result}
        return {"success": False, "error": "计划正在处理，请稍候", "status": entry.get("status")}

    def _cancel_assistant_plan(self, body):
        scope = _plan_scope(body)
        nonce = str(body.get("planNonce", body.get("plan_nonce", "")) or "")
        with _PENDING_PLAN_LOCK:
            entry = _PENDING_INTENT_PLANS.get(scope)
            if not entry or str(entry.get("planNonce", "")) != nonce:
                return {"success": False, "error": "计划不存在或已过期"}
            if entry.get("status") != "pending":
                return {"success": False, "error": "计划已经被处理", "status": entry.get("status")}
            entry["status"] = "cancelled"
            entry["cancelledAt"] = time.time()
        _record_context_event("plan_cancelled", "助手计划卡已取消", details={"planDigest": entry.get("planDigest")}, source="assistant", severity="info")
        return {"success": True, "planDigest": entry.get("planDigest"), "status": "cancelled"}

    def _record_app_telemetry(self, body):
        if _adaptive_guard is None:
            return {"success": False, "error": "adaptive guard unavailable"}
        event_id = _adaptive_guard.record_app_telemetry(body)
        _record_context_event(
            "app_telemetry", f"App telemetry {body.get('eventType', 'unknown')}",
            details={"eventId": event_id, "page": body.get("page", ""), "action": body.get("action", ""), "result": body.get("result", "")},
            source="app", severity="info",
        )
        return {"success": True, "eventId": event_id}

    # ===== 新增: 情感分析接口 =====
    def _analyze_emotion(self, body):
        """分析文本情绪"""
        text = body.get("message", body.get("text", ""))
        if not text:
            return {"error": "需要 message 参数"}
        if _intent_engine:
            return _intent_engine.analyze_emotion(text)
        return {}

    # ===== 新增: 对话记忆接口 =====
    def _get_context_summary(self):
        """获取对话上下文摘要"""
        if _intent_engine:
            return {"context": _intent_engine.get_context_summary()}
        return {"context": ""}

    def _context_manifest(self):
        if _context_engine is None:
            return {"error": "上下文引擎未初始化", "code": 503}
        try:
            if not PROJECT_CONTEXT_PATH.exists():
                _context_engine.rebuild_snapshot()
            return json.loads(PROJECT_CONTEXT_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"error": str(exc), "code": 500}

    def _context_stats(self):
        manifest = self._context_manifest()
        return {
            "schemaVersion": manifest.get("schemaVersion"),
            "generatedAt": manifest.get("generatedAt"),
            **manifest.get("collectionStats", {}),
        }

    def _context_search(self, query):
        if _context_engine is None:
            return {"query": query, "matches": [], "error": "上下文引擎未初始化"}
        if not str(query).strip():
            return {"query": query, "matches": [], "error": "需要 query 或 q 参数"}
        return {"query": query, "matches": _context_engine.search(str(query), limit=60, event_limit=100)}

    def _context_rebuild(self):
        if _context_engine is None:
            return {"success": False, "error": "上下文引擎未初始化"}
        static = _context_engine.collect_static_sources()
        database = _context_engine.collect_database_state()
        snapshot = _context_engine.rebuild_snapshot()
        _record_context_event("context_rebuild", "Context rebuilt", details={"static": static, "database": database})
        return {"success": True, "static": static, "database": database, "stats": snapshot["collectionStats"]}

    def _clear_context(self):
        """清空对话记忆"""
        if _intent_engine:
            _intent_engine.clear_memory()
        with _PENDING_PLAN_LOCK:
            _PENDING_INTENT_PLANS.clear()
        if _proactive_intelligence is not None:
            _proactive_intelligence.clear_conversation()
        try:
            conn = _db()
            conn.execute("DELETE FROM chat_history")
            conn.commit(); conn.close()
        except Exception:
            pass
        return {"success": True, "message": "助手对话已清空，历史学习日志保留"}

    # ===== 新增: 设备注册接口 =====
    def _register_device(self, body):
        """注册新设备"""
        if _intent_engine:
            result = _intent_engine.register_device(body)
            if result.get("success") and _context_engine is not None:
                _context_engine.upsert_entity(
                    "device", body["id"], name=body.get("name", body["id"]),
                    aliases=body.get("aliases", []),
                    capabilities=body.get("capabilities", []),
                    state={"type": body.get("type"), "room": body.get("room"), "custom": True},
                    source="device_registry", enabled=True,
                )
                _context_engine.rebuild_snapshot()
                _record_context_event(
                    "device_registered", f"Custom device {body['id']} registered",
                    details={"device": body}, entity_type="device", entity_id=body["id"],
                    source="registry",
                )
            return result
        return {"success": False, "error": "意图引擎未初始化"}

    def _unregister_device(self, body):
        """注销设备"""
        device_id = body.get("device_id", body.get("id", ""))
        if not device_id:
            return {"success": False, "error": "需要 device_id 参数"}
        if _intent_engine:
            result = _intent_engine.unregister_device(device_id)
            if result.get("success") and _context_engine is not None:
                _context_engine.upsert_entity(
                    "device", device_id, name=device_id, source="device_registry",
                    state={"custom": True, "unregistered": True}, enabled=False,
                )
                _context_engine.rebuild_snapshot()
                _record_context_event(
                    "device_unregistered", f"Custom device {device_id} unregistered",
                    entity_type="device", entity_id=device_id, source="registry",
                )
            return result
        return {"success": False, "error": "意图引擎未初始化"}

    def _list_device_templates(self):
        """列出所有设备模板"""
        if _intent_engine:
            return _intent_engine.list_device_templates()
        return []

    def _get_radar_config(self):
        with _LINKAGE_LOCK:
            return {
                "radar_presence": dict(_LINKAGE_CONFIG["radar_presence"]),
                "radar_light": dict(_LINKAGE_CONFIG["radar_light"]),
                "independent": True,
                "zones_cm": {
                    "kitchen": [20, 35], "bathroom": [40, 55],
                    "living_room": [60, 85], "bedroom": [90, 110],
                },
                "filter": {"sampleWindow": 7, "stableSamples": 5},
            }

    def _set_radar_enabled(self, enabled):
        with _LINKAGE_LOCK:
            _LINKAGE_CONFIG["radar_presence"]["enabled"] = bool(enabled)
            _save_linkage_config()
        _record_context_event(
            "radar_config", f"Radar presence {'enabled' if enabled else 'disabled'}",
            details={"radarPresenceEnabled": bool(enabled), "radarLightUnchanged": True},
            entity_type="device", entity_id="radar_01", source="mcp",
        )
        if _context_engine is not None:
            _context_engine.upsert_entity(
                "device", "radar_01", name="毫米波雷达", aliases=["毫米波", "人体存在"],
                capabilities={"radar_presence": {"enabled": bool(enabled)}, "radar_light": dict(_LINKAGE_CONFIG["radar_light"])},
                state=self._get_radar_config(), source="runtime", enabled=True,
            )
            _context_engine.rebuild_snapshot()
        return {"success": True, **self._get_radar_config()}

    def _register_capability(self, capability):
        allowed_executors = {
            "device_toggle", "device_control", "scene_activate",
            "safe_internal_api", "read_only_query",
        }
        if not isinstance(capability, dict):
            return {"success": False, "error": "capability 必须是对象"}
        capability_id = str(capability.get("id", "")).strip()
        name = str(capability.get("name", "")).strip()
        executor_type = capability.get("executor_type")
        if not capability_id or not name:
            return {"success": False, "error": "capability 需要 id 和 name"}
        if executor_type not in allowed_executors:
            return {"success": False, "error": "executor_type 不在安全白名单", "allowed": sorted(allowed_executors)}
        if _context_engine is None:
            return {"success": False, "error": "上下文引擎未初始化"}
        _context_engine.upsert_entity(
            "capability", capability_id, name=name,
            aliases=capability.get("aliases", []), capabilities=capability,
            state={"registered": True}, source="capability_registry", enabled=True,
        )
        _context_engine.rebuild_snapshot()
        _record_context_event(
            "capability_registered", f"Capability {capability_id} registered",
            details={"capability": capability}, entity_type="capability",
            entity_id=capability_id, source="registry",
        )
        return {"success": True, "capability": capability}

    def _invoke_capability(self, capability_id, arguments=None):
        if _context_engine is None:
            return {"success": False, "error": "上下文引擎未初始化"}
        arguments = dict(arguments or {})
        conn = _context_engine._connect()
        try:
            row = conn.execute(
                "SELECT capabilities_json FROM ai_context_entities "
                "WHERE entity_type='capability' AND entity_id=? AND enabled=1",
                (capability_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return {"success": False, "error": f"能力不存在或未启用: {capability_id}"}
        capability = json.loads(row[0])
        executor_type = capability.get("executor_type")
        target_device_id = capability.get("target_device_id") or arguments.get("device_id")
        if target_device_id == "door_01":
            return {"success": False, "error": "自定义能力禁止调用门禁；请使用 door_control 并人工输入本次密码"}

        if executor_type == "device_toggle":
            if not target_device_id or not isinstance(arguments.get("is_on"), bool):
                return {"success": False, "error": "device_toggle 需要 target_device_id 和布尔 is_on"}
            return self._toggle_device(target_device_id, {"isOn": arguments["is_on"]})

        if executor_type == "device_control":
            action = capability.get("action") or arguments.get("action")
            if not target_device_id or not action:
                return {"success": False, "error": "device_control 需要 target_device_id 和 action"}
            params = dict(arguments.get("params") or {})
            for key in ("value", "mode"):
                if key in arguments:
                    params[key] = arguments[key]
            return self._control_device(target_device_id, {"action": action, "params": params})

        if executor_type == "scene_activate":
            scene_id = capability.get("target_scene_id") or arguments.get("scene_id")
            if not scene_id:
                return {"success": False, "error": "scene_activate 需要 target_scene_id"}
            return self._activate_scene({"scene_id": scene_id})

        read_only_targets = {
            "live_status": lambda: _context_live_state(),
            "devices": lambda: self._get_devices(),
            "sensors": lambda: self._get_sensors(),
            "radar_config": lambda: self._get_radar_config(),
            "linkage_config": lambda: self._get_linkage_config(),
            "context_search": lambda: self._context_search(arguments.get("query", "")),
        }
        if executor_type == "read_only_query":
            target = capability.get("target")
            handler = read_only_targets.get(target)
            if handler is None:
                return {"success": False, "error": "read_only_query target 不在白名单", "allowed": sorted(read_only_targets)}
            return {"success": True, "data": handler()}

        safe_internal_targets = {
            "activate_scene": lambda: self._activate_scene({"scene_id": arguments.get("scene_id")}),
            "set_linkage_config": lambda: self._update_linkage_config({"rule_key": arguments.get("rule_key"), "config": arguments.get("config", {})}),
            "set_radar_enabled": lambda: self._set_radar_enabled(arguments.get("enabled")),
            "rebuild_context": lambda: self._context_rebuild(),
        }
        if executor_type == "safe_internal_api":
            target = capability.get("target")
            if target == "set_radar_enabled" and not isinstance(arguments.get("enabled"), bool):
                return {"success": False, "error": "set_radar_enabled 需要布尔 enabled"}
            handler = safe_internal_targets.get(target)
            if handler is None:
                return {"success": False, "error": "safe_internal_api target 不在白名单", "allowed": sorted(safe_internal_targets)}
            return handler()

        return {"success": False, "error": f"不支持的 executor_type: {executor_type}"}

    def _list_context_capabilities(self):
        if _context_engine is None:
            return []
        return [hit for hit in _context_engine.search("capability 功能 能力", limit=100) if hit.get("kind") == "entity"]

    def _get_recent_context_logs(self, limit=100, severity=None):
        if _context_engine is None:
            return []
        conn = _context_engine._connect()
        try:
            if severity:
                rows = conn.execute(
                    "SELECT event_type,summary,details_json,source,severity,created_at FROM ai_context_events "
                    "WHERE severity=? ORDER BY id DESC LIMIT ?", (severity, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT event_type,summary,details_json,source,severity,created_at FROM ai_context_events "
                    "ORDER BY id DESC LIMIT ?", (int(limit),),
                ).fetchall()
            return [{"type": row[0], "summary": row[1], "details": json.loads(row[2]), "source": row[3], "severity": row[4], "createdAt": row[5]} for row in rows]
        finally:
            conn.close()

    # ═══════════════════════════════════════════════════════════════
    # 远程管理接口实现
    # ═══════════════════════════════════════════════════════════════

    def _list_api_keys(self):
        conn = sqlite3.connect(str(_API_KEY_DB))
        rows = conn.execute("SELECT key_id, name, permissions, is_active, created_at, last_used, usage_count, rate_limit, expires_at FROM api_keys").fetchall()
        conn.close()
        return [{"key_id": r[0], "name": r[1], "permissions": r[2], "is_active": bool(r[3]),
                 "created_at": r[4], "last_used": r[5], "usage_count": r[6], "rate_limit": r[7],
                 "expires_at": r[8]} for r in rows]

    def _create_api_key(self, body):
        name = body.get("name", "新密钥")
        permissions = body.get("permissions", "read")
        rate_limit = body.get("rate_limit", 100)
        expires_at = body.get("expires_at")
        key_id = f"key_{int(time.time())}"
        api_key = "sm_" + os.urandom(24).hex()[:48]
        conn = sqlite3.connect(str(_API_KEY_DB))
        conn.execute("INSERT INTO api_keys(key_id, api_key, name, permissions, rate_limit, expires_at) VALUES(?,?,?,?,?,?)",
                     (key_id, api_key, name, permissions, rate_limit, expires_at))
        conn.commit(); conn.close()
        return {"key_id": key_id, "api_key": api_key, "name": name, "permissions": permissions}

    def _revoke_api_key(self, body):
        key_id = body.get("key_id", "")
        conn = sqlite3.connect(str(_API_KEY_DB))
        conn.execute("UPDATE api_keys SET is_active=0 WHERE key_id=?", (key_id,))
        conn.commit(); conn.close()
        return {"success": True, "key_id": key_id}

    def _remote_access_log(self):
        conn = _db()
        rows = conn.execute("SELECT client_id, endpoint, method, ip_address, status_code, encrypted, created_at FROM remote_access_log ORDER BY created_at DESC LIMIT 200").fetchall()
        conn.close()
        return [{"client_id": r[0], "endpoint": r[1], "method": r[2], "ip": r[3], "status": r[4], "encrypted": bool(r[5]), "timestamp": r[6]} for r in rows]

    def _crypto_status(self):
        return {
            "sm3_available": True,
            "sm4_available": True,
            "sm2_available": True,
            "envelope_version": 1,
            "sm4_key_fingerprint": sm3_hash(_SM4_KEY).hex()[:16],
            "sm2_device_pubkey": _SM2_KEYPAIR.public_key_hex[:32] + "...",
            "remote_pubkey_registered": _REMOTE_SM2_PUB is not None,
            "nonce_cache_size": len(__import__('gm_crypto')._NONCE_CACHE),
        }

    def _crypto_self_test(self):
        from gm_crypto import self_test
        return self_test()

    def _rotate_sm4_key(self):
        global _SM4_KEY, _envelope
        old_fp = sm3_hash(_SM4_KEY).hex()[:16]
        _SM4_KEY = generate_sm4_key()
        _SM4_KEY_FILE.write_text(_SM4_KEY.hex())
        _envelope = SecureEnvelope(_SM4_KEY, _SM2_KEYPAIR)
        new_fp = sm3_hash(_SM4_KEY).hex()[:16]
        return {"success": True, "old_fingerprint": old_fp, "new_fingerprint": new_fp, "note": "远程服务器需同步更新SM4密钥"}

    def _register_remote_pubkey(self, body):
        pubkey_hex = body.get("public_key", "")
        if not pubkey_hex or len(pubkey_hex) != 130:
            return {"error": "公钥格式错误 (需要未压缩格式 04||X||Y, 130 hex字符)"}
        try:
            pubkey_bytes = bytes.fromhex(pubkey_hex)
            _SM2_REMOTE_PUB_FILE.write_text(pubkey_hex)
            return {"success": True, "fingerprint": sm3_hash(pubkey_bytes).hex()[:16]}
        except Exception as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════

def _initialize_super_context():
    global _context_engine, _super_mcp
    _context_engine = ContextEngine(
        db_path=DB_PATH,
        root_dir=SMART_HOME_DIR,
        snapshot_path=PROJECT_CONTEXT_PATH,
        max_chars=int(os.environ.get("A9_CONTEXT_MAX_CHARS", "48000")),
    )
    service = object.__new__(H)

    def get_device(device_id):
        return next((item for item in service._get_devices() if item.get("id") == device_id), {"error": "设备不存在", "device_id": device_id})

    def control_device(device_id, action, value=None, mode=None):
        params = {}
        if value is not None:
            params["value"] = value
        if mode is not None:
            params["mode"] = mode
        return service._control_device(device_id, {"action": action, "params": params})

    handlers = {
        "get_live_status": lambda: _context_live_state(),
        "list_devices": lambda: service._get_devices(),
        "get_device": get_device,
        "list_sensors": lambda: service._get_sensors(),
        "get_recent_operations": lambda device_id=None, limit=200: service._get_operations(device_id, 7, limit),
        "get_recent_logs": lambda limit=100, severity=None: service._get_recent_context_logs(limit, severity),
        "get_linkage_config": lambda: service._get_linkage_config(),
        "get_guard_status": lambda: service._get_guard_status(),
        "get_pending_guard_feedback": lambda limit=50: service._get_guard_incidents(limit, True),
        "get_guard_learning": lambda query="", limit=20: service._get_guard_learning(query, limit),
        "get_radar_config": lambda: service._get_radar_config(),
        "list_capabilities": lambda: service._list_context_capabilities(),
        "toggle_device": lambda device_id, is_on: service._toggle_device(device_id, {"isOn": is_on}),
        "control_device": control_device,
        "activate_scene": lambda scene_id: service._activate_scene({"scene_id": scene_id}),
        "set_linkage_config": lambda rule_key, config: service._update_linkage_config({"rule_key": rule_key, "config": config}),
        "set_guard_config": lambda config: service._update_guard_config({"config": config}),
        "submit_guard_feedback": lambda incident_id, score, better_action="", notes="": service._submit_guard_feedback({
            "incident_id": incident_id, "score": score, "better_action": better_action, "notes": notes,
        }),
        "set_radar_enabled": lambda enabled: service._set_radar_enabled(enabled),
        "register_device": lambda device: service._register_device(device),
        "unregister_device": lambda device_id: service._unregister_device({"device_id": device_id}),
        "register_capability": lambda capability: service._register_capability(capability),
        "invoke_capability": lambda capability_id, arguments=None: service._invoke_capability(capability_id, arguments),
        "door_control": lambda action, password=None: service._door_control({"action": action, "password": password}),
    }
    _super_mcp = SuperMCP(_context_engine, tool_handlers=handlers)

    static_result = _context_engine.collect_static_sources()
    database_result = _context_engine.collect_database_state()
    for api in _build_api_list():
        _context_engine.upsert_entity(
            "api", api["path"], name=api["desc"],
            aliases=api.get("methods", []), capabilities=api,
            state={"auth": api.get("auth")}, source="gateway_routes", enabled=True,
        )
    for index, capability in enumerate(_build_capability_desc()):
        capability_id = f"builtin_{index}_{capability['name']}"
        _context_engine.upsert_entity(
            "capability", capability_id, name=capability["name"],
            capabilities=capability, state={"builtin": True},
            source="gateway_capabilities", enabled=True,
        )
    for rule_key, config in _LINKAGE_CONFIG.items():
        _context_engine.upsert_entity(
            "rule", rule_key, name=config.get("description", rule_key),
            capabilities={"configurable": True}, state=config,
            source="linkage_config", enabled=bool(config.get("enabled", True)),
        )
    if _adaptive_guard is not None:
        _context_engine.upsert_entity(
            "rule", "adaptive_guard", name="自适应主动警戒",
            aliases=["联动自动管理", "主动智能", "被动智能", "主人评分"],
            capabilities={"feedback": "0-10", "persistentLearning": True, "doorAutomation": False},
            state=_adaptive_guard.get_status(include_incidents=False), source="adaptive_guard",
            enabled=bool(_adaptive_guard.get_config().get("enabled", True)),
        )
    for tool in _super_mcp.list_tools():
        _context_engine.upsert_entity(
            "mcp_tool", tool["name"], name=tool["name"],
            aliases=[], capabilities={"description": tool["description"], "inputSchema": tool["inputSchema"]},
            state={"annotations": tool.get("annotations", {})}, source="super_mcp", enabled=True,
        )
    for source, path in (("gateway", LOG_PATH), ("gateway_stdout", ROOT / "gateway_stdout.log")):
        if path.exists():
            _context_engine.ingest_log(path, source)
    snapshot = _context_engine.rebuild_snapshot()
    _record_context_event(
        "context_initialized", "Super context and MCP initialized",
        details={"static": static_result, "database": database_result, "stats": snapshot["collectionStats"]},
        source="startup",
    )
    _context_engine.rebuild_snapshot()
    log(f"[CONTEXT] 超级上下文已初始化: {snapshot['collectionStats']}")


def _initialize_super_context_runtime():
    """Build the large RAG/MCP snapshot without delaying device and settings APIs."""
    try:
        _initialize_super_context()
        threading.Thread(target=_context_sync_thread, daemon=True).start()
    except Exception as exc:
        log(f"[CONTEXT] 超级上下文初始化失败: {exc}")


def main():
    global _intent_engine, _proto_gateway, _external_intelligence
    log("=" * 60)
    log("智慧家居安全远程 API 网关 v6 + AI 智能意图")
    log(f"国密双层加密: SM3 + SM4-CBC + SM2")
    log(f"设备 SM2 公钥: {_SM2_KEYPAIR.public_key_hex[:32]}...")
    log(f"SM4 密钥指纹: {sm3_hash(_SM4_KEY).hex()[:16]}")
    log(f"硬件桥接: {'已加载' if _HW_OK else '未加载'}")
    log("=" * 60)

    db_init()
    _external_intelligence = ExternalIntelligenceCollector(
        str(DB_PATH),
        max_items=int(os.environ.get("A9_EXTERNAL_MAX_ITEMS", "24")),
        timeout=int(os.environ.get("A9_EXTERNAL_TIMEOUT", "6")),
    )
    log("[EXTERNAL] 外部信息缓存已初始化（失败隔离、五分钟缓存）")
    _init_api_key_db()
    _initialize_adaptive_guard()

    # 初始化意图引擎
    _intent_engine = IntentEngine(
        get_context_fn=_get_intent_context,
        get_status_fn=_get_anomaly_status,
        db_path=str(DB_PATH),
        log_fn=log,
        tts_fn=_tts_speak,
    )
    log("[INTENT] AI 智能意图引擎已初始化")

    # 设置联动引擎执行器(直接调用硬件桥接)
    def _linkage_executor(intent):
        try:
            itype = intent.get("type", "")
            if itype == "device_toggle":
                return hw_toggle(intent.get("device_id", ""), intent.get("isOn", True))
            elif itype == "device_control":
                return hw_control(intent.get("device_id", ""), intent.get("action", "toggle"), intent.get("params", {}))
            return None
        except Exception as e:
            log(f"[LINKAGE] 执行失败: {e}")
            return None
    _intent_engine.set_linkage_executor(_linkage_executor)
    log("[INTENT] 联动引擎执行器已设置")

    # 加载联动配置 (SQLite → 内存)
    _load_linkage_config()
    _apply_living_light_auto_linkage(announce=False)
    log(f"[LINKAGE] 联动配置已加载: {list(_LINKAGE_CONFIG.keys())}")

    # 同步KV上下文引擎
    _sync_kv_from_code()
    _update_kv_realtime()
    log("[KV] 上下文引擎已初始化")

    threading.Thread(target=_initialize_super_context_runtime, daemon=True).start()

    # 启动轮询线程
    threading.Thread(target=sensor_poll_thread, daemon=True).start()
    threading.Thread(target=udp_alarm_listener, daemon=True).start()
    threading.Thread(target=_proactive_cycle_thread, daemon=True).start()
    log("[PROACTIVE] 五分钟助手汇总线程已启动")

    # 启动异常检测线程
    _intent_engine.start_anomaly_detector(interval=30.0)

    # 启动数据推送
    try:
        from data_pusher import start_pusher
        start_pusher()
        log("[PUSHER] 数据推送服务已启动")
    except Exception as e:
        log(f"[PUSHER] 启动失败: {e}")

    # 启动多协议安全传输网关
    try:
        from protocol_gateway import ProtocolGateway
        _proto_gateway = ProtocolGateway(_SM4_KEY, _SM2_KEYPAIR)
        _proto_gateway.start()
        log("[PROTO] 多协议网关已启动 (HTTPS:8443 / WS:8080/ws / MQTT:1883 / CoAP:5683)")
    except Exception as e:
        log(f"[PROTO] 多协议网关启动失败: {e}")
        _proto_gateway = None

    # 启动 HTTP 服务
    server = BoundedThreadingHTTPServer(
        (HOST, PORT), H,
        max_workers=int(os.environ.get("A9_HTTP_MAX_WORKERS", "64")),
    )
    log(f"[HTTP] 网关监听 {HOST}:{PORT}")
    _ensure_voice_bridge()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("[HTTP] 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
