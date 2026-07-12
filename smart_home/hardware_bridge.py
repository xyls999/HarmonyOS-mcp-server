#!/usr/bin/env python3
"""
硬件控制桥接模块 v2 · 纯标准库实现
将智慧家居设备ID映射到 central_controller.py 的真实硬件调用

v2 变更:
  - 新增 hw_living_status / hw_kitchen_status / hw_bathroom_status / hw_bedroom_status
  - 每次调用只尝试一次，失败不重试
  - 返回 {success, data, error}
  - 设备离线时静默返回失败
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

# 导入 central_controller
_CONNECT_DIR = Path(__file__).resolve().parent / "connect"
if str(_CONNECT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONNECT_DIR))

try:
    from central_controller import (
        load_config, device_endpoint,
        living_door, living_text,
        kitchen_status, kitchen_set_light,
        bathroom_status, bathroom_set_light, bathroom_set_fan,
        bedroom_status, bedroom_set_light, bedroom_set_curtain, bedroom_curtain_action,
        all_status,
    )
    _CONFIG = load_config(str(_CONNECT_DIR / "devices.json"))
    _HW_AVAILABLE = True
except Exception as _e:
    _HW_AVAILABLE = False
    _CONFIG = {}
    living_door = living_text = kitchen_status = kitchen_set_light = None
    bathroom_status = bathroom_set_light = bathroom_set_fan = None
    bedroom_status = bedroom_set_light = bedroom_set_curtain = bedroom_curtain_action = None
    all_status = None

_TIMEOUT = 3.0

# 设备中文名
_DEVICE_NAMES = {
    "light_01": "客厅主灯", "light_02": "厨房灯", "light_03": "卧室灯",
    "light_04": "卫生间灯", "light_05": "客厅氛围灯",
    "ac_01": "客厅空调", "fan_01": "客厅吊扇", "fan_02": "换气扇",
    "curtain_01": "智能窗帘", "door_01": "客厅大门", "alarm_01": "蜂鸣警报",
    "camera_01": "客厅摄像头", "exhaust_01": "抽风机",
    "nfc_01": "NFC门禁", "voice_01": "语音中控", "radar_01": "毫米波雷达",
}


def _dev_name(device_id):
    return _DEVICE_NAMES.get(device_id, device_id)


def _hw_ok(data=None):
    return {"success": True, "data": data or {}, "error": None}


def _hw_fail(error):
    return {"success": False, "data": {}, "error": str(error)}


# ===== 区域状态查询 =====
def hw_living_status(service="temp"):
    """查询客厅设备状态
    service: temp/light/ac/door/beep/event
    """
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")
    try:
        if service == "door":
            r = living_door(_CONFIG, "query", _TIMEOUT)
            return _hw_ok(r)
        else:
            r = living_text(_CONFIG, service, "query", _TIMEOUT)
            return _hw_ok(r)
    except Exception as e:
        return _hw_fail(e)


def hw_kitchen_status():
    """查询厨房完整状态"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")
    try:
        r = kitchen_status(_CONFIG, _TIMEOUT)
        return _hw_ok(r)
    except Exception as e:
        return _hw_fail(e)


def hw_bathroom_status():
    """查询卫生间完整状态"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")
    try:
        r = bathroom_status(_CONFIG, _TIMEOUT)
        return _hw_ok(r)
    except Exception as e:
        return _hw_fail(e)


def hw_bedroom_status():
    """查询卧室完整状态"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")
    try:
        r = bedroom_status(_CONFIG, _TIMEOUT)
        return _hw_ok(r)
    except Exception as e:
        return _hw_fail(e)


# ===== 开关设备 =====
def hw_toggle(device_id, is_on):
    """开关设备，返回 {success, data, error}"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")

    try:
        if device_id == "light_01" or device_id == "light_05":
            action = "on" if is_on else "off"
            r = living_text(_CONFIG, "light", action, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "ac_01":
            action = "on" if is_on else "off"
            r = living_text(_CONFIG, "ac", action, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "door_01":
            action = "open" if is_on else "close"
            r = living_door(_CONFIG, action, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "alarm_01":
            action = "alarm" if is_on else "off"
            r = living_text(_CONFIG, "beep", action, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "light_02":
            brightness = 100 if is_on else 0
            r = kitchen_set_light(_CONFIG, brightness, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "light_04":
            brightness = 100 if is_on else 0
            r = bathroom_set_light(_CONFIG, brightness, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "fan_02":
            if is_on:
                r = bathroom_set_fan(_CONFIG, "forward", 100, _TIMEOUT)
            else:
                r = bathroom_set_fan(_CONFIG, "stop", 0, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "light_03":
            brightness = 100 if is_on else 0
            r = bedroom_set_light(_CONFIG, brightness, _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "curtain_01":
            position = 100 if is_on else 0
            r = bedroom_set_curtain(_CONFIG, position, _TIMEOUT)
            return _hw_ok(r)

        else:
            return _hw_ok({"note": "虚拟设备，无硬件控制"})

    except Exception as e:
        return _hw_fail(e)


# ===== 参数控制 =====
def hw_control(device_id, action, params):
    """控制设备参数，返回 {success, data, error}"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")

    try:
        if device_id == "ac_01":
            r = living_text(_CONFIG, "ac", "on", _TIMEOUT)
            return _hw_ok(r)

        elif device_id == "light_01" or device_id == "light_05":
            if action == "set_brightness":
                val = params.get("value", 100)
                act = "on" if val > 0 else "off"
                r = living_text(_CONFIG, "light", act, _TIMEOUT)
                return _hw_ok(r)
            else:
                return _hw_ok({"note": "客厅灯仅支持开关"})

        elif device_id == "light_02":
            if action == "set_brightness":
                val = params.get("value", 100)
                r = kitchen_set_light(_CONFIG, int(val), _TIMEOUT)
                return _hw_ok(r)
            else:
                return _hw_ok({"note": "厨房灯仅支持亮度"})

        elif device_id == "light_04":
            if action == "set_brightness":
                val = params.get("value", 100)
                r = bathroom_set_light(_CONFIG, int(val), _TIMEOUT)
                return _hw_ok(r)
            else:
                return _hw_ok({"note": "卫生间灯仅支持亮度"})

        elif device_id == "light_03":
            if action == "set_brightness":
                val = params.get("value", 100)
                r = bedroom_set_light(_CONFIG, int(val), _TIMEOUT)
                return _hw_ok(r)
            else:
                return _hw_ok({"note": "卧室灯仅支持亮度"})

        elif device_id == "fan_02":
            if action == "set_speed":
                val = params.get("value", 100)
                if int(val) > 0:
                    r = bathroom_set_fan(_CONFIG, "forward", int(val), _TIMEOUT)
                else:
                    r = bathroom_set_fan(_CONFIG, "stop", 0, _TIMEOUT)
                return _hw_ok(r)
            else:
                return _hw_ok({"note": "换气扇仅支持风速"})

        elif device_id == "curtain_01":
            if action == "set_position":
                val = params.get("value", 100)
                r = bedroom_set_curtain(_CONFIG, int(val), _TIMEOUT)
                return _hw_ok(r)
            elif action == "stop":
                r = bedroom_curtain_action(_CONFIG, "stop", _TIMEOUT)
                return _hw_ok(r)
            elif action == "home":
                r = bedroom_curtain_action(_CONFIG, "home", _TIMEOUT)
                return _hw_ok(r)
            else:
                return _hw_ok({"note": "窗帘仅支持位置/停止/回零"})

        else:
            return _hw_ok({"note": "无硬件控制映射"})

    except Exception as e:
        return _hw_fail(e)


# ===== 传感器读取 =====
def hw_sensor_read(sensor_id):
    """读取传感器数据，返回 {success, data, error}"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")

    try:
        if sensor_id == "temp_01" or sensor_id == "humid_01":
            r = living_text(_CONFIG, "temp", "query", _TIMEOUT)
            reply = r.get("reply", "") if isinstance(r, dict) else str(r)
            data = {"raw": reply}
            for part in reply.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k == "temp":
                        data["temp"] = float(v)
                    elif k == "humi":
                        data["humidity"] = float(v)
            return _hw_ok(data)

        elif sensor_id in ("smoke_01", "heat_01", "air_01"):
            r = kitchen_status(_CONFIG, _TIMEOUT)
            data = {}
            if sensor_id == "smoke_01":
                data["smoke_alarm"] = r.get("smoke_alarm", 0)
                data["smoke_level"] = r.get("smoke_level", 0)
            elif sensor_id == "heat_01":
                data["temp_alarm"] = r.get("temp_alarm", 0)
                data["thermal_mv"] = r.get("thermal_mv", 0)
            elif sensor_id == "air_01":
                data["smoke_level"] = r.get("smoke_level", 0)
                data["alarm"] = r.get("alarm", 0)
            return _hw_ok(data)

        else:
            return _hw_ok({"note": "无硬件传感器映射"})

    except Exception as e:
        return _hw_fail(e)


# ===== 场景批量执行 =====
def hw_scene_execute(actions):
    """执行场景动作列表
    actions: [(device_id, is_on, primary_value), ...]
    返回: [{"device_id": str, "success": bool, "error": str|None}, ...]
    """
    results = []
    for device_id, is_on, pv in actions:
        r = hw_toggle(device_id, is_on)
        results.append({
            "device_id": device_id,
            "success": r["success"],
            "error": r["error"],
        })
    return results


# ===== 查询所有设备状态 =====
def hw_all_status():
    """查询所有硬件设备状态"""
    if not _HW_AVAILABLE:
        return _hw_fail("硬件模块未加载")
    try:
        r = all_status(_CONFIG, _TIMEOUT)
        return _hw_ok(r)
    except Exception as e:
        return _hw_fail(e)
