"""ESP32-S3 LED 自定义设备适配器。

设备文档只定义了 HTTP 接口，因此这里把“发现”和“控制”隔离成一个小适配器：

* 发现只访问用户指定的中控地址 ``/api/state``，读取其公开的 ``esp_ip``；
* 随后仅探测该 IP 的 LED 状态接口，不做端口扫描、不枚举其他内网主机；
* 设备必须真实支持 ``/api/status`` + ``/api/led`` 文档接口；开发板离线或
  状态接口不可达时，本次发现失败，不生成模拟设备，也不写入注册表；
* 注册信息只保存设备 ID、能力和传输方式，不保存 API 密钥、请求体或完整内网日志。

这使得上层网关不需要知道 ESP32 的具体协议细节，后续增加 MQTT/CoAP 设备时也可
复用同一套注册/控制契约。
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from protocol_contract import Capability


_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_COLORS = {"red", "green", "blue"}
_TRUE = {"1", "on", "true", "yes"}
_FALSE = {"0", "off", "false", "no"}
_TYPE_LABELS = {
    "light": "灯光设备", "fan": "风扇设备", "ac": "空调设备",
    "curtain": "窗帘设备", "switch": "智能开关", "socket": "智能插座",
    "sensor": "环境传感器", "camera": "摄像头", "custom": "其他设备",
}


def _private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
        return ip.version == 4 and (ip.is_private or ip.is_loopback)
    except ValueError:
        return False


def _safe_base(url: str) -> str:
    """只接受内网 HTTP(S) 基址，去掉路径/查询参数，避免 SSRF 和凭据泄露。"""
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("发现地址必须是 http(s) 内网地址")
    if not _private_ip(parsed.hostname):
        raise ValueError("发现地址只允许内网 IPv4 地址")
    if parsed.username or parsed.password:
        raise ValueError("发现地址不允许携带凭据")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return urlunsplit((parsed.scheme, f"{parsed.hostname}:{port}", "", "", ""))


def _safe_board_url(ip: str, port: Any = 80) -> str:
    if not _private_ip(str(ip)):
        raise ValueError("设备 IP 不是受支持的内网 IPv4")
    try:
        port_num = int(port)
    except (TypeError, ValueError):
        port_num = 80
    if not 1 <= port_num <= 65535:
        port_num = 80
    return f"http://{ip}:{port_num}"


def _json_request(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 2.5) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(64 * 1024)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("设备返回不是 JSON 对象")
        return data


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


class CustomLedAdapter:
    """面向网关的线程安全 LED 适配器和最小设备注册表。"""

    adapter_id = "esp32_led_http"
    protocol = "http"
    supported_scan_types = {"light"}

    def __init__(self, registry_path: str | Path, discovery_url: str | None = None):
        self.registry_path = Path(registry_path)
        self.discovery_url = _safe_base(
            discovery_url or os.environ.get("A9_CUSTOM_DISCOVERY_URL", "http://192.168.1.102:8080")
        )
        self._lock = threading.RLock()
        self._registry: dict[str, dict] = self._load()
        self._pending: dict[str, dict] = {}

    def _load(self) -> dict[str, dict]:
        try:
            value = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def capabilities(self) -> list[Capability]:
        return [
            Capability("query", "查询 LED 状态"),
            Capability("on", "打开 LED", {"color": "red|green|blue?"}),
            Capability("off", "关闭 LED"),
            Capability("toggle", "切换 LED", {"isOn": "bool", "color": "red|green|blue?"}),
            Capability("set_color", "设置 LED 颜色", {"color": "red|green|blue"}),
        ]

    def query(self, device_id: str) -> dict[str, Any]:
        return self.status(device_id)

    def invoke(self, device_id: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.control(device_id, action, params)

    def _save(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._registry, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.registry_path)

    @staticmethod
    def _descriptor(device_id: str, name: str, room: str, base: str, transport: str,
                    state: dict | None = None, board_ip: str = "", scan_type: str = "custom",
                    manufacturer: str = "自研", dev_board: str = "ESP32") -> dict:
        state = state or {}
        return {
            "id": device_id,
            "name": name,
            "type": "custom",
            "room": room,
            "icon": "lightbulb",
            "status": "online",
            "isOn": _bool(state.get("led_enabled"), False),
            "primaryValue": 100 if _bool(state.get("led_enabled"), False) else 0,
            "mode": str(state.get("led_color", "red")),
            "protocol": "http",
            "transport": transport,
            "endpoint": base,
            "board_ip": board_ip,
            "custom": True,
            "scan_type": scan_type if scan_type in _TYPE_LABELS else "custom",
            "manufacturer": manufacturer[:48],
            "dev_board": dev_board[:48],
            "capabilities": [
                {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关设备"},
                {"action": "set_color", "params": {"color": "red|green|blue"}, "desc": "设置颜色"},
                {"action": "query", "params": {}, "desc": "查询状态"},
            ],
            "last_discovered_at": int(time.time()),
        }

    def discover(self, name: str = "", room: str = "自定义设备", device_type: str = "light",
                 persist: bool = False, manufacturer: str = "自研", dev_board: str = "ESP32") -> dict:
        """按类型定向发现：中控 /api/state → esp_ip → 设备状态接口。"""
        scan_type = device_type if device_type in _TYPE_LABELS else "custom"
        if scan_type not in self.supported_scan_types:
            raise RuntimeError("当前局域网发现源未声明该设备类型的兼容能力")
        name = (name or _TYPE_LABELS[scan_type])[:64]
        state = _json_request(self.discovery_url + "/api/state")
        board_ip = str(state.get("esp_ip", "")).strip()
        if not board_ip:
            raise RuntimeError("中控没有返回 esp_ip")

        # 文档默认端口为 80；若中控额外公开 led_port 才使用该值。
        board_base = _safe_board_url(board_ip, state.get("led_port", 80))
        transport = "http"
        try:
            board_state = _json_request(board_base + "/api/status")
        except Exception as exc:
            raise RuntimeError("设备未联网或状态接口不可达") from exc
        if not isinstance(board_state, dict) or board_state.get("ok") is False:
            raise RuntimeError("设备状态接口返回异常，未通过在线校验")
        device_id = "custom_led_" + re.sub(r"[^0-9a-f]", "", board_ip.replace(".", ""))[:12]
        descriptor = self._descriptor(device_id, name, room, board_base, transport, board_state, board_ip, scan_type,
                                      manufacturer, dev_board)
        with self._lock:
            if persist:
                self._registry[device_id] = descriptor
                self._save()
            else:
                self._pending[device_id] = descriptor
        return {"success": True, "device": descriptor, "discovery": {
            "source": self.discovery_url,
            "board_ip": board_ip,
            "transport": transport,
            "simulated_scan": False,
            "verified_online": True,
            "scanned_hosts": 1,
        }}

    def register_pending(self, device_id: str) -> dict:
        with self._lock:
            descriptor = self._pending.pop(str(device_id), None)
            if descriptor is None:
                return {"success": False, "error": "扫描结果已过期，请重新扫描"}
            self._registry[str(device_id)] = descriptor
            self._save()
            return {"success": True, "device": dict(descriptor)}

    def list_devices(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._registry.values()]

    def get(self, device_id: str) -> dict | None:
        with self._lock:
            item = self._registry.get(device_id)
            return dict(item) if item else None

    def status(self, device_id: str) -> dict:
        device = self.get(device_id)
        if not device:
            return {"success": False, "error": "自定义设备不存在"}
        if device.get("transport") != "http":
            return {"success": False, "online": False, "error": "设备记录不是经在线校验的真实设备，请重新扫描"}
        try:
            current = _json_request(str(device["endpoint"]) + "/api/status")
            merged = self._merge_state(device, current)
            with self._lock:
                self._registry[device_id] = merged
                self._save()
            return {"success": True, "status": current, "device": merged}
        except Exception as exc:
            offline = self._merge_state(device, {"online": False})
            with self._lock:
                self._registry[device_id] = offline
                self._save()
            return {"success": False, "online": False, "error": "设备状态不可达", "detail": type(exc).__name__, "device": offline}

    @staticmethod
    def _merge_state(device: dict, state: dict) -> dict:
        enabled = _bool(state.get("led_enabled", device.get("isOn")), False)
        color = str(state.get("led_color", device.get("mode", "red"))).lower()
        if color not in _COLORS:
            color = "red"
        result = dict(device)
        result.update({"status": "online" if state.get("online", True) is not False else "offline",
                       "isOn": enabled, "primaryValue": 100 if enabled else 0, "mode": color})
        return result

    def control(self, device_id: str, action: str, params: dict | None = None) -> dict:
        device = self.get(device_id)
        if not device:
            return {"success": False, "error": "自定义设备不存在"}
        params = dict(params or {})
        action = str(action or "toggle")
        if action in {"query", "status"}:
            return self.status(device_id)
        if action in {"on", "off", "toggle"}:
            enabled = action == "on" if action != "toggle" else _bool(params.get("isOn", params.get("enabled")), not bool(device.get("isOn")))
        elif action in {"set_color", "color"}:
            enabled = bool(device.get("isOn"))
        else:
            return {"success": False, "error": "LED 适配器不支持该动作"}
        color = str(params.get("color", params.get("led_color", device.get("mode", "red")))).lower()
        if color not in _COLORS:
            return {"success": False, "error": "颜色必须是 red、green 或 blue"}
        if device.get("transport") != "http":
            return {"success": False, "error": "设备记录不是经在线校验的真实设备，请重新扫描"}
        try:
            query = urlencode({"led": "1" if enabled else "0", "color": color})
            result = _json_request(str(device["endpoint"]) + "/api/led?" + query)
            merged = self._merge_state(device, result)
            with self._lock:
                self._registry[device_id] = merged
                self._save()
            return {"success": True, "device": merged, "transport": device.get("transport"), "result": result}
        except Exception as exc:
            return {"success": False, "error": "LED 控制请求失败", "detail": type(exc).__name__}
