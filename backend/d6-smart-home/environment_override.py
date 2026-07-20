"""主机手动温湿度输入的边界校验。

输入会走原有温湿度联动和阈值判断，不改变下游设备逻辑。
"""

from __future__ import annotations

from typing import Any, Mapping


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是数字") from exc


def normalize_override(payload: Mapping[str, Any] | None) -> dict[str, float | bool]:
    data = payload if isinstance(payload, Mapping) else {}
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled 必须是布尔值")
    temp = _number(data.get("temp"), "temp")
    humidity = _number(data.get("humidity", data.get("humi")), "humidity")
    if not -20 <= temp <= 60:
        raise ValueError("温度范围必须为 -20 到 60℃")
    if not 0 < humidity <= 100:
        raise ValueError("湿度范围必须为 0 到 100%")
    return {"enabled": enabled, "temp": temp, "humidity": humidity}
