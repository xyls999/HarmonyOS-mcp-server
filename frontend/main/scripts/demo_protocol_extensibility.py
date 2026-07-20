#!/usr/bin/env python3
"""智慧家居“可扩展接入 + 多协议安全”现场演示。

默认只读；加 ``--discover-led`` 才执行设备发现，加 ``--control-led`` 才执行一次
蓝色切换并恢复原颜色。输出会删除 endpoint、board_ip、令牌等内网敏感字段。
"""
from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.request import Request, urlopen


SENSITIVE_KEYS = {"endpoint", "board_ip", "ip", "token", "api_key", "authorization", "source"}


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items() if key.lower() not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def request(base: str, path: str, method: str = "GET", body: dict | None = None) -> Any:
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(base.rstrip("/") + path, data=payload, method=method,
                  headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def section(title: str, value: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(scrub(value), ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="演示设备扩展与多协议安全能力")
    parser.add_argument("--base", default="http://127.0.0.1:8080", help="A9 主控 HTTP 基址")
    parser.add_argument("--scan-device", "--discover-led", dest="scan_device", action="store_true", help="执行一次设备类型扫描")
    parser.add_argument("--control-device", "--control-led", dest="control_device", action="store_true", help="切换设备颜色后恢复")
    args = parser.parse_args()

    health = request(args.base, "/health")
    catalog = request(args.base, "/api/protocols/catalog")
    section("主控健康状态", health)
    section("主流协议与安全能力", catalog)

    protocols = catalog.get("protocols", {}) if isinstance(catalog, dict) else {}
    required = {"http", "https", "websocket", "mqtt", "coap"}
    missing = sorted(required.difference(protocols))
    if missing:
        raise SystemExit("协议目录缺失: " + ", ".join(missing))

    if args.scan_device or args.control_device:
        discovered = request(args.base, "/api/custom/scan", "POST",
                             {"deviceType": "light", "room": "自定义设备"})
        section("定向发现并自动注册", discovered)

    devices = request(args.base, "/api/devices")
    custom = [item for item in devices if str(item.get("id", "")).startswith("custom_led_")]
    section("统一设备模型中的自定义设备", custom)
    if not custom:
        print("\n提示：使用 --discover-led 完成现场设备发现。")
        return 0

    if args.control_device:
        device = custom[0]
        original_color = str(device.get("mode", "red"))
        device_id = str(device["id"])
        changed = request(args.base, f"/api/devices/{device_id}/control", "POST",
                          {"action": "set_color", "params": {"color": "blue"}})
        restored = request(args.base, f"/api/devices/{device_id}/control", "POST",
                           {"action": "set_color", "params": {"color": original_color}})
        section("统一控制接口：切换蓝色", changed)
        section("恢复演示前颜色", restored)
        if not changed.get("success") or not restored.get("success"):
            raise SystemExit("控制演示失败")

    print("\n验收通过：新设备无需改业务页面即可注册；五类协议和安全策略均可由接口读取。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
