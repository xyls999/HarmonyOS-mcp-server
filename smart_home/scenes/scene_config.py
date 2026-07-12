"""
场景配置 · 与前端 mockData.ets 完全对齐
纯标准库，无需第三方依赖
"""

# ===== 场景动作 =====
# (device_id, is_on, primary_value_or_None)
SCENE_ACTIONS = {
    # 回家 s1 — 4台设备
    "s1": [
        ("light_01", True, 80),    # 客厅主灯 开 80%
        ("ac_01", True, 24),       # 客厅空调 开 24°C
        ("curtain_01", True, 100), # 智能窗帘 全开
        ("door_01", True, None),   # 客厅大门 解锁
    ],
    # 离家 s2 — 12台设备
    "s2": [
        ("light_01", False, None),     # 客厅主灯 关
        ("light_02", False, None),     # 厨房灯 关
        ("light_03", False, None),     # 卧室灯 关
        ("light_04", False, None),     # 卫生间灯 关
        ("light_05", False, None),     # 客厅氛围灯 关
        ("ac_01", False, None),        # 客厅空调 关
        ("fan_01", False, None),       # 客厅吊扇 关
        ("fan_02", False, None),       # 换气扇 关
        ("exhaust_01", False, None),   # 抽风机 关
        ("curtain_01", False, 0),      # 窗帘 全关
        ("door_01", False, None),      # 大门 锁定
        ("nfc_01", False, None),       # NFC门禁 关
    ],
    # 睡眠 s3 — 7台设备
    "s3": [
        ("light_01", False, None),     # 客厅主灯 关
        ("light_02", False, None),     # 厨房灯 关
        ("light_03", False, None),     # 卧室灯 关
        ("light_04", False, None),     # 卫生间灯 关
        ("light_05", False, None),     # 客厅氛围灯 关
        ("ac_01", True, 26),           # 空调 26°C
        ("curtain_01", False, 0),      # 窗帘 全关
    ],
    # 观影 s4 — 4台设备
    "s4": [
        ("light_01", True, 20),        # 客厅主灯 20%
        ("light_05", False, None),     # 客厅氛围灯 关
        ("curtain_01", False, 0),      # 窗帘 全关
        ("ac_01", True, 24),           # 空调 24°C
    ],
    # 用餐 s5 — 3台设备
    "s5": [
        ("light_01", True, 60),        # 客厅主灯 60%
        ("light_02", True, 80),        # 厨房灯 80%
        ("exhaust_01", True, 1),       # 抽风机 开
    ],
}

SCENE_META = {
    "s1": {"name": "回家", "icon": "house_fill", "color": "#22D3EE", "desc": "回家模式：打开客厅灯(80%)、空调(24°C制冷)、窗帘(全开)、解锁门禁"},
    "s2": {"name": "离家", "icon": "figure_walk", "color": "#F97316", "desc": "离家模式：关闭所有灯光(5盏)、空调、风扇(3台)、窗帘，锁门，关闭NFC"},
    "s3": {"name": "睡眠", "icon": "moon_fill", "color": "#818CF8", "desc": "睡眠模式：关闭所有灯光，空调调至26度，关闭窗帘"},
    "s4": {"name": "观影", "icon": "film", "color": "#F472B6", "desc": "观影模式：客厅灯调暗至20%，关闭氛围灯和窗帘，空调保持"},
    "s5": {"name": "用餐", "icon": "fork_knife", "color": "#34D399", "desc": "用餐模式：客厅灯调至60%，厨房灯开，抽风机开"},
}

# 场景别名映射（用于自然语言匹配）
SCENE_ALIASES = {
    "s1": ["回家", "回家模式", "到家", "我回来了", "welcome", "home"],
    "s2": ["离家", "离家模式", "出门", "走了", "我要出门", "leave", "away"],
    "s3": ["睡眠", "睡眠模式", "睡觉", "晚安", "休息", "就寝", "sleep", "night"],
    "s4": ["观影", "观影模式", "看电影", "电视", "电影", "movie", "film"],
    "s5": ["用餐", "用餐模式", "吃饭", "晚餐", "午餐", "dinner", "meal"],
}


def get_scene_id_by_name(name):
    """通过名称或别名获取场景ID"""
    name_lower = name.lower().strip()
    for sid, aliases in SCENE_ALIASES.items():
        for alias in aliases:
            if name_lower == alias.lower():
                return sid
    # 模糊匹配
    for sid, aliases in SCENE_ALIASES.items():
        for alias in aliases:
            if alias.lower() in name_lower or name_lower in alias.lower():
                return sid
    return None


def get_scene_summary():
    """获取所有场景摘要"""
    lines = ["可用场景:"]
    for sid, meta in SCENE_META.items():
        actions = SCENE_ACTIONS[sid]
        on_count = sum(1 for a in actions if a[1])
        off_count = sum(1 for a in actions if not a[1])
        lines.append(f"  {meta['name']}({sid}): {meta['desc']} | 开{on_count}台/关{off_count}台设备")
    return "\n".join(lines)
