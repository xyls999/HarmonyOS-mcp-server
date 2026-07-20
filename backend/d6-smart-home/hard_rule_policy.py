"""小而确定的现场规则边界。

这里不做语义推理，也不读取 RAG。它只负责把现场协议字段归一化，并声明
当前允许运行的硬规则，供网关和测试共同使用。
"""

from __future__ import annotations

from typing import Any, Mapping


ALLOWED_AUTOMATION_RULES = {
    "kitchen_alarm",
    "high_temperature_cool",
    "high_humidity_dry",
}
ALLOWED_SECURITY_RULES = {
    "door_event",
    "door_repeated_request",
    "door_password_failure",
}
RAG_ENABLED = False


class DisabledRAG:
    def get_context(self, _query: str) -> str:
        return ""

    def get_stats(self) -> dict[str, Any]:
        return {"enabled": False, "total": 0, "language": "zh-CN"}

    def search(self, _query: str, n: int = 5) -> list[dict[str, Any]]:
        return []


class DisabledKnowledge:
    def search(self, _query: str, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def get_stats(self) -> dict[str, Any]:
        return {"enabled": False, "total": 0, "families": 0, "sources": 0, "language": "zh-CN"}


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_living_environment(payload: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Normalize the field TEMP QUERY response (``humi`` is the field key)."""
    data = payload if isinstance(payload, Mapping) else {}
    temp = _number(data.get("temp"))
    humidity = _number(data.get("humidity", data.get("humi")))
    if temp is None or humidity is None:
        return None
    if not -20 <= temp <= 60 or not 0 < humidity <= 100:
        return None
    return {"temp": temp, "humidity": humidity}


def normalize_kitchen_state(payload: Mapping[str, Any] | None) -> dict[str, int]:
    """Keep the edge-computed alarm bits; derive only omitted compatibility fields."""
    data = payload if isinstance(payload, Mapping) else {}
    smoke_level_value = _number(data.get("smoke_level"))
    # A missing field is an unavailable sensor sample, not GP03 low level.
    # Only an explicit field value of 0 means smoke alarm.
    smoke_level = int(smoke_level_value) if smoke_level_value is not None else 1
    smoke_alarm = int(_number(data.get("smoke_alarm"), 1 if smoke_level_value == 0 else 0) or 0)
    thermal_mv = int(_number(data.get("thermal_mv"), 0) or 0)
    if "temp_alarm" in data:
        temp_alarm = int(_number(data.get("temp_alarm"), 0) or 0)
    else:
        # Compatibility fallback for an older central parser. The field
        # firmware remains authoritative whenever temp_alarm is present.
        temp_alarm = int(thermal_mv <= 1400 and thermal_mv > 0)
    alarm = int(_number(data.get("alarm"), 1 if smoke_alarm or temp_alarm else 0) or 0)
    brightness = max(0, min(100, int(_number(data.get("brightness"), 0) or 0)))
    return {
        "smoke_level": smoke_level,
        "smoke_alarm": int(bool(smoke_alarm)),
        "temp_alarm": int(bool(temp_alarm)),
        "alarm": int(bool(alarm or smoke_alarm or temp_alarm)),
        "thermal_mv": thermal_mv,
        "brightness": brightness,
    }
