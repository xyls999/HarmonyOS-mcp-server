"""Build one atomic, freshness-aware automation input snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _freshness(observed_at: Any, now: datetime, ttl: float) -> str:
    observed = _parse_time(observed_at)
    if observed is None:
        return "unknown"
    if (now - observed).total_seconds() <= ttl:
        return "fresh"
    return "stale"


def build_snapshot(
    device_status: Mapping[str, Any] | None,
    sensor_status: Mapping[str, Any] | None,
    weather: Mapping[str, Any] | None,
    now: datetime | None = None,
    *,
    device_ttl_seconds: float = 30.0,
    sensor_ttl_seconds: float = 300.0,
) -> dict[str, Any]:
    captured = now or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    devices: dict[str, Any] = {}
    sensors: dict[str, Any] = {}
    freshness: dict[str, str] = {}
    for key, value in (device_status or {}).items():
        item = dict(value) if isinstance(value, Mapping) else {"value": value}
        status = _freshness(item.get("observed_at") or item.get("updated_at"), captured, device_ttl_seconds)
        freshness[str(key)] = status
        if status != "stale":
            devices[str(key)] = item
    for key, value in (sensor_status or {}).items():
        item = dict(value) if isinstance(value, Mapping) else {"value": value}
        status = _freshness(item.get("observed_at") or item.get("updated_at"), captured, sensor_ttl_seconds)
        freshness[str(key)] = status
        if status != "stale":
            item["freshness"] = status
            if str(key) == "radar_01":
                # The bathroom controller exposes the real millimetre-wave bit
                # as radar_target_present.  An offline controller must remain
                # unknown; treating its zero-filled payload as "nobody home"
                # would allow a dangerous false shutdown.
                if item.get("online") is True and "radar_target_present" in item:
                    item["present"] = bool(item.get("radar_target_present"))
                elif item.get("online") is not True:
                    item.pop("present", None)
            sensors[str(key)] = item
    result = {
        "version": captured.isoformat(),
        "capturedAt": captured.isoformat(),
        "devices": devices,
        "sensors": sensors,
        "weather": dict(weather or {}),
        "freshness": freshness,
    }
    light = sensors.get("light_s_01")
    if isinstance(light, dict) and light.get("online") is True and isinstance(light.get("value"), (int, float)):
        result["light_sensor"] = {
            "sensorId": "light_s_01",
            "value": float(light["value"]),
            "freshness": light.get("freshness", "unknown"),
        }
    return result
