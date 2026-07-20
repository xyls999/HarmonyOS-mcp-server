#!/usr/bin/env python3
"""
AI 智能意图引擎 v2 · 纯标准库实现
在 /data/A9/smart_home/ 运行，被 gateway_v6.py 导入

v2 升级:
  1. IntentMatcher    - 快速正则意图匹配 (0延迟)
  2. FuzzyReasoner    - 模糊意图推理 (上下文感知)
  3. AnomalyDetector  - 异常模式识别 (后台线程)
  4. HabitLearner     - 习惯学习与主动推荐
  5. DeviceCapability - 设备能力自动描述
  6. DeviceRegistry   - 设备模板化注册 (新设备零代码嵌入)
  7. ConversationMemory - 对话上下文记忆 (多轮对话指代消解)
  8. LinkageEngine    - 设备联动策略引擎 (自动推理设备间关系)
  9. EmotionAnalyzer  - 情感感知 (识别用户情绪调整回复)
 10. EnergyAdvisor    - 节能优化顾问 (基于用电模式建议)
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


# ═══════════════════════════════════════════════════════════════
# 设备能力描述
# ═══════════════════════════════════════════════════════════════

# 设备能力定义: device_id -> [{action, params_schema, desc}]
DEVICE_CAPABILITIES = {
    "light_01": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关客厅主灯"},
        {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度(实际只支持开/关)"},
    ],
    "ac_01": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关客厅空调"},
        {"action": "set_temp", "params": {"value": "16-30"}, "desc": "设置温度(16-30°C)"},
        {"action": "set_mode", "params": {"mode": "cool|heat|dry|fan"}, "desc": "设置模式(制冷/制热/除湿/送风)"},
        {"action": "set_fan", "params": {"mode": "auto|low|mid|high"}, "desc": "设置风速"},
        {"action": "set_swing", "params": {"mode": "on|off"}, "desc": "设置摆风"},
    ],
    "door_01": [
        {"action": "toggle", "params": {"isOn": "bool", "doorPassword": "str"}, "desc": "开关客厅大门(需密码)"},
    ],
    "alarm_01": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关蜂鸣警报"},
    ],
    "light_02": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关厨房灯"},
        {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度"},
    ],
    "light_04": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关卫生间灯"},
        {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度"},
    ],
    "fan_02": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关换气扇"},
        {"action": "set_speed", "params": {"value": "0-100"}, "desc": "设置风速"},
    ],
    "light_03": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关卧室灯"},
        {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度(建议只用开/关,有频闪)"},
    ],
    "curtain_01": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关智能窗帘"},
        {"action": "set_position", "params": {"value": "0-100"}, "desc": "设置位置(0=全关,100=全开)"},
        {"action": "stop", "params": {}, "desc": "紧急停止"},
    ],
}

# 设备中文名映射
DEVICE_NAMES = {
    "light_01": "客厅主灯", "light_02": "厨房灯", "light_03": "卧室灯",
    "light_04": "卫生间灯",
    "ac_01": "客厅空调", "fan_02": "换气扇",
    "curtain_01": "智能窗帘", "door_01": "客厅大门", "alarm_01": "蜂鸣警报",
}

# 房间→设备映射
ROOM_DEVICES = {
    "客厅": ["light_01", "ac_01", "door_01", "alarm_01"],
    "厨房": ["light_02"],
    "卫生间": ["light_04", "fan_02"],
    "卧室": ["light_03", "curtain_01"],
}

# 设备别名(自然语言→device_id)
DEVICE_ALIASES = {
    "客厅灯": "light_01", "客厅主灯": "light_01", "主灯": "light_01",
    "厨房灯": "light_02",
    "卧室灯": "light_03",
    "卫生间灯": "light_04", "浴室灯": "light_04",
    "空调": "ac_01", "客厅空调": "ac_01",
    "窗帘": "curtain_01", "智能窗帘": "curtain_01", "卧室窗帘": "curtain_01",
    "门": "door_01", "大门": "door_01", "客厅大门": "door_01",
    "警报": "alarm_01", "蜂鸣器": "alarm_01", "警报器": "alarm_01",
    "换气扇": "fan_02", "排气扇": "fan_02",
    "灯": None,  # 需要上下文判断
}


def get_device_capabilities(device_defs: list[dict] = None) -> list[dict]:
    """获取所有设备能力描述

    Args:
        device_defs: 设备定义列表(从 gateway_v6 传入，避免循环导入)
    """
    if device_defs is None:
        device_defs = [
            {"id": did, "name": DEVICE_NAMES.get(did, did), "type": "unknown", "room": "unknown"}
            for did in DEVICE_CAPABILITIES
        ]
    result = []
    for d in device_defs:
        caps = DEVICE_CAPABILITIES.get(d["id"], [])
        result.append({
            "id": d["id"],
            "name": d.get("name", d["id"]),
            "type": d.get("type", "unknown"),
            "room": d.get("room", "unknown"),
            "capabilities": caps,
        })
    return result


# ═══════════════════════════════════════════════════════════════
# DeviceRegistry - 设备模板化注册系统
# ═══════════════════════════════════════════════════════════════
# 新设备只需按模板填入，即可被AI理解、被意图引擎匹配、被联动引擎发现
# 模板格式:
# {
#     "id": "new_device_01",
#     "name": "新设备名",
#     "type": "light|ac|fan|curtain|door|alarm|sensor|custom",
#     "room": "客厅|厨房|卫生间|卧室",
#     "aliases": ["别名1", "别名2"],
#     "capabilities": [
#         {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关"},
#         {"action": "set_xxx", "params": {"value": "0-100"}, "desc": "设置xxx"},
#     ],
#     "intent_patterns": [  # 可选: 自定义意图匹配正则
#         (r"(开|打开).*(新设备)", "device_toggle", {"isOn": True}),
#         (r"(关|关闭).*(新设备)", "device_toggle", {"isOn": False}),
#     ],
#     "linkage_triggers": [  # 可选: 联动触发条件
#         {"when": "on", "then": [{"device": "light_01", "action": "set_brightness", "params": {"value": 30}}],
#          "desc": "新设备开启时调暗客厅灯"},
#     ],
#     "energy_watts": 50,  # 可选: 功率(瓦), 用于节能计算
# }

# 内置设备模板(已注册的设备)
_BUILTIN_TEMPLATES = [
    {
        "id": "light_01", "name": "客厅主灯", "type": "light", "room": "客厅",
        "aliases": ["客厅灯", "客厅主灯", "主灯"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关客厅主灯"},
            {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度"},
        ],
        "intent_patterns": [
            (r"(开|打开|启动|点亮).*(客厅)?(主)?灯", "device_toggle", {"isOn": True}),
            (r"(关|关闭|关掉|熄灭).*(客厅)?(主)?灯", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [],
        "energy_watts": 12,
    },
    {
        "id": "ac_01", "name": "客厅空调", "type": "ac", "room": "客厅",
        "aliases": ["空调", "客厅空调"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关客厅空调"},
            {"action": "set_temp", "params": {"value": "16-30"}, "desc": "设置温度(16-30°C)"},
            {"action": "set_mode", "params": {"mode": "cool|heat|dry|fan"}, "desc": "设置模式"},
            {"action": "set_fan", "params": {"mode": "auto|low|mid|high"}, "desc": "设置风速"},
            {"action": "set_swing", "params": {"mode": "on|off"}, "desc": "设置摆风"},
        ],
        "intent_patterns": [
            (r"(开|打开|启动).*(空调)", "device_toggle", {"isOn": True}),
            (r"(关|关闭|关掉).*(空调)", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [
            {"when": "on", "then": [{"device": "curtain_01", "action": "set_position", "params": {"value": 30}}],
             "desc": "空调开启时关窗帘保温"},
        ],
        "energy_watts": 1200,
    },
    {
        "id": "door_01", "name": "客厅大门", "type": "door", "room": "客厅",
        "aliases": ["门", "大门", "客厅大门"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool", "doorPassword": "str"}, "desc": "开关门(需密码)"},
        ],
        "intent_patterns": [
            (r"(开门|解锁|把门打开|打开门)", "door", "open"),
            (r"(关门|锁门|锁上|把门关上|关上门)", "door", "close"),
        ],
        "linkage_triggers": [
            {"when": "open", "then": [{"device": "light_01", "action": "toggle", "params": {"isOn": True}}],
             "desc": "开门时自动开灯"},
        ],
        "energy_watts": 5,
    },
    {
        "id": "alarm_01", "name": "蜂鸣警报", "type": "alarm", "room": "客厅",
        "aliases": ["警报", "蜂鸣器", "警报器"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关蜂鸣警报"},
        ],
        "intent_patterns": [],
        "linkage_triggers": [],
        "energy_watts": 10,
    },
    {
        "id": "light_02", "name": "厨房灯", "type": "light", "room": "厨房",
        "aliases": ["厨房灯"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关厨房灯"},
            {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度"},
        ],
        "intent_patterns": [
            (r"(开|打开|启动).*(厨房)?灯", "device_toggle", {"isOn": True}),
            (r"(关|关闭|关掉).*(厨房)?灯", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [],
        "energy_watts": 10,
    },
    {
        "id": "light_04", "name": "卫生间灯", "type": "light", "room": "卫生间",
        "aliases": ["卫生间灯", "浴室灯", "厕所灯"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关卫生间灯"},
            {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度"},
        ],
        "intent_patterns": [
            (r"(开|打开|启动).*(卫生间|浴室|厕所)?灯", "device_toggle", {"isOn": True}),
            (r"(关|关闭|关掉).*(卫生间|浴室|厕所)?灯", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [
            {"when": "on", "then": [{"device": "fan_02", "action": "toggle", "params": {"isOn": True}}],
             "desc": "卫生间灯开启时自动开换气扇"},
        ],
        "energy_watts": 10,
    },
    {
        "id": "fan_02", "name": "换气扇", "type": "fan", "room": "卫生间",
        "aliases": ["换气扇", "排气扇", "风扇"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关换气扇"},
            {"action": "set_speed", "params": {"value": "0-100"}, "desc": "设置风速"},
        ],
        "intent_patterns": [
            (r"(开|打开|启动).*(换气扇|排气扇|风扇)", "device_toggle", {"isOn": True}),
            (r"(关|关闭|关掉).*(换气扇|排气扇|风扇)", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [],
        "energy_watts": 30,
    },
    {
        "id": "light_03", "name": "卧室灯", "type": "light", "room": "卧室",
        "aliases": ["卧室灯"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关卧室灯"},
            {"action": "set_brightness", "params": {"value": "0-100"}, "desc": "设置亮度(建议只用开/关,有频闪)"},
        ],
        "intent_patterns": [
            (r"(开|打开|启动).*(卧室)?灯", "device_toggle", {"isOn": True}),
            (r"(关|关闭|关掉).*(卧室)?灯", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [],
        "energy_watts": 10,
    },
    {
        "id": "curtain_01", "name": "智能窗帘", "type": "curtain", "room": "卧室",
        "aliases": ["窗帘", "智能窗帘", "卧室窗帘"],
        "capabilities": [
            {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关智能窗帘"},
            {"action": "set_position", "params": {"value": "0-100"}, "desc": "设置位置(0=全关,100=全开)"},
            {"action": "stop", "params": {}, "desc": "紧急停止"},
        ],
        "intent_patterns": [
            (r"(开|打开|拉开).*(窗帘)", "device_toggle", {"isOn": True}),
            (r"(关|关闭|拉上|合上).*(窗帘)", "device_toggle", {"isOn": False}),
        ],
        "linkage_triggers": [],
        "energy_watts": 15,
    },
]


class DeviceRegistry:
    """设备模板化注册中心 — 新设备按模板填入即可被AI理解

    功能:
    1. 注册新设备模板 → 自动更新 DEVICE_CAPABILITIES / DEVICE_NAMES / DEVICE_ALIASES / ROOM_DEVICES
    2. 自动生成意图匹配规则 → 新设备立刻可被自然语言控制
    3. 自动注册联动规则 → 新设备自动参与联动策略
    4. 持久化到DB → 重启后自动恢复
    5. 查询/删除/更新 → 完整的设备生命周期管理
    """

    def __init__(self, db_path: str | Path = None, log_fn: Callable = None):
        self._db_path = str(db_path) if db_path else None
        self._log = log_fn or (lambda m: None)
        self._templates: dict[str, dict] = {}  # id -> template
        self._init_db()
        self._load_builtin()
        self._load_from_db()

    def _init_db(self):
        """初始化设备注册表"""
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS device_registry (
                device_id TEXT PRIMARY KEY,
                template_json TEXT NOT NULL,
                registered_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""")
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"[REGISTRY] DB初始化失败: {e}")

    def _load_builtin(self):
        """加载内置设备模板"""
        for tpl in _BUILTIN_TEMPLATES:
            self._apply_template(tpl, persist=False)
        self._log(f"[REGISTRY] 已加载 {len(_BUILTIN_TEMPLATES)} 个内置设备模板")

    def _load_from_db(self):
        """从DB加载自定义设备模板"""
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute("SELECT device_id, template_json FROM device_registry").fetchall()
            conn.close()
            count = 0
            for device_id, tpl_json in rows:
                if device_id not in self._templates:
                    tpl = json.loads(tpl_json)
                    self._apply_template(tpl, persist=False)
                    count += 1
            if count:
                self._log(f"[REGISTRY] 从DB加载 {count} 个自定义设备")
        except Exception as e:
            self._log(f"[REGISTRY] DB加载失败: {e}")

    def _apply_template(self, tpl: dict, persist: bool = True):
        """应用设备模板 — 更新全局映射表"""
        dev_id = tpl["id"]
        self._templates[dev_id] = tpl

        # 1. 更新 DEVICE_CAPABILITIES
        caps = tpl.get("capabilities", [])
        if caps:
            DEVICE_CAPABILITIES[dev_id] = caps

        # 2. 更新 DEVICE_NAMES
        name = tpl.get("name", dev_id)
        DEVICE_NAMES[dev_id] = name

        # 3. 更新 DEVICE_ALIASES
        for alias in tpl.get("aliases", []):
            DEVICE_ALIASES[alias] = dev_id

        # 4. 更新 ROOM_DEVICES
        room = tpl.get("room", "")
        if room:
            if room not in ROOM_DEVICES:
                ROOM_DEVICES[room] = []
            if dev_id not in ROOM_DEVICES[room]:
                ROOM_DEVICES[room].append(dev_id)

        # 5. 持久化到DB
        if persist and self._db_path:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT OR REPLACE INTO device_registry(device_id, template_json, updated_at) VALUES(?,?,datetime('now'))",
                    (dev_id, json.dumps(tpl, ensure_ascii=False))
                )
                conn.commit()
                conn.close()
            except Exception as e:
                self._log(f"[REGISTRY] 持久化失败: {e}")

    def register(self, template: dict) -> dict:
        """注册新设备

        Args:
            template: 设备模板，格式见模块文档

        Returns:
            {"success": True, "device_id": ..., "auto_rules": [...]}
        """
        # 校验必填字段
        required = ["id", "name", "type", "room", "capabilities"]
        for field in required:
            if field not in template:
                return {"success": False, "error": f"缺少必填字段: {field}"}

        dev_id = template["id"]
        if dev_id in self._templates and dev_id not in [t["id"] for t in _BUILTIN_TEMPLATES]:
            self._log(f"[REGISTRY] 更新设备: {dev_id}")
        else:
            self._log(f"[REGISTRY] 注册新设备: {dev_id} ({template['name']})")

        # 自动补全 aliases (如果没提供)
        if "aliases" not in template:
            template["aliases"] = [template["name"]]

        # 自动生成意图匹配规则 (如果没提供)
        auto_rules = []
        if "intent_patterns" not in template or not template["intent_patterns"]:
            auto_rules = self._auto_generate_intent_patterns(template)
            template["intent_patterns"] = auto_rules

        # 自动生成联动规则 (如果没提供)
        if "linkage_triggers" not in template:
            template["linkage_triggers"] = self._auto_generate_linkage(template)

        # 应用模板
        self._apply_template(template, persist=True)

        return {
            "success": True,
            "device_id": dev_id,
            "name": template["name"],
            "auto_rules": auto_rules,
            "message": f"设备 {template['name']} 已注册，AI可自动识别并控制",
        }

    def _auto_generate_intent_patterns(self, tpl: dict) -> list:
        """根据设备类型自动生成意图匹配正则"""
        dev_id = tpl["id"]
        name = tpl["name"]
        aliases = tpl.get("aliases", [name])
        dev_type = tpl.get("type", "custom")
        patterns = []

        # 构建名称匹配组
        name_group = "|".join(re.escape(a) for a in aliases)

        if dev_type in ("light",):
            patterns = [
                (rf"(开|打开|启动|点亮).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": True}),
                (rf"(关|关闭|关掉|熄灭).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": False}),
            ]
        elif dev_type in ("ac",):
            patterns = [
                (rf"(开|打开|启动).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": True}),
                (rf"(关|关闭|关掉).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": False}),
            ]
        elif dev_type in ("fan",):
            patterns = [
                (rf"(开|打开|启动).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": True}),
                (rf"(关|关闭|关掉).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": False}),
            ]
        elif dev_type in ("curtain",):
            patterns = [
                (rf"(开|打开|拉开).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": True}),
                (rf"(关|关闭|拉上|合上).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": False}),
            ]
        elif dev_type in ("door",):
            patterns = [
                (rf"(开|打开|解锁).*({name_group})", "door", "open"),
                (rf"(关|关闭|锁).*({name_group})", "door", "close"),
            ]
        elif dev_type in ("alarm",):
            patterns = [
                (rf"(开|启动|触发).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": True}),
                (rf"(关|关闭|解除|取消).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": False}),
            ]
        else:
            # 通用模式
            patterns = [
                (rf"(开|打开|启动).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": True}),
                (rf"(关|关闭|关掉).*({name_group})", "device_toggle", {"device_id": dev_id, "isOn": False}),
            ]

        return patterns

    def _auto_generate_linkage(self, tpl: dict) -> list:
        """根据设备类型和房间自动生成联动规则"""
        dev_type = tpl.get("type", "")
        room = tpl.get("room", "")
        linkages = []

        if dev_type == "light" and room == "卫生间":
            linkages.append({
                "when": "on",
                "then": [{"device": "fan_02", "action": "toggle", "params": {"isOn": True}}],
                "desc": f"{tpl['name']}开启时自动开换气扇",
            })
        elif dev_type == "ac":
            linkages.append({
                "when": "on",
                "then": [{"device": "curtain_01", "action": "set_position", "params": {"value": 30}}],
                "desc": f"{tpl['name']}开启时关窗帘保温",
            })

        return linkages

    def unregister(self, device_id: str) -> dict:
        """注销设备"""
        if device_id not in self._templates:
            return {"success": False, "error": f"设备 {device_id} 未注册"}

        # 不允许注销内置设备
        if device_id in [t["id"] for t in _BUILTIN_TEMPLATES]:
            return {"success": False, "error": "内置设备不可注销"}

        tpl = self._templates.pop(device_id)

        # 清理全局映射
        DEVICE_CAPABILITIES.pop(device_id, None)
        DEVICE_NAMES.pop(device_id, None)
        # 清理别名
        for alias in tpl.get("aliases", []):
            DEVICE_ALIASES.pop(alias, None)
        # 清理房间映射
        for room, devs in ROOM_DEVICES.items():
            if device_id in devs:
                devs.remove(device_id)

        # 从DB删除
        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute("DELETE FROM device_registry WHERE device_id=?", (device_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass

        self._log(f"[REGISTRY] 已注销设备: {device_id}")
        return {"success": True, "device_id": device_id}

    def get_template(self, device_id: str) -> dict | None:
        """获取设备模板"""
        return self._templates.get(device_id)

    def list_templates(self) -> list[dict]:
        """列出所有已注册设备模板"""
        return list(self._templates.values())

    def get_intent_patterns(self) -> list[tuple]:
        """获取所有设备的意图匹配规则(包括自动生成的)"""
        patterns = []
        for tpl in self._templates.values():
            for pat in tpl.get("intent_patterns", []):
                if len(pat) == 3:
                    patterns.append(tuple(pat))
        return patterns

    def get_linkage_rules(self) -> list[dict]:
        """获取所有设备的联动规则"""
        rules = []
        for tpl in self._templates.values():
            for lr in tpl.get("linkage_triggers", []):
                lr_copy = dict(lr)
                lr_copy["source_device"] = tpl["id"]
                rules.append(lr_copy)
        return rules

    def get_energy_profile(self) -> dict[str, int]:
        """获取所有设备功率配置"""
        profile = {}
        for tpl in self._templates.values():
            watts = tpl.get("energy_watts", 0)
            if watts:
                profile[tpl["id"]] = watts
        return profile


# ═══════════════════════════════════════════════════════════════
# ConversationMemory - 对话上下文记忆
# ═══════════════════════════════════════════════════════════════

class ConversationMemory:
    """对话上下文记忆 — 多轮对话指代消解 + 话题追踪

    功能:
    1. 记录最近N轮对话，保持上下文连贯
    2. 指代消解: "把它调暗" → 知道"它"是上轮提到的客厅灯
    3. 话题追踪: 知道当前在讨论哪个设备/房间/场景
    4. 省略补全: "再调低一点" → 知道是调低上次的空调温度
    5. 持久化到DB → 重启后恢复最近对话
    """

    # 指代词 → 可能的指代类型
    PRONOUN_MAP = {
        "它": "device", "他": "device", "她": "device",
        "这个": "device", "那个": "device",
        "那个设备": "device", "这个设备": "device",
        "灯": "light", "空调": "ac", "窗帘": "curtain",
        "门": "door", "风扇": "fan", "换气扇": "fan",
    }

    # 省略动作词 → 基于上轮动作推断
    CONTINUATION_PATTERNS = [
        (r"(再)?(调|弄)(高|低|亮|暗|大|小)一点", "adjust"),
        (r"(再)?(开|打开)一点", "increase"),
        (r"(再)?(关|关闭)一点", "decrease"),
        (r"还是(太热|太冷|太亮|太暗|太干|太湿)", "complaint"),
        (r"(不|别)(要|用)了", "cancel"),
        (r"换一个", "switch"),
    ]

    def __init__(self, db_path: str | Path = None, log_fn: Callable = None, max_turns: int = 20):
        self._db_path = str(db_path) if db_path else None
        self._log = log_fn or (lambda m: None)
        self._max_turns = max_turns
        self._history: list[dict] = []  # [{role, content, intent, topic_device, topic_room, timestamp}]
        self._current_topic = {
            "device_id": None, "device_name": None,
            "room": None, "action_type": None, "last_params": None,
        }
        self._init_db()
        self._load_from_db()

    def _init_db(self):
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS conversation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent_json TEXT,
                topic_device TEXT,
                topic_room TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_time ON conversation_memory(created_at)")
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"[MEMORY] DB初始化失败: {e}")

    def _load_from_db(self):
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT role, content, intent_json, topic_device, topic_room "
                "FROM conversation_memory ORDER BY created_at DESC LIMIT ?",
                (self._max_turns,)
            ).fetchall()
            conn.close()
            self._history = []
            for r in reversed(rows):
                entry = {"role": r[0], "content": r[1]}
                if r[2]:
                    try:
                        entry["intent"] = json.loads(r[2])
                    except Exception:
                        pass
                if r[3]:
                    self._current_topic["device_id"] = r[3]
                    self._current_topic["device_name"] = DEVICE_NAMES.get(r[3], r[3])
                if r[4]:
                    self._current_topic["room"] = r[4]
                self._history.append(entry)
        except Exception:
            pass

    def add(self, role: str, content: str, intent: dict = None):
        """添加一轮对话"""
        entry = {
            "role": role, "content": content,
            "intent": intent, "timestamp": time.time(),
        }

        # 更新话题追踪
        if role == "user" and intent:
            itype = intent.get("type", "")
            if itype in ("device_toggle", "device_control", "ac_temp"):
                dev_id = intent.get("device_id", "")
                if dev_id:
                    self._current_topic["device_id"] = dev_id
                    self._current_topic["device_name"] = DEVICE_NAMES.get(dev_id, dev_id)
                    self._current_topic["action_type"] = itype
                    self._current_topic["last_params"] = intent.get("params")
                    # 推断房间
                    for room, devs in ROOM_DEVICES.items():
                        if dev_id in devs:
                            self._current_topic["room"] = room
                            break
            elif itype == "scene":
                self._current_topic["action_type"] = "scene"
            elif itype == "query":
                self._current_topic["action_type"] = "query"

        self._history.append(entry)
        if len(self._history) > self._max_turns:
            self._history = self._history[-self._max_turns:]

        # 持久化
        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO conversation_memory(role, content, intent_json, topic_device, topic_room) VALUES(?,?,?,?,?)",
                    (role, content[:500],
                     json.dumps(intent, ensure_ascii=False) if intent else None,
                     self._current_topic.get("device_id"),
                     self._current_topic.get("room"))
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    def resolve_reference(self, text: str) -> dict | None:
        """指代消解 — 解析"它""这个""再调低一点"等指代

        Returns:
            {"device_id": ..., "device_name": ..., "action_hint": ..., "context": ...}
            或 None (无法消解)
        """
        text = text.strip()

        # 1. 显式指代词
        for pronoun, ref_type in self.PRONOUN_MAP.items():
            if pronoun in text:
                topic = self._current_topic
                if topic["device_id"] and ref_type in ("device", topic.get("device_id", "").split("_")[0] if "_" in topic.get("device_id", "") else "device"):
                    dev_id = topic["device_id"]
                    dev_name = topic["device_name"]
                    # 判断动作方向
                    action_hint = self._infer_action_from_text(text)
                    return {
                        "device_id": dev_id,
                        "device_name": dev_name,
                        "action_hint": action_hint,
                        "context": f"指代上轮讨论的{dev_name}",
                        "original_text": text,
                        "resolved_text": text.replace(pronoun, dev_name),
                    }

        # 2. 省略续接模式
        for pattern, action_type in self.CONTINUATION_PATTERNS:
            if re.search(pattern, text):
                topic = self._current_topic
                if topic["device_id"]:
                    dev_id = topic["device_id"]
                    dev_name = topic["device_name"]
                    action_hint = self._infer_action_from_text(text)
                    return {
                        "device_id": dev_id,
                        "device_name": dev_name,
                        "action_hint": action_hint,
                        "context": f"续接上轮{dev_name}操作",
                        "original_text": text,
                        "resolved_text": f"{dev_name}{text}",
                    }

        return None

    def _infer_action_from_text(self, text: str) -> str:
        """从文本推断动作方向"""
        if any(w in text for w in ["高", "亮", "大", "开", "热"]):
            return "increase"
        if any(w in text for w in ["低", "暗", "小", "关", "冷"]):
            return "decrease"
        if any(w in text for w in ["不", "别", "取消", "停"]):
            return "cancel"
        return "adjust"

    def get_context_summary(self) -> str:
        """获取当前对话上下文摘要(用于AI prompt)"""
        topic = self._current_topic
        parts = []
        if topic["device_id"]:
            parts.append(f"当前话题设备: {topic['device_name']}({topic['device_id']})")
        if topic["room"]:
            parts.append(f"当前话题房间: {topic['room']}")
        if topic["action_type"]:
            parts.append(f"最近操作类型: {topic['action_type']}")
        if topic["last_params"]:
            parts.append(f"最近操作参数: {json.dumps(topic['last_params'], ensure_ascii=False)}")

        # 最近3轮对话
        recent = self._history[-6:]  # 3轮=6条
        if recent:
            conv_lines = []
            for entry in recent[-6:]:
                role = "用户" if entry["role"] == "user" else "助手"
                conv_lines.append(f"{role}: {entry['content'][:80]}")
            parts.append("最近对话:\n" + "\n".join(conv_lines))

        return "\n".join(parts) if parts else "无上下文"

    def get_recent_intents(self, n: int = 5) -> list[dict]:
        """获取最近N条用户意图"""
        intents = []
        for entry in reversed(self._history):
            if entry.get("role") == "user" and entry.get("intent"):
                intents.append(entry["intent"])
                if len(intents) >= n:
                    break
        return intents

    def clear(self):
        """清空对话记忆"""
        self._history.clear()
        self._current_topic = {
            "device_id": None, "device_name": None,
            "room": None, "action_type": None, "last_params": None,
        }
        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute("DELETE FROM conversation_memory")
                conn.commit()
                conn.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# LinkageEngine - 设备联动策略引擎
# ═══════════════════════════════════════════════════════════════

class LinkageEngine:
    """设备联动策略引擎 — 自动推理设备间联动关系

    功能:
    1. 基于模板的联动规则(设备注册时定义)
    2. 基于习惯的联动发现(用户经常同时操作两个设备)
    3. 基于场景的联动(场景激活时自动触发关联设备)
    4. 联动执行 + 日志记录
    """

    def __init__(self, db_path: str | Path = None, log_fn: Callable = None,
                 executor_fn: Callable = None, registry: DeviceRegistry = None):
        self._db_path = str(db_path) if db_path else None
        self._log = log_fn or (lambda m: None)
        self._executor = executor_fn  # 执行设备动作的函数
        self._registry = registry
        self._habit_linkages: list[dict] = []  # 从习惯中发现的联动
        self._init_db()
        self._load_habit_linkages()

    def _init_db(self):
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS linkage_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_device TEXT NOT NULL,
                trigger_event TEXT NOT NULL,
                target_device TEXT NOT NULL,
                target_action TEXT NOT NULL,
                target_params TEXT,
                rule_type TEXT DEFAULT 'template',
                enabled INTEGER DEFAULT 1,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS linkage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                source_device TEXT,
                trigger_event TEXT,
                target_device TEXT,
                result TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"[LINKAGE] DB初始化失败: {e}")

    def _load_habit_linkages(self):
        """从DB加载习惯发现的联动规则"""
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT source_device, trigger_event, target_device, target_action, target_params, description "
                "FROM linkage_rules WHERE rule_type='habit' AND enabled=1"
            ).fetchall()
            conn.close()
            for r in rows:
                self._habit_linkages.append({
                    "source_device": r[0], "trigger_event": r[1],
                    "target_device": r[2], "target_action": r[3],
                    "target_params": json.loads(r[4]) if r[4] else {},
                    "desc": r[5] or "",
                })
        except Exception:
            pass

    def on_device_change(self, device_id: str, event: str, state: dict = None):
        """设备状态变化时检查联动

        Args:
            device_id: 变化的设备ID
            event: "on" / "off" / "position_changed" / "temp_changed"
            state: 当前设备状态
        """
        triggered = []

        # 1. 检查模板联动规则
        if self._registry:
            for rule in self._registry.get_linkage_rules():
                if rule.get("source_device") == device_id and rule.get("when") == event:
                    triggered.append(rule)

        # 2. 检查习惯联动规则
        for rule in self._habit_linkages:
            if rule["source_device"] == device_id and rule["trigger_event"] == event:
                triggered.append(rule)

        # 执行联动
        for rule in triggered:
            self._execute_linkage(device_id, event, rule)

    def _execute_linkage(self, source_device: str, event: str, rule: dict):
        """执行一条联动规则"""
        target_device = rule.get("target_device") or (rule.get("then", [{}])[0].get("device") if rule.get("then") else None)
        if not target_device:
            return

        target_action = rule.get("target_action") or (rule.get("then", [{}])[0].get("action") if rule.get("then") else "toggle")
        target_params = rule.get("target_params") or (rule.get("then", [{}])[0].get("params") if rule.get("then") else {})

        desc = rule.get("desc", f"{source_device} {event} → {target_device} {target_action}")
        self._log(f"[LINKAGE] 触发联动: {desc}")

        if self._executor:
            try:
                result = self._executor({
                    "type": "device_control" if target_action.startswith("set_") else "device_toggle",
                    "device_id": target_device,
                    "action": target_action,
                    "params": target_params,
                    "isOn": target_params.get("isOn", True) if target_action == "toggle" else None,
                })
                self._log(f"[LINKAGE] 执行结果: {result}")
            except Exception as e:
                self._log(f"[LINKAGE] 执行失败: {e}")

        # 记录日志
        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO linkage_log(source_device, trigger_event, target_device, result) VALUES(?,?,?,?)",
                    (source_device, event, target_device, "ok")
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    def discover_from_habits(self, habit_stats: list[dict]) -> list[dict]:
        """从习惯数据中发现联动关系

        逻辑: 如果两个设备经常在同一小时内被操作，且操作间隔<5分钟，
        则认为存在联动关系

        Args:
            habit_stats: [{action_type, action_id, count, hour, ...}]

        Returns:
            发现的联动规则列表
        """
        discovered = []
        # 按小时分组
        by_hour: dict[int, list] = {}
        for stat in habit_stats:
            h = stat.get("hour", 0)
            if h not in by_hour:
                by_hour[h] = []
            by_hour[h].append(stat)

        # 同一小时内有多个设备操作 → 可能联动
        for hour, actions in by_hour.items():
            if len(actions) < 2:
                continue
            for i in range(len(actions)):
                for j in range(i + 1, len(actions)):
                    a1, a2 = actions[i], actions[j]
                    if a1.get("action_id") == a2.get("action_id"):
                        continue
                    # 检查是否已有此联动规则
                    existing = False
                    for hl in self._habit_linkages:
                        if (hl["source_device"] == a1["action_id"] and hl["target_device"] == a2["action_id"]):
                            existing = True
                            break
                    if not existing and a1.get("count", 0) >= 3 and a2.get("count", 0) >= 3:
                        rule = {
                            "source_device": a1["action_id"],
                            "trigger_event": "on",
                            "target_device": a2["action_id"],
                            "target_action": "toggle",
                            "target_params": {"isOn": True},
                            "desc": f"习惯发现: {DEVICE_NAMES.get(a1['action_id'], a1['action_id'])}开启时常同时操作{DEVICE_NAMES.get(a2['action_id'], a2['action_id'])}",
                            "rule_type": "habit",
                        }
                        discovered.append(rule)
                        self._habit_linkages.append(rule)

                        # 持久化
                        if self._db_path:
                            try:
                                conn = sqlite3.connect(self._db_path)
                                conn.execute(
                                    "INSERT INTO linkage_rules(source_device, trigger_event, target_device, target_action, target_params, rule_type, description) VALUES(?,?,?,?,?,?,?)",
                                    (rule["source_device"], rule["trigger_event"], rule["target_device"],
                                     rule["target_action"], json.dumps(rule["target_params"], ensure_ascii=False),
                                     "habit", rule["desc"])
                                )
                                conn.commit()
                                conn.close()
                            except Exception:
                                pass

        if discovered:
            self._log(f"[LINKAGE] 从习惯中发现 {len(discovered)} 条联动规则")
        return discovered

    def get_rules(self) -> list[dict]:
        """获取所有联动规则"""
        rules = []
        if self._registry:
            rules.extend(self._registry.get_linkage_rules())
        rules.extend(self._habit_linkages)
        return rules

    def get_log(self, limit: int = 50) -> list[dict]:
        """获取联动执行日志"""
        if not self._db_path:
            return []
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT source_device, trigger_event, target_device, result, created_at "
                "FROM linkage_log ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [{"source": r[0], "event": r[1], "target": r[2], "result": r[3], "time": r[4]} for r in rows]
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════
# EmotionAnalyzer - 情感感知
# ═══════════════════════════════════════════════════════════════

class EmotionAnalyzer:
    """情感感知 — 识别用户情绪，调整回复风格

    情绪维度:
    - positive/negative: 正面/负面
    - urgency: 紧急程度 (1-5)
    - comfort: 舒适度 (1-5)

    影响:
    - 紧急+负面 → 优先执行，简短确认，语音加速
    - 舒适+正面 → 可以闲聊，详细解释
    - 负面+不紧急 → 安慰性回复，建议改善方案
    """

    # 情绪关键词映射
    EMOTION_KEYWORDS = {
        "urgent_negative": [
            "着火了", "火灾", "救命", "紧急", "快", "赶紧", "马上",
            "报警", "闯入", "有人", "危险", "漏电", "漏水", "煤气",
        ],
        "negative": [
            "烦", "讨厌", "难受", "不舒服", "不好", "差", "糟糕",
            "失望", "生气", "郁闷", "无聊", "冷", "热", "吵",
        ],
        "positive": [
            "舒服", "好", "棒", "不错", "喜欢", "开心", "满意",
            "谢谢", "感谢", "赞", "完美", "温馨", "惬意",
        ],
        "comfort": [
            "放松", "休息", "安静", "舒适", "暖和", "凉快",
            "刚刚好", "正好", "合适",
        ],
    }

    # 情绪→回复风格映射
    REPLY_STYLES = {
        "urgent_negative": {
            "tone": "紧急确认",
            "brevity": "极简",  # 回复尽量短
            "action_priority": "immediate",  # 立即执行
            "voice_speed": "fast",
            "prefix": "⚠️ ",
            "suffix": "",
        },
        "negative": {
            "tone": "安慰+建议",
            "brevity": "适中",
            "action_priority": "high",
            "voice_speed": "normal",
            "prefix": "",
            "suffix": "，我帮您调整一下",
        },
        "positive": {
            "tone": "友好闲聊",
            "brevity": "详细",
            "action_priority": "normal",
            "voice_speed": "normal",
            "prefix": "",
            "suffix": " 😊",
        },
        "comfort": {
            "tone": "温馨确认",
            "brevity": "适中",
            "action_priority": "low",
            "voice_speed": "slow",
            "prefix": "",
            "suffix": "，享受舒适时光~",
        },
        "neutral": {
            "tone": "标准",
            "brevity": "适中",
            "action_priority": "normal",
            "voice_speed": "normal",
            "prefix": "",
            "suffix": "",
        },
    }

    def analyze(self, text: str) -> dict:
        """分析文本情绪

        Returns:
            {
                "emotion": "urgent_negative|negative|positive|comfort|neutral",
                "urgency": 1-5,
                "valence": -1 to 1 (负面到正面),
                "style": {...},  # 回复风格
                "detected_keywords": [...],
            }
        """
        text = text.strip()
        detected = []
        emotion = "neutral"

        # 按优先级检测: 紧急负面 > 负面 > 舒适 > 正面 > 中性
        for emo_type, keywords in [
            ("urgent_negative", self.EMOTION_KEYWORDS["urgent_negative"]),
            ("negative", self.EMOTION_KEYWORDS["negative"]),
            ("comfort", self.EMOTION_KEYWORDS["comfort"]),
            ("positive", self.EMOTION_KEYWORDS["positive"]),
        ]:
            for kw in keywords:
                if kw in text:
                    detected.append(kw)

        # 如果同时有正面和负面关键词，取更紧急的
        if detected:
            if any(kw in text for kw in self.EMOTION_KEYWORDS["urgent_negative"]):
                emotion = "urgent_negative"
            elif any(kw in text for kw in self.EMOTION_KEYWORDS["negative"]):
                if any(kw in text for kw in self.EMOTION_KEYWORDS["positive"]):
                    emotion = "negative"  # 负面优先
                else:
                    emotion = "negative"
            elif any(kw in text for kw in self.EMOTION_KEYWORDS["comfort"]):
                emotion = "comfort"
            elif any(kw in text for kw in self.EMOTION_KEYWORDS["positive"]):
                emotion = "positive"

        # 计算数值
        urgency = 1
        valence = 0.0
        if emotion == "urgent_negative":
            urgency = 5
            valence = -1.0
        elif emotion == "negative":
            urgency = 3
            valence = -0.5
        elif emotion == "comfort":
            urgency = 1
            valence = 0.3
        elif emotion == "positive":
            urgency = 1
            valence = 0.8

        style = self.REPLY_STYLES.get(emotion, self.REPLY_STYLES["neutral"])

        return {
            "emotion": emotion,
            "urgency": urgency,
            "valence": valence,
            "style": style,
            "detected_keywords": detected,
        }

    def apply_style(self, reply: str, emotion_result: dict) -> str:
        """根据情绪调整回复文本"""
        style = emotion_result.get("style", {})
        prefix = style.get("prefix", "")
        suffix = style.get("suffix", "")

        if style.get("brevity") == "极简" and len(reply) > 50:
            # 紧急情况截短
            reply = reply[:50] + "..."

        return f"{prefix}{reply}{suffix}"

    def should_execute_immediately(self, emotion_result: dict) -> bool:
        """判断是否应立即执行(不等待确认)"""
        return emotion_result.get("urgency", 1) >= 4


# ═══════════════════════════════════════════════════════════════
# EnergyAdvisor - 节能优化顾问
# ═══════════════════════════════════════════════════════════════

class EnergyAdvisor:
    """节能优化顾问 — 基于设备使用模式给出节能建议

    功能:
    1. 计算实时/日/月能耗估算
    2. 识别高耗能设备
    3. 发现浪费模式(空房开灯、空调过冷等)
    4. 生成节能建议
    5. 跟踪节能效果
    """

    # 默认功率表(瓦) — 可被 DeviceRegistry 的 energy_watts 覆盖
    DEFAULT_WATTS = {
        "light": 12, "ac": 1200, "fan": 30, "curtain": 15,
        "door": 5, "alarm": 10, "sensor": 1, "custom": 20,
    }

    def __init__(self, db_path: str | Path = None, log_fn: Callable = None,
                 get_context_fn: Callable = None, registry: DeviceRegistry = None):
        self._db_path = str(db_path) if db_path else None
        self._log = log_fn or (lambda m: None)
        self._get_context = get_context_fn or (lambda: {})
        self._registry = registry
        self._init_db()

    def _init_db(self):
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS energy_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_json TEXT NOT NULL,
                total_watts REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS energy_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggestion_type TEXT NOT NULL,
                description TEXT NOT NULL,
                potential_saving TEXT,
                accepted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"[ENERGY] DB初始化失败: {e}")

    def _get_device_watts(self, device_id: str) -> float:
        """获取设备功率"""
        if self._registry:
            tpl = self._registry.get_template(device_id)
            if tpl and tpl.get("energy_watts"):
                return float(tpl["energy_watts"])
        # 从 DEVICE_CAPABILITIES 推断类型
        dev_type = "custom"
        if device_id.startswith("light"):
            dev_type = "light"
        elif device_id.startswith("ac"):
            dev_type = "ac"
        elif device_id.startswith("fan"):
            dev_type = "fan"
        elif device_id.startswith("curtain"):
            dev_type = "curtain"
        elif device_id.startswith("door"):
            dev_type = "door"
        elif device_id.startswith("alarm"):
            dev_type = "alarm"
        return self.DEFAULT_WATTS.get(dev_type, 20)

    def get_current_consumption(self) -> dict:
        """获取当前实时能耗"""
        ctx = self._get_context()
        total_watts = 0.0
        device_details = []

        for dev_id in DEVICE_CAPABILITIES:
            is_on = ctx.get(f"{dev_id}_on", False)
            watts = self._get_device_watts(dev_id)
            consumption = watts if is_on else 0
            total_watts += consumption
            device_details.append({
                "id": dev_id,
                "name": DEVICE_NAMES.get(dev_id, dev_id),
                "on": is_on,
                "watts": watts,
                "consuming": consumption,
            })

        # 估算日/月费用(按0.6元/kWh)
        daily_kwh = total_watts * 24 / 1000
        monthly_cost = daily_kwh * 30 * 0.6

        return {
            "total_watts": total_watts,
            "total_kw": round(total_watts / 1000, 2),
            "daily_kwh_estimate": round(daily_kwh, 2),
            "monthly_cost_estimate": round(monthly_cost, 2),
            "active_devices": sum(1 for d in device_details if d["on"]),
            "devices": device_details,
        }

    def analyze_waste(self) -> list[dict]:
        """分析浪费模式"""
        ctx = self._get_context()
        hour = ctx.get("hour", datetime.now().hour)
        suggestions = []

        # 1. 空房开灯检测
        for room, devs in ROOM_DEVICES.items():
            lights_on = []
            for dev_id in devs:
                if dev_id.startswith("light") and ctx.get(f"{dev_id}_on", False):
                    lights_on.append(dev_id)

            if lights_on and room == "厨房" and not (11 <= hour <= 13 or 17 <= hour <= 20):
                suggestions.append({
                    "type": "empty_room_light",
                    "severity": "low",
                    "description": f"厨房灯开着但非用餐时间，建议关闭节省电力",
                    "devices": lights_on,
                    "potential_saving": f"{sum(self._get_device_watts(d) for d in lights_on):.0f}W",
                })
            if lights_on and room == "卫生间" and not (6 <= hour <= 22):
                suggestions.append({
                    "type": "empty_room_light",
                    "severity": "low",
                    "description": f"卫生间灯深夜仍开着，建议关闭",
                    "devices": lights_on,
                    "potential_saving": f"{sum(self._get_device_watts(d) for d in lights_on):.0f}W",
                })

        # 2. 空调过冷/过热检测
        ac_on = ctx.get("ac_01_on", False)
        temp = ctx.get("temp")
        if ac_on and temp is not None:
            if temp < 22:
                suggestions.append({
                    "type": "ac_too_cold",
                    "severity": "medium",
                    "description": f"当前室温{temp}°C偏低，空调温度可调高2-3°C，每月可省约30元",
                    "devices": ["ac_01"],
                    "potential_saving": "约30元/月",
                })
            elif temp > 28 and ac_on:
                suggestions.append({
                    "type": "ac_inefficient",
                    "severity": "medium",
                    "description": f"空调开着但室温仍{temp}°C，可能需要清洗滤网或检查门窗",
                    "devices": ["ac_01"],
                    "potential_saving": "提升制冷效率",
                })

        # 3. 高温未开空调(舒适度建议)
        if not ac_on and temp is not None and temp > 30:
            suggestions.append({
                "type": "comfort_suggestion",
                "severity": "info",
                "description": f"当前{temp}°C，开启空调可提升舒适度(建议26°C节能模式)",
                "devices": ["ac_01"],
                "potential_saving": "舒适度提升",
            })

        # 4. 窗帘+空调同时运行
        curtain_open = ctx.get("curtain_01_on", False)
        if ac_on and curtain_open:
            suggestions.append({
                "type": "ac_curtain_conflict",
                "severity": "medium",
                "description": "空调运行时窗帘开着，阳光直射增加制冷负担，建议关窗帘",
                "devices": ["ac_01", "curtain_01"],
                "potential_saving": "约15%空调能耗",
            })

        # 5. 深夜全屋灯光
        if hour >= 23 or hour <= 5:
            all_lights = [dev_id for dev_id in DEVICE_CAPABILITIES if dev_id.startswith("light") and ctx.get(f"{dev_id}_on", False)]
            if len(all_lights) >= 3:
                suggestions.append({
                    "type": "night_lights",
                    "severity": "medium",
                    "description": f"深夜有{len(all_lights)}盏灯开着，建议只保留必要的灯",
                    "devices": all_lights,
                    "potential_saving": f"{sum(self._get_device_watts(d) for d in all_lights):.0f}W",
                })

        # 持久化建议
        if suggestions and self._db_path:
            try:
                conn = sqlite3.connect(self._db_path)
                for s in suggestions:
                    # 避免重复(同类型同天)
                    existing = conn.execute(
                        "SELECT id FROM energy_suggestions WHERE suggestion_type=? AND created_at >= datetime('now','-1 day') LIMIT 1",
                        (s["type"],)
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO energy_suggestions(suggestion_type, description, potential_saving) VALUES(?,?,?)",
                            (s["type"], s["description"], s.get("potential_saving", ""))
                        )
                conn.commit()
                conn.close()
            except Exception:
                pass

        return suggestions

    def get_daily_report(self) -> dict:
        """生成每日能耗报告"""
        consumption = self.get_current_consumption()
        waste = self.analyze_waste()

        # 计算节能潜力
        total_waste_watts = 0
        for w in waste:
            saving = w.get("potential_saving", "")
            if saving.endswith("W"):
                try:
                    total_waste_watts += float(saving[:-1])
                except ValueError:
                    pass

        potential_monthly_saving = total_waste_watts * 24 * 30 / 1000 * 0.6

        return {
            "current_consumption": consumption,
            "waste_analysis": waste,
            "waste_count": len(waste),
            "potential_saving_watts": total_waste_watts,
            "potential_monthly_saving": round(potential_monthly_saving, 2),
            "summary": f"当前功耗{consumption['total_watts']:.0f}W，发现{len(waste)}项优化点，月度可节省约{potential_monthly_saving:.1f}元",
        }

    def get_suggestions(self, limit: int = 10) -> list[dict]:
        """获取历史节能建议"""
        if not self._db_path:
            return []
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT suggestion_type, description, potential_saving, accepted, created_at "
                "FROM energy_suggestions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [{"type": r[0], "description": r[1], "saving": r[2], "accepted": bool(r[3]), "time": r[4]} for r in rows]
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════
# IntentMatcher - 快速意图匹配
# ═══════════════════════════════════════════════════════════════

# 意图规则: (pattern, intent_type, intent_data)
# intent_type: scene / device_toggle / device_control / door / query / ac_temp
INTENT_RULES: list[tuple] = [
    # ===== 场景意图 =====
    (r"(睡觉|晚安|休息|就寝|困了|想睡|睡吧|该睡了)", "scene", "s3"),
    (r"(回家|到家|回来了|我回来了|到家了)", "scene", "s1"),
    (r"(出门|走了|离家|我出门|离开|我走了|出门了)", "scene", "s2"),
    (r"(看电影|观影|电视|电影时间|看剧|追剧)", "scene", "s4"),
    (r"(吃饭|用餐|晚餐|午餐|做饭|开饭|吃饭了)", "scene", "s5"),

    # ===== 设备开关 - 客厅灯 =====
    (r"(开|打开|启动|点亮).*(客厅)?(主)?灯", "device_toggle", {"device_id": "light_01", "isOn": True}),
    (r"(关|关闭|关掉|熄灭).*(客厅)?(主)?灯", "device_toggle", {"device_id": "light_01", "isOn": False}),
    # ===== 厨房灯 =====
    (r"(开|打开|启动).*(厨房)?灯", "device_toggle", {"device_id": "light_02", "isOn": True}),
    (r"(关|关闭|关掉).*(厨房)?灯", "device_toggle", {"device_id": "light_02", "isOn": False}),
    # ===== 卧室灯 =====
    (r"(开|打开|启动).*(卧室)?灯", "device_toggle", {"device_id": "light_03", "isOn": True}),
    (r"(关|关闭|关掉).*(卧室)?灯", "device_toggle", {"device_id": "light_03", "isOn": False}),
    # ===== 卫生间灯 =====
    (r"(开|打开|启动).*(卫生间|浴室|厕所)?灯", "device_toggle", {"device_id": "light_04", "isOn": True}),
    (r"(关|关闭|关掉).*(卫生间|浴室|厕所)?灯", "device_toggle", {"device_id": "light_04", "isOn": False}),
    # ===== 空调 =====
    (r"(开|打开|启动).*(空调)", "device_toggle", {"device_id": "ac_01", "isOn": True}),
    (r"(关|关闭|关掉).*(空调)", "device_toggle", {"device_id": "ac_01", "isOn": False}),
    # ===== 窗帘 =====
    (r"(开|打开|拉开).*(窗帘)", "device_toggle", {"device_id": "curtain_01", "isOn": True}),
    (r"(关|关闭|拉上|合上).*(窗帘)", "device_toggle", {"device_id": "curtain_01", "isOn": False}),
    # ===== 换气扇 =====
    (r"(开|打开|启动).*(换气扇|排气扇|风扇)", "device_toggle", {"device_id": "fan_02", "isOn": True}),
    (r"(关|关闭|关掉).*(换气扇|排气扇|风扇)", "device_toggle", {"device_id": "fan_02", "isOn": False}),
    # ===== 门禁 =====
    (r"(开门|解锁|把门打开|打开门)", "door", "open"),
    (r"(关门|锁门|锁上|把门关上|关上门)", "door", "close"),

    # ===== 参数控制 =====
    (r"(客厅)?灯.*?(\d+)\s*%", "device_control", {"device_id": "light_01", "action": "set_brightness"}),
    (r"厨房灯.*?(\d+)\s*%", "device_control", {"device_id": "light_02", "action": "set_brightness"}),
    (r"卧室灯.*?(\d+)\s*%", "device_control", {"device_id": "light_03", "action": "set_brightness"}),
    (r"卫生间灯.*?(\d+)\s*%", "device_control", {"device_id": "light_04", "action": "set_brightness"}),
    (r"空调.*?(\d+)\s*度", "ac_temp", None),
    (r"(\d+)\s*度.*?空调", "ac_temp", None),
    (r"窗帘.*?(\d+)\s*%", "device_control", {"device_id": "curtain_01", "action": "set_position"}),
    (r"换气扇.*?(\d+)", "device_control", {"device_id": "fan_02", "action": "set_speed"}),

    # ===== 查询 =====
    (r"(温度|几度|多热|多冷|室温)", "query", "temperature"),
    (r"(湿度|多湿|潮不潮)", "query", "humidity"),
    (r"(烟雾|安全|报警|火灾)", "query", "safety"),
    (r"(状态|全部|所有|概览|总览)", "query", "all"),
    (r"(厨房|厨房状态)", "query", "kitchen"),
    (r"(门|门禁|锁)", "query", "door"),
    # ===== 节能查询 =====
    (r"(能耗|用电|电费|功耗|节能|省电|费电)", "query", "energy"),
    (r"(浪费|优化|节能建议)", "query", "energy_waste"),
]


class IntentMatcher:
    """快速意图匹配器 - 正则+关键词，0延迟"""

    def __init__(self, registry: DeviceRegistry = None):
        self._registry = registry
        self._compiled = [(re.compile(p, re.IGNORECASE), itype, idata) for p, itype, idata in INTENT_RULES]
        # 动态规则(从设备注册表加载)
        self._dynamic_compiled = []
        if registry:
            self._refresh_dynamic()

    def _refresh_dynamic(self):
        """从设备注册表刷新动态意图规则"""
        if not self._registry:
            return
        self._dynamic_compiled = []
        for pat_tuple in self._registry.get_intent_patterns():
            try:
                p, itype, idata = pat_tuple
                self._dynamic_compiled.append((re.compile(p, re.IGNORECASE), itype, idata))
            except Exception:
                pass

    def match(self, text: str) -> dict | None:
        """匹配用户输入，返回意图或 None"""
        text = text.strip()
        if not text:
            return None

        # 1. 先尝试场景别名匹配
        try:
            from scenes.scene_config import SCENE_ALIASES, get_scene_id_by_name
            for sid, aliases in SCENE_ALIASES.items():
                for alias in aliases:
                    if alias.lower() == text.lower() or alias.lower() in text.lower():
                        return {"type": "scene", "scene_id": sid, "confidence": 0.95,
                                "source": "alias", "explanation": f"匹配场景别名: {alias}"}
        except ImportError:
            pass

        # 2. 正则规则匹配(静态)
        for pattern, itype, idata in self._compiled:
            m = pattern.search(text)
            if m:
                return self._build_result(m, itype, idata)

        # 3. 动态规则匹配(从设备注册表)
        for pattern, itype, idata in self._dynamic_compiled:
            m = pattern.search(text)
            if m:
                return self._build_result(m, itype, idata)

        # 4. 设备别名匹配
        for alias, dev_id in DEVICE_ALIASES.items():
            if alias in text and dev_id:
                is_on = any(kw in text for kw in ["开", "打开", "启动", "点亮"])
                is_off = any(kw in text for kw in ["关", "关闭", "关掉", "熄灭"])
                if is_on or is_off:
                    return {
                        "type": "device_toggle",
                        "device_id": dev_id,
                        "isOn": is_on and not is_off,
                        "confidence": 0.8,
                        "source": "alias",
                        "explanation": f"{'开' if is_on else '关'}{DEVICE_NAMES.get(dev_id, dev_id)}"
                    }

        return None

    def _build_result(self, m, itype: str, idata) -> dict:
        """构建匹配结果"""
        result = {"type": itype, "confidence": 0.9, "source": "regex"}

        if itype == "scene":
            result["scene_id"] = idata
            result["explanation"] = f"匹配场景: {idata}"

        elif itype == "device_toggle":
            result.update(idata)
            dev_name = DEVICE_NAMES.get(idata.get("device_id", ""), idata.get("device_id", ""))
            state = "开" if idata.get("isOn") else "关"
            result["explanation"] = f"{state}{dev_name}"

        elif itype == "device_control":
            result.update(idata)
            value_str = m.group(m.lastindex) if m.lastindex else None
            if value_str:
                try:
                    val = int(value_str)
                    result["params"] = {"value": val}
                    dev_name = DEVICE_NAMES.get(idata.get("device_id", ""), "")
                    result["explanation"] = f"{dev_name}设为{val}"
                except ValueError:
                    pass

        elif itype == "ac_temp":
            value_str = m.group(m.lastindex) if m.lastindex else None
            if value_str:
                try:
                    temp = int(value_str)
                    temp = max(16, min(30, temp))
                    result["device_id"] = "ac_01"
                    result["action"] = "set_temp"
                    result["params"] = {"value": temp}
                    result["explanation"] = f"空调设为{temp}°C"
                except ValueError:
                    pass

        elif itype == "door":
            result["door_action"] = idata
            result["explanation"] = f"{'开门' if idata == 'open' else '关门'}"

        elif itype == "query":
            result["query_type"] = idata
            result["explanation"] = f"查询{idata}"

        return result


# ═══════════════════════════════════════════════════════════════
# FuzzyReasoner - 模糊意图推理
# ═══════════════════════════════════════════════════════════════

FUZZY_RULES: list[dict] = [
    {
        "triggers": ["有点暗", "太暗了", "看不清", "光线不好", "不够亮", "暗了"],
        "context_check": "light_off_or_low",
        "action": {"type": "device_toggle", "device_id": "light_01", "isOn": True},
        "alt_action": {"type": "device_control", "device_id": "light_01", "action": "set_brightness", "params": {"value": 80}},
        "explanation": "当前光线不足，为您开灯",
    },
    {
        "triggers": ["太亮了", "刺眼", "光太强", "太亮", "晃眼"],
        "context_check": "light_on",
        "action": {"type": "device_control", "device_id": "light_01", "action": "set_brightness", "params": {"value": 30}},
        "explanation": "为您调暗灯光到30%",
    },
    {
        "triggers": ["太热了", "好热", "热死了", "闷热", "热得受不了", "好闷"],
        "context_check": "hot_or_ac_off",
        "action": {"type": "device_toggle", "device_id": "ac_01", "isOn": True},
        "alt_action": {"type": "device_control", "device_id": "ac_01", "action": "set_temp", "params": {"value": 26}},
        "explanation": "为您开启空调制冷26°C",
    },
    {
        "triggers": ["太冷了", "好冷", "冷死了", "冻死了", "好冻"],
        "context_check": "cold_or_ac_off",
        "action": {"type": "device_toggle", "device_id": "ac_01", "isOn": True},
        "alt_action": {"type": "device_control", "device_id": "ac_01", "action": "set_temp", "params": {"value": 24}},
        "explanation": "为您开启空调制热24°C",
    },
    {
        "triggers": ["太干了", "好干", "干燥", "皮肤干", "嗓子干"],
        "context_check": "low_humidity",
        "action": None,  # 无加湿器
        "explanation": "当前湿度偏低，建议使用加湿器",
    },
    {
        "triggers": ["太湿了", "潮湿", "闷湿", "好湿", "返潮"],
        "context_check": "high_humidity",
        "action": {"type": "device_toggle", "device_id": "fan_02", "isOn": True},
        "alt_action": {"type": "device_toggle", "device_id": "fan_02", "isOn": True},
        "explanation": "湿度偏高，为您开启换气扇通风",
    },
    {
        "triggers": ["我想看电影", "看电影吧", "电影时间", "追剧", "看剧"],
        "context_check": "always",
        "action": {"type": "scene", "scene_id": "s4"},
        "explanation": "为您切换到观影模式",
    },
    {
        "triggers": ["我出门了", "我走了", "出门了", "走了", "不在家"],
        "context_check": "always",
        "action": {"type": "scene", "scene_id": "s2"},
        "explanation": "为您切换到离家模式",
    },
]


class FuzzyReasoner:
    """模糊意图推理器 - 上下文感知"""

    def __init__(self, get_context_fn: Callable = None, log_fn: Callable = None):
        self._get_context = get_context_fn or (lambda: {})
        self._log = log_fn or (lambda m: None)

    def _check_context(self, rule_id: str, ctx: dict) -> bool:
        """检查上下文条件"""
        if rule_id == "always":
            return True
        if rule_id == "light_off_or_low":
            return not ctx.get("light_01_on", True)
        if rule_id == "light_on":
            return ctx.get("light_01_on", False)
        if rule_id == "hot_or_ac_off":
            return ctx.get("temp", 0) > 26 or not ctx.get("ac_01_on", False)
        if rule_id == "cold_or_ac_off":
            return ctx.get("temp", 30) < 20 or not ctx.get("ac_01_on", False)
        if rule_id == "low_humidity":
            return ctx.get("humidity", 50) < 35
        if rule_id == "high_humidity":
            return ctx.get("humidity", 30) > 70
        return False

    def reason(self, text: str) -> dict | None:
        """推理模糊意图"""
        text = text.strip()
        if not text:
            return None

        ctx = self._get_context()

        for rule in FUZZY_RULES:
            for trigger in rule["triggers"]:
                if trigger in text:
                    ctx_ok = self._check_context(rule["context_check"], ctx)
                    self._log(f"[FUZZY] trigger={trigger} ctx_check={rule['context_check']} ctx_ok={ctx_ok}")
                    action = rule["action"]
                    # 如果主上下文不满足但有替代动作，尝试替代
                    if not ctx_ok and "alt_action" in rule and rule.get("alt_action"):
                        action = rule["alt_action"]
                        ctx_ok = True
                        self._log(f"[FUZZY] 切换到替代动作: {action}")
                    if ctx_ok:
                        action = rule["action"]
                        if action is None:
                            return {
                                "type": "suggestion",
                                "confidence": 0.85,
                                "source": "fuzzy",
                                "explanation": rule["explanation"],
                                "action": None,
                            }
                        result = {
                            "confidence": 0.85,
                            "source": "fuzzy",
                            "explanation": rule["explanation"],
                        }
                        result.update(action)
                        return result

        return None


# ═══════════════════════════════════════════════════════════════
# AnomalyDetector - 异常模式识别
# ═══════════════════════════════════════════════════════════════

ANOMALY_RULES: list[dict] = [
    {
        "id": "unusual_door_night",
        "name": "夜间异常开门",
        "check_fn": "check_door_night",
        "severity": "critical",
        "message": "凌晨{hour}点检测到门被打开，请注意安全！",
    },
    {
        "id": "ac_overuse",
        "name": "空调长时间运行",
        "check_fn": "check_ac_overuse",
        "severity": "warning",
        "message": "空调已连续运行{hours}小时，建议适当休息或调高温度",
    },
    {
        "id": "temp_spike",
        "name": "温度骤变",
        "check_fn": "check_temp_spike",
        "severity": "warning",
        "message": "温度5分钟内变化{change}°C，可能设备异常",
    },
    {
        "id": "smoke_no_heat",
        "name": "烟雾无高温(可能误触)",
        "check_fn": "check_smoke_no_heat",
        "severity": "warning",
        "message": "烟雾报警但温度正常，可能是误触",
    },
    {
        "id": "smoke_with_heat",
        "name": "烟雾+高温(确认火灾)",
        "check_fn": "check_smoke_with_heat",
        "severity": "critical",
        "message": "⚠️ 烟雾报警+温度异常，疑似真实火灾！",
    },
    {
        "id": "high_temp_no_ac",
        "name": "高温未开空调",
        "check_fn": "check_high_temp_no_ac",
        "severity": "info",
        "message": "当前温度{temp}°C较高，建议开启空调",
    },
]


class AnomalyDetector:
    """异常模式检测器 - 后台线程定期检查"""

    def __init__(self, db_path: str | Path, get_status_fn: Callable = None,
                 log_fn: Callable = None, tts_fn: Callable = None):
        self._db_path = str(db_path)
        self._get_status = get_status_fn or (lambda: {})
        self._log = log_fn or print
        self._tts = tts_fn or (lambda t: None)
        self._last_door_state = None
        self._last_temp = None
        self._last_temp_time = 0
        self._ac_on_since = None
        self._notified: set[str] = set()
        self._running = False
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS anomaly_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anomaly_type TEXT NOT NULL,
            severity TEXT DEFAULT 'warning',
            details TEXT,
            device_id TEXT,
            message TEXT,
            resolved INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_type ON anomaly_events(anomaly_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_time ON anomaly_events(created_at)")
        conn.commit()
        conn.close()

    def _record(self, anomaly_type: str, severity: str, message: str, details: dict = None, device_id: str = None):
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO anomaly_events(anomaly_type,severity,details,device_id,message) VALUES(?,?,?,?,?)",
                (anomaly_type, severity, json.dumps(details or {}, ensure_ascii=False),
                 device_id, message)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"[ANOMALY] 记录失败: {e}")

    def check(self) -> list[dict]:
        status = self._get_status()
        now = datetime.now()
        hour = now.hour
        anomalies = []

        door_open = status.get("door_01_on", False)
        ac_on = status.get("ac_01_on", False)
        temp = status.get("temp")
        humidity = status.get("humidity")
        smoke_alarm = status.get("smoke_alarm", False)
        heat_alarm = status.get("heat_alarm", False)

        # 1. 夜间异常开门
        if door_open and 0 <= hour <= 6:
            key = f"door_night_{now.date()}"
            if key not in self._notified:
                msg = f"凌晨{hour}点检测到门被打开，请注意安全！"
                anomalies.append({"id": "unusual_door_night", "severity": "critical", "message": msg})
                self._record("unusual_door_night", "critical", msg, {"hour": hour}, "door_01")
                self._notified.add(key)
                self._tts(msg)

        # 2. 空调长时间运行
        if ac_on:
            if self._ac_on_since is None:
                self._ac_on_since = time.time()
            running_hours = (time.time() - self._ac_on_since) / 3600
            if running_hours > 12:
                key = f"ac_overuse_{now.date()}_{int(running_hours)}"
                if key not in self._notified:
                    msg = f"空调已连续运行{int(running_hours)}小时，建议适当休息或调高温度"
                    anomalies.append({"id": "ac_overuse", "severity": "warning", "message": msg})
                    self._record("ac_overuse", "warning", msg, {"hours": int(running_hours)}, "ac_01")
                    self._notified.add(key)
                    self._tts(msg)
        else:
            self._ac_on_since = None

        # 3. 温度骤变
        if temp is not None:
            now_ts = time.time()
            if self._last_temp is not None and self._last_temp_time > 0:
                dt = now_ts - self._last_temp_time
                if dt > 0 and dt < 600:
                    change = abs(temp - self._last_temp)
                    if change > 5:
                        key = f"temp_spike_{now.date()}_{int(now_ts/300)}"
                        if key not in self._notified:
                            msg = f"温度5分钟内变化{change:.1f}°C，可能设备异常"
                            anomalies.append({"id": "temp_spike", "severity": "warning", "message": msg})
                            self._record("temp_spike", "warning", msg,
                                         {"old_temp": self._last_temp, "new_temp": temp, "change": change}, "temp_01")
                            self._notified.add(key)
                            self._tts(msg)
            self._last_temp = temp
            self._last_temp_time = now_ts

        # 4. 烟雾+温度判断
        now_ts = time.time()
        if smoke_alarm:
            if heat_alarm:
                key = f"fire_confirmed_{now.date()}_{int(now_ts/60)}"
                if key not in self._notified:
                    msg = "⚠️ 烟雾报警+温度异常，疑似真实火灾！"
                    anomalies.append({"id": "smoke_with_heat", "severity": "critical", "message": msg})
                    self._record("smoke_with_heat", "critical", msg, {"smoke": True, "heat": True}, "smoke_01")
                    self._notified.add(key)
                    self._tts(msg)
            else:
                key = f"smoke_no_heat_{now.date()}_{int(time.time()/300)}"
                if key not in self._notified:
                    msg = "烟雾报警但温度正常，可能是误触"
                    anomalies.append({"id": "smoke_no_heat", "severity": "warning", "message": msg})
                    self._record("smoke_no_heat", "warning", msg, {"smoke": True, "heat": False}, "smoke_01")

        # 5. 高温未开空调
        if temp is not None and temp > 30 and not ac_on:
            key = f"high_temp_no_ac_{now.date()}_{int(now.hour)}"
            if key not in self._notified:
                msg = f"当前温度{temp}°C较高，建议开启空调"
                anomalies.append({"id": "high_temp_no_ac", "severity": "info", "message": msg})
                self._record("high_temp_no_ac", "info", msg, {"temp": temp}, "ac_01")
                self._notified.add(key)

        # 清理过期通知标记
        if hour == 0 and len(self._notified) > 100:
            self._notified.clear()

        return anomalies

    def get_events(self, limit: int = 50) -> list[dict]:
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT anomaly_type,severity,details,device_id,message,resolved,created_at "
                "FROM anomaly_events ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [{
                "type": r[0], "severity": r[1], "details": json.loads(r[2]) if r[2] else {},
                "device_id": r[3], "message": r[4], "resolved": bool(r[5]), "timestamp": r[6]
            } for r in rows]
        except Exception:
            return []

    def start(self, interval: float = 30.0):
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    self.check()
                except Exception as e:
                    self._log(f"[ANOMALY] 检查异常: {e}")
                time.sleep(interval)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        self._log("[ANOMALY] 异常检测线程已启动")

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════
# HabitLearner - 习惯学习与主动推荐
# ═══════════════════════════════════════════════════════════════

class HabitLearner:
    """习惯学习器 - 记录操作模式，生成主动推荐"""

    def __init__(self, db_path: str | Path, log_fn: Callable = None):
        self._db_path = str(db_path)
        self._log = log_fn or print
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS user_habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'u001',
            action_type TEXT NOT NULL,
            action_id TEXT NOT NULL,
            action_params TEXT,
            hour INTEGER,
            weekday INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_habits_user ON user_habits(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_habits_action ON user_habits(action_type,action_id,hour)")

        conn.execute("""CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rec_type TEXT NOT NULL,
            description TEXT NOT NULL,
            suggested_action TEXT,
            accepted INTEGER DEFAULT 0,
            dismissed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rec_type ON ai_recommendations(rec_type)")
        conn.commit()
        conn.close()

    def record(self, action_type: str, action_id: str, action_params: dict = None):
        now = datetime.now()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO user_habits(user_id,action_type,action_id,action_params,hour,weekday) VALUES(?,?,?,?,?,?)",
                ("u001", action_type, action_id,
                 json.dumps(action_params or {}, ensure_ascii=False),
                 now.hour, now.weekday())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"[HABIT] 记录失败: {e}")

        self._check_and_recommend(action_type, action_id, now.hour, now.weekday())

    def _check_and_recommend(self, action_type: str, action_id: str, hour: int, weekday: int):
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT COUNT(*), DATE(created_at) as d FROM user_habits "
                "WHERE action_type=? AND action_id=? AND ABS(hour-?)<=1 "
                "AND created_at >= datetime('now','-7 days') "
                "GROUP BY d ORDER BY d DESC LIMIT 7",
                (action_type, action_id, hour)
            ).fetchall()
            conn.close()

            distinct_days = len(rows)
            if distinct_days >= 3:
                conn = sqlite3.connect(self._db_path)
                existing = conn.execute(
                    "SELECT id FROM ai_recommendations "
                    "WHERE rec_type=? AND created_at >= datetime('now','-7 days') LIMIT 1",
                    (f"habit_{action_type}_{action_id}",)
                ).fetchone()
                conn.close()

                if not existing:
                    desc = self._build_recommendation_desc(action_type, action_id, hour)
                    action_json = json.dumps({
                        "type": action_type,
                        "action_id": action_id,
                        "hour": hour,
                    }, ensure_ascii=False)
                    conn = sqlite3.connect(self._db_path)
                    conn.execute(
                        "INSERT INTO ai_recommendations(rec_type,description,suggested_action) VALUES(?,?,?)",
                        (f"habit_{action_type}_{action_id}", desc, action_json)
                    )
                    conn.commit()
                    conn.close()
                    self._log(f"[HABIT] 新推荐: {desc}")
        except Exception as e:
            self._log(f"[HABIT] 推荐检查失败: {e}")

    def _build_recommendation_desc(self, action_type: str, action_id: str, hour: int) -> str:
        dev_name = DEVICE_NAMES.get(action_id, action_id)
        if action_type == "scene":
            try:
                from scenes.scene_config import SCENE_META
                scene_name = SCENE_META.get(action_id, {}).get("name", action_id)
                return f"检测到您连续多天在{hour}点左右激活「{scene_name}」场景，是否设置为自动执行？"
            except ImportError:
                return f"检测到您连续多天在{hour}点左右执行场景{action_id}，是否设置为自动执行？"
        elif action_type == "device_toggle":
            return f"检测到您连续多天在{hour}点左右操作{dev_name}，是否设置为自动执行？"
        elif action_type == "device_control":
            return f"检测到您连续多天在{hour}点左右调节{dev_name}，是否设置为自动执行？"
        else:
            return f"检测到您连续多天在{hour}点左右执行{action_type}:{action_id}，是否设置为自动执行？"

    def get_recommendations(self, limit: int = 10) -> list[dict]:
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT id,rec_type,description,suggested_action,accepted,dismissed,created_at "
                "FROM ai_recommendations WHERE dismissed=0 ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [{
                "id": r[0], "type": r[1], "description": r[2],
                "suggested_action": json.loads(r[3]) if r[3] else None,
                "accepted": bool(r[4]), "dismissed": bool(r[5]), "timestamp": r[6]
            } for r in rows]
        except Exception:
            return []

    def accept_recommendation(self, rec_id: int) -> bool:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("UPDATE ai_recommendations SET accepted=1 WHERE id=?", (rec_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def dismiss_recommendation(self, rec_id: int) -> bool:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("UPDATE ai_recommendations SET dismissed=1 WHERE id=?", (rec_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def get_stats(self) -> dict:
        try:
            conn = sqlite3.connect(self._db_path)
            total_habits = conn.execute("SELECT COUNT(*) FROM user_habits").fetchone()[0]
            total_recs = conn.execute("SELECT COUNT(*) FROM ai_recommendations").fetchone()[0]
            accepted_recs = conn.execute("SELECT COUNT(*) FROM ai_recommendations WHERE accepted=1").fetchone()[0]
            recent = conn.execute(
                "SELECT action_type, action_id, COUNT(*) as cnt FROM user_habits "
                "WHERE created_at >= datetime('now','-7 days') "
                "GROUP BY action_type, action_id ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            conn.close()
            top_actions = []
            for r in recent:
                dev_name = DEVICE_NAMES.get(r[1], r[1])
                top_actions.append({"type": r[0], "id": r[1], "name": dev_name, "count": r[2]})
            return {
                "total_habits": total_habits,
                "total_recommendations": total_recs,
                "accepted_recommendations": accepted_recs,
                "top_actions_7d": top_actions,
            }
        except Exception:
            return {"total_habits": 0, "total_recommendations": 0, "accepted_recommendations": 0, "top_actions_7d": []}


# ═══════════════════════════════════════════════════════════════
# IntentEngine - 统一入口
# ═══════════════════════════════════════════════════════════════

class IntentEngine:
    """
    意图引擎统一入口 v2
    三层解析: 快速匹配 → 模糊推理 → AI兜底
    + 对话记忆 + 指代消解 + 情感感知 + 联动引擎 + 节能顾问
    """

    def __init__(self, get_context_fn: Callable = None, get_status_fn: Callable = None,
                 db_path: str | Path = None, log_fn: Callable = None, tts_fn: Callable = None):
        self._log = log_fn or print
        self._tts = tts_fn or (lambda t: None)

        # 设备注册中心
        self._registry = DeviceRegistry(db_path, log_fn)

        # 意图匹配器(接入注册中心的动态规则)
        self._matcher = IntentMatcher(self._registry)

        # 模糊推理器
        self._reasoner = FuzzyReasoner(get_context_fn, log_fn=log_fn or print)

        # 对话记忆
        self._memory = ConversationMemory(db_path, log_fn, max_turns=20)

        # 情感分析器
        self._emotion = EmotionAnalyzer()

        # 联动引擎
        self._linkage = LinkageEngine(db_path, log_fn, executor_fn=None, registry=self._registry)

        # 节能顾问
        self._energy = EnergyAdvisor(db_path, log_fn, get_context_fn, self._registry)

        # 异常检测器
        self._anomaly = None
        if db_path:
            self._anomaly = AnomalyDetector(db_path, get_status_fn, log_fn, tts_fn)

        # 习惯学习器
        self._habit = None
        if db_path:
            self._habit = HabitLearner(db_path, log_fn)

    def parse(self, text: str, execute: bool = False, executor: Callable = None) -> dict:
        """
        解析用户输入

        Args:
            text: 用户输入文本
            execute: 是否执行意图
            executor: 执行函数，签名为 executor(intent) -> result

        Returns:
            {
                "intent": {...},
                "executed": bool,
                "result": {...},
                "reply": str,
                "voice_text": str,
                "source": str,  # "fast" / "fuzzy" / "ai"
                "emotion": {...},  # 情感分析结果
                "context_resolved": {...}|None,  # 指代消解结果
            }
        """
        text = text.strip()
        if not text:
            return {"intent": None, "executed": False, "reply": "请输入消息", "source": "none"}

        # 情感分析
        emotion_result = self._emotion.analyze(text)

        # 指代消解
        context_resolved = self._memory.resolve_reference(text)
        resolved_text = text
        if context_resolved and context_resolved.get("resolved_text"):
            resolved_text = context_resolved["resolved_text"]
            self._log(f"[MEMORY] 指代消解: '{text}' → '{resolved_text}'")

        # 第一层: 快速意图匹配
        intent = self._matcher.match(resolved_text)
        if intent:
            self._log(f"[INTENT] 快速匹配: type={intent['type']} conf={intent['confidence']}")
            # 记录对话
            self._memory.add("user", text, intent)
            result = self._try_execute(intent, execute, executor, emotion_result)
            result["source"] = "fast"
            result["emotion"] = emotion_result
            result["context_resolved"] = context_resolved
            return result

        # 第二层: 模糊意图推理
        intent = self._reasoner.reason(resolved_text)
        if intent:
            self._log(f"[INTENT] 模糊推理: type={intent.get('type','suggestion')} conf={intent.get('confidence',0)}")
            self._memory.add("user", text, intent)
            result = self._try_execute(intent, execute, executor, emotion_result)
            result["source"] = "fuzzy"
            result["emotion"] = emotion_result
            result["context_resolved"] = context_resolved
            return result

        # 第三层: AI 兜底
        self._log(f"[INTENT] 未匹配，AI兜底: text={text[:30]}")
        self._memory.add("user", text, None)
        return {
            "intent": {"type": "chat", "confidence": 0, "source": "fallback"},
            "executed": False,
            "reply": None,  # None 表示需要 AI 兜底
            "source": "ai",
            "emotion": emotion_result,
            "context_resolved": context_resolved,
        }

    def _try_execute(self, intent: dict, execute: bool, executor: Callable = None,
                     emotion_result: dict = None) -> dict:
        """尝试执行意图"""
        explanation = intent.get("explanation", "")
        itype = intent.get("type", "")

        if itype == "suggestion":
            self._tts(explanation)
            # 情感调整
            if emotion_result:
                explanation = self._emotion.apply_style(explanation, emotion_result)
            return {
                "intent": intent,
                "executed": False,
                "reply": explanation,
                "voice_text": explanation,
            }

        if not execute or not executor:
            return {
                "intent": intent,
                "executed": False,
                "reply": explanation or f"识别到意图: {itype}",
                "voice_text": explanation,
            }

        # 情感判断: 紧急情况直接执行，不确认
        if emotion_result and not self._emotion.should_execute_immediately(emotion_result):
            # 非紧急，正常执行
            pass

        try:
            exec_result = executor(intent)
            voice_text = explanation if explanation else "已执行"

            # 情感调整回复
            if emotion_result:
                voice_text = self._emotion.apply_style(voice_text, emotion_result)

            self._tts(voice_text)

            # 记录到习惯学习器
            if self._habit:
                if itype == "scene":
                    self._habit.record("scene", intent.get("scene_id", ""))
                elif itype in ("device_toggle", "device_control"):
                    self._habit.record(itype, intent.get("device_id", ""), intent.get("params"))

            # 触发联动引擎
            if itype in ("device_toggle", "device_control"):
                dev_id = intent.get("device_id", "")
                event = "on" if intent.get("isOn") else "off"
                self._linkage.on_device_change(dev_id, event)

            # 记录助手回复
            self._memory.add("assistant", voice_text, intent)

            return {
                "intent": intent,
                "executed": True,
                "result": exec_result,
                "reply": voice_text,
                "voice_text": voice_text,
            }
        except Exception as e:
            self._log(f"[INTENT] 执行失败: {e}")
            return {
                "intent": intent,
                "executed": False,
                "reply": f"执行失败: {e}",
                "voice_text": f"执行失败",
            }

    # ===== 对话记忆接口 =====
    def add_assistant_reply(self, text: str, intent: dict = None):
        """记录助手回复(用于AI兜底后的对话记录)"""
        self._memory.add("assistant", text, intent)

    def get_context_summary(self) -> str:
        """获取对话上下文摘要(用于AI prompt增强)"""
        return self._memory.get_context_summary()

    def clear_memory(self):
        """清空对话记忆"""
        self._memory.clear()

    # ===== 设备注册接口 =====
    def register_device(self, template: dict) -> dict:
        """注册新设备"""
        result = self._registry.register(template)
        if result.get("success"):
            # 刷新匹配器的动态规则
            self._matcher._refresh_dynamic()
        return result

    def unregister_device(self, device_id: str) -> dict:
        """注销设备"""
        result = self._registry.unregister(device_id)
        if result.get("success"):
            self._matcher._refresh_dynamic()
        return result

    def list_device_templates(self) -> list[dict]:
        """列出所有设备模板"""
        return self._registry.list_templates()

    # ===== 联动引擎接口 =====
    def get_linkage_rules(self) -> list[dict]:
        """获取联动规则"""
        return self._linkage.get_rules()

    def get_linkage_log(self, limit: int = 50) -> list[dict]:
        """获取联动执行日志"""
        return self._linkage.get_log(limit)

    def set_linkage_executor(self, executor_fn: Callable):
        """设置联动执行函数"""
        self._linkage._executor = executor_fn

    # ===== 节能顾问接口 =====
    def get_energy_consumption(self) -> dict:
        """获取当前能耗"""
        return self._energy.get_current_consumption()

    def get_energy_waste(self) -> list[dict]:
        """获取浪费分析"""
        return self._energy.analyze_waste()

    def get_energy_report(self) -> dict:
        """获取每日能耗报告"""
        return self._energy.get_daily_report()

    def get_energy_suggestions(self, limit: int = 10) -> list[dict]:
        """获取节能建议"""
        return self._energy.get_suggestions(limit)

    # ===== 情感分析接口 =====
    def analyze_emotion(self, text: str) -> dict:
        """分析文本情绪"""
        return self._emotion.analyze(text)

    # ===== 原有接口 =====
    def start_anomaly_detector(self, interval: float = 30.0):
        if self._anomaly:
            self._anomaly.start(interval)

    def get_anomaly_events(self, limit: int = 50) -> list[dict]:
        if self._anomaly:
            return self._anomaly.get_events(limit)
        return []

    def get_recommendations(self, limit: int = 10) -> list[dict]:
        if self._habit:
            return self._habit.get_recommendations(limit)
        return []

    def accept_recommendation(self, rec_id: int) -> bool:
        if self._habit:
            return self._habit.accept_recommendation(rec_id)
        return False

    def dismiss_recommendation(self, rec_id: int) -> bool:
        if self._habit:
            return self._habit.dismiss_recommendation(rec_id)
        return False

    def get_habit_stats(self) -> dict:
        if self._habit:
            return self._habit.get_stats()
        return {}

    def record_habit(self, action_type: str, action_id: str, action_params: dict = None):
        if self._habit:
            self._habit.record(action_type, action_id, action_params)


# ═══════════════════════════════════════════════════════════════
# AI System Prompt 增强
# ═══════════════════════════════════════════════════════════════

AI_INTENT_PROMPT = """
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
- <<QUERY:energy>>       查能耗

### 规则
1. 先用自然语言回复用户，再附上控制指令
2. 一个回复可以包含多个指令
3. 不确定时不要输出指令，只回复文字
4. 设备离线时不要输出控制指令
5. 门禁操作需要密码，不要自动开门
6. 注意用户情绪: 紧急时简短确认，舒适时可以闲聊
7. 如果用户说"它""这个""再调低一点"，参考上下文理解指代

### 设备列表
{device_list}

### 场景列表
{scene_list}

### 对话上下文
{conversation_context}
"""


def build_ai_intent_prompt(context_summary: str = "") -> str:
    """构建带设备能力+对话上下文的 AI intent prompt"""
    device_lines = []
    for dev_id, caps in DEVICE_CAPABILITIES.items():
        name = DEVICE_NAMES.get(dev_id, dev_id)
        cap_strs = [f"{c['action']}({', '.join(f'{k}={v}' for k,v in c.get('params',{}).items())})" for c in caps]
        device_lines.append(f"- {dev_id}({name}): {', '.join(cap_strs)}")

    scene_lines = []
    try:
        from scenes.scene_config import SCENE_META
        for sid, meta in SCENE_META.items():
            scene_lines.append(f"- {sid}({meta['name']}): {meta['desc']}")
    except ImportError:
        scene_lines = ["- s1(回家) - s2(离家) - s3(睡眠) - s4(观影) - s5(用餐)"]

    return AI_INTENT_PROMPT.format(
        device_list="\n".join(device_lines),
        scene_list="\n".join(scene_lines),
        conversation_context=context_summary or "无上下文",
    )


def parse_ai_commands(reply: str) -> list[dict]:
    """解析 AI 回复中的控制指令"""
    commands = []

    for m in re.finditer(r'<<DEVICE:([\w_]+):(\w+):(\{[^}]*\})>>', reply):
        dev_id, action, params_str = m.group(1), m.group(2), m.group(3)
        try:
            params = json.loads(params_str)
        except json.JSONDecodeError:
            params = {}
        commands.append({"type": "device", "device_id": dev_id, "action": action, "params": params})

    for m in re.finditer(r'<<SCENE:([\w_]+)>>', reply):
        commands.append({"type": "scene", "scene_id": m.group(1)})

    for m in re.finditer(r'<<QUERY:([\w_]+)>>', reply):
        commands.append({"type": "query", "query_type": m.group(1)})

    for m in re.finditer(r'<<SCHEDULE:([^:>]+):(\{.+?\})>>', reply):
        time_expr = m.group(1).strip()
        try:
            action = json.loads(m.group(2))
        except json.JSONDecodeError:
            action = {"type": "unknown", "raw": m.group(2)}
        commands.append({"type": "schedule", "time_expr": time_expr, "action": action})

    for m in re.finditer(r'<<PUSH:(high|medium|low):([^:>]+):(.+?)>>', reply):
        commands.append({"type": "push", "importance": m.group(1), "title": m.group(2).strip(), "message": m.group(3).strip()})

    return commands


def strip_ai_commands(reply: str) -> str:
    """移除 AI 回复中的控制指令标记"""
    text = re.sub(r'<<DEVICE:[\w_]+:\w+:\{[^}]*\}>>', '', reply)
    text = re.sub(r'<<SCENE:[\w_]+>>', '', text)
    text = re.sub(r'<<QUERY:[\w_]+>>', '', text)
    text = re.sub(r'<<SCHEDULE:[^>]+>>', '', text)
    text = re.sub(r'<<PUSH:(?:high|medium|low):[^>]+>>', '', text)
    text = re.sub(r'<<CHART:[^>]*>>', "", text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    return text.strip()
