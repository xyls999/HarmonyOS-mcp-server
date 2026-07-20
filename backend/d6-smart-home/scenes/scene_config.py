"""只使用现场真实设备的预置场景和中文短语匹配。"""
from __future__ import annotations


SCENE_COMMANDS = {
    "s1": [
        {"type": "device", "device_id": "door_01", "action": "on", "params": {}},
        {"type": "device", "device_id": "light_01", "action": "set_brightness", "params": {"value": 80, "brightness": 80}},
        {"type": "device", "device_id": "curtain_01", "action": "set_position", "params": {"value": 100, "position": 100}},
    ],
    "s2": [
        *[{"type": "device", "device_id": device_id, "action": "off", "params": {}}
          for device_id in ("light_01", "light_02", "light_03", "light_04", "ac_01", "fan_02")],
        {"type": "device", "device_id": "curtain_01", "action": "set_position", "params": {"value": 0, "position": 0}},
        {"type": "device", "device_id": "door_01", "action": "off", "params": {}},
    ],
    "s3": [
        *[{"type": "device", "device_id": device_id, "action": "off", "params": {}}
          for device_id in ("light_01", "light_02", "light_03", "light_04", "fan_02")],
        {"type": "device", "device_id": "curtain_01", "action": "set_position", "params": {"value": 0, "position": 0}},
        {"type": "device", "device_id": "ac_01", "action": "preset", "params": {"profile": "COOL_26_AUTO"}},
    ],
    "s4": [
        {"type": "device", "device_id": "light_01", "action": "set_brightness", "params": {"value": 20, "brightness": 20}},
        {"type": "device", "device_id": "curtain_01", "action": "set_position", "params": {"value": 0, "position": 0}},
    ],
    "s5": [
        {"type": "device", "device_id": "light_01", "action": "set_brightness", "params": {"value": 60, "brightness": 60}},
        {"type": "device", "device_id": "light_02", "action": "set_brightness", "params": {"value": 80, "brightness": 80}},
    ],
    "s6": [
        {"type": "device", "device_id": "curtain_01", "action": "set_position", "params": {"value": 100, "position": 100}},
        {"type": "device", "device_id": "light_03", "action": "set_brightness", "params": {"value": 50, "brightness": 50}},
    ],
}

SCENE_META = {
    "s1": {"name": "回家", "icon": "house_fill", "color": "#4D8B70", "desc": "开门、打开客厅灯并拉开窗帘"},
    "s2": {"name": "离家", "icon": "figure_walk", "color": "#4D8B70", "desc": "关闭灯光、空调和换气扇，合帘并关门"},
    "s3": {"name": "睡眠", "icon": "moon_fill", "color": "#4D8B70", "desc": "关闭灯光和换气扇，合帘并将空调设为 26℃"},
    "s4": {"name": "观影", "icon": "film", "color": "#4D8B70", "desc": "调暗客厅灯并合上窗帘"},
    "s5": {"name": "用餐", "icon": "fork_knife", "color": "#4D8B70", "desc": "调整客厅和厨房照明"},
    "s6": {"name": "起床", "icon": "sun_max", "color": "#4D8B70", "desc": "拉开窗帘并打开卧室灯"},
}

SCENE_ALIASES = {
    "s1": ("回家", "到家", "我回来了", "开门回家"),
    "s2": ("离家", "出门", "我要出门", "我走了", "离开家"),
    "s3": ("睡眠", "睡觉", "晚安", "就寝", "准备休息"),
    "s4": ("观影", "看电影", "电影模式", "准备看电影"),
    "s5": ("用餐", "吃饭", "开饭", "开始吃饭"),
    "s6": ("起床", "早安", "我醒了", "早上好"),
}


def match_prepared_scene(text: str) -> str | None:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return None
    for scene_id, aliases in SCENE_ALIASES.items():
        if any(alias.lower() in normalized for alias in aliases):
            return scene_id
    return None


def get_scene_id_by_name(name: str) -> str | None:
    return match_prepared_scene(name)


def get_scene_commands(scene_id: str) -> list[dict]:
    return [dict(command) for command in SCENE_COMMANDS.get(str(scene_id), [])]


SCENE_ACTIONS = {
    scene_id: [
        (command["device_id"], command["action"] != "off", command.get("params", {}).get("value"))
        for command in commands
    ]
    for scene_id, commands in SCENE_COMMANDS.items()
}
