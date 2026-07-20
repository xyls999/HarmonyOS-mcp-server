"""Small compatibility adapter for field-package commands missing in old bridges."""

from __future__ import annotations

import importlib


def set_living_light_auto(enabled: bool) -> dict:
    """Send the field package's ``LIGHT AUTO`` command without changing light state.

    The older D6 hardware bridge exposes ``living_text`` internally but does not
    expose an ``auto`` action through ``hw_control``.  This adapter keeps the
    protocol mapping in the gateway layer and makes disabling the gateway rule
    fail closed (it never sends an unrelated ON/OFF command).
    """
    if not enabled:
        return {"success": True, "data": {"mode": "manual", "gateway_enabled": False}, "error": None}
    try:
        bridge = importlib.import_module("hardware_bridge")
        command = getattr(bridge, "living_text", None)
        if not callable(command):
            return {"success": False, "data": {}, "error": "现场桥接未暴露 living_text"}
        config = getattr(bridge, "_CONFIG", {})
        timeout = float(getattr(bridge, "_TIMEOUT", 3.0))
        result = command(config, "light", "auto", timeout)
        return {"success": True, "data": {"mode": "auto", "gateway_enabled": True, "reply": result}, "error": None}
    except Exception as exc:
        return {"success": False, "data": {}, "error": str(exc)}
