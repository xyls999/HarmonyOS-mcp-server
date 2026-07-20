"""可扩展设备与多协议安全传输契约。

这个模块是接入新设备时唯一需要遵守的最小接口。设备适配器负责把厂商协议
翻译成统一的 ``query/toggle/control``，协议网关负责选择 HTTP(S)、WebSocket、
MQTT 或 CoAP 通道；业务层不直接依赖某个厂商 SDK。
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit


PROTOCOL_PROFILES: dict[str, dict[str, Any]] = {
    "http": {
        "label": "局域网 HTTP",
        "ports": [80, 8080],
        "security": "仅允许内网；主控写权限、审计日志；不直接暴露公网",
        "use": "兼容旧设备和简单局域网设备",
        "encrypted": False,
    },
    "https": {
        "label": "HTTPS",
        "ports": [8443],
        "security": "TLS 1.3 + SM2 签名 + SM4 信封 + SM3 完整性",
        "use": "远程管理、批量查询、跨网段安全调用",
        "encrypted": True,
    },
    "websocket": {
        "label": "WebSocket",
        "ports": [8080],
        "security": "升级后使用 SM4 加密帧、SM3 完整性校验和令牌认证",
        "use": "实时状态、助手事件、报警推送",
        "encrypted": True,
    },
    "mqtt": {
        "label": "MQTT 3.1.1",
        "ports": [1883, 8883],
        "security": "主控 ACL + SM4 加密负载 + SM3 标签；公网使用 TLS 端口",
        "use": "传感器上报、设备控制、场景事件",
        "encrypted": True,
    },
    "coap": {
        "label": "CoAP",
        "ports": [5683, 5684],
        "security": "轻量 SM4 加密负载 + SM3 标签；低功耗设备使用",
        "use": "低功耗传感器和小数据查询",
        "encrypted": True,
    },
}

_ACTION_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,48}$")


@dataclass(frozen=True)
class Capability:
    action: str
    description: str
    params: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ACTION_RE.fullmatch(self.action):
            raise ValueError("能力 action 只能包含小写字母、数字、点、下划线和短横线")


class DeviceAdapter(Protocol):
    adapter_id: str
    protocol: str

    def capabilities(self) -> list[Capability]: ...

    def query(self, device_id: str) -> dict[str, Any]: ...

    def invoke(self, device_id: str, action: str, params: dict[str, Any]) -> dict[str, Any]: ...


def validate_private_endpoint(endpoint: str) -> str:
    """校验设备 endpoint，拒绝公网地址、凭据和任意协议。"""
    parsed = urlsplit(str(endpoint or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("设备 endpoint 必须是 http(s) 地址")
    if parsed.username or parsed.password:
        raise ValueError("endpoint 不允许携带用户名或密码")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("endpoint 必须使用内网 IPv4 地址") from exc
    if address.version != 4 or not (address.is_private or address.is_loopback):
        raise ValueError("endpoint 只允许内网 IPv4 地址")
    return endpoint.rstrip("/")


class AdapterRegistry:
    """设备适配器注册表：能力白名单和协议描述可被 AI/MCP 读取。"""

    def __init__(self) -> None:
        self._adapters: dict[str, DeviceAdapter] = {}

    def register(self, adapter: DeviceAdapter) -> None:
        adapter_id = str(adapter.adapter_id).strip()
        protocol = str(adapter.protocol).lower().strip()
        if not adapter_id or adapter_id in self._adapters:
            raise ValueError("adapter_id 为空或已注册")
        if protocol not in PROTOCOL_PROFILES:
            raise ValueError(f"不支持的传输协议: {protocol}")
        capabilities = adapter.capabilities()
        if not capabilities:
            raise ValueError("适配器至少需要一个能力")
        if len({cap.action for cap in capabilities}) != len(capabilities):
            raise ValueError("能力 action 不能重复")
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> DeviceAdapter | None:
        return self._adapters.get(adapter_id)

    def invoke(self, adapter_id: str, device_id: str, action: str,
               params: dict[str, Any] | None = None) -> dict[str, Any]:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return {"success": False, "error": "适配器不存在"}
        allowed = {cap.action for cap in adapter.capabilities()}
        if action not in allowed:
            return {"success": False, "error": "动作不在适配器能力白名单"}
        return adapter.invoke(device_id, action, dict(params or {}))

    def catalog(self) -> dict[str, Any]:
        return {
            "protocols": PROTOCOL_PROFILES,
            "adapters": [
                {
                    "id": adapter_id,
                    "protocol": adapter.protocol,
                    "capabilities": [
                        {"action": cap.action, "description": cap.description, "params": cap.params}
                        for cap in adapter.capabilities()
                    ],
                }
                for adapter_id, adapter in sorted(self._adapters.items())
            ],
        }


def secure_transport_requirements(protocol: str, remote: bool = False) -> dict[str, Any]:
    """给前端/评审展示的安全决策，不返回任何密钥。"""
    key = str(protocol).lower().strip()
    if key not in PROTOCOL_PROFILES:
        raise ValueError("未知协议")
    profile = dict(PROTOCOL_PROFILES[key])
    if remote and key == "http":
        return {"allowed": False, "reason": "HTTP 仅限本地内网，远程必须切换 HTTPS"}
    return {"allowed": True, "protocol": key, "security": profile["security"],
            "encrypted": profile["encrypted"], "ports": profile["ports"]}
