"""
本地 RAG 服务 v2 · 强命中命令 + 固定格式输出
纯标准库实现（TF-IDF + 关键词匹配 + 精确命令映射）

v2 变更:
  - 增加精确命令映射表，确保设备控制命令100%命中
  - 增加区域状态查询关键词
  - 增加房间→设备关联映射
  - 所有命令关键词完全对齐交接文档
"""
from __future__ import annotations
import json
import math
import os
import re
from collections import Counter
from pathlib import Path


# ===== 精确命令映射表（优先级最高） =====
EXACT_COMMAND_MAP = {
    # 客厅灯
    "开客厅灯": {"device": "light_01", "action": "on", "room": "客厅"},
    "关客厅灯": {"device": "light_01", "action": "off", "room": "客厅"},
    "客厅灯开": {"device": "light_01", "action": "on", "room": "客厅"},
    "客厅灯关": {"device": "light_01", "action": "off", "room": "客厅"},
    "打开主灯": {"device": "light_01", "action": "on", "room": "客厅"},
    "关闭主灯": {"device": "light_01", "action": "off", "room": "客厅"},
    "客厅灯亮度": {"device": "light_01", "action": "query", "room": "客厅"},
    # 客厅氛围灯
    "开氛围灯": {"device": "light_05", "action": "on", "room": "客厅"},
    "关氛围灯": {"device": "light_05", "action": "off", "room": "客厅"},
    # 空调
    "开空调": {"device": "ac_01", "action": "on", "room": "客厅"},
    "关空调": {"device": "ac_01", "action": "off", "room": "客厅"},
    "空调开": {"device": "ac_01", "action": "on", "room": "客厅"},
    "空调关": {"device": "ac_01", "action": "off", "room": "客厅"},
    "打开空调": {"device": "ac_01", "action": "on", "room": "客厅"},
    "关闭空调": {"device": "ac_01", "action": "off", "room": "客厅"},
    "空调温度": {"device": "ac_01", "action": "query", "room": "客厅"},
    "空调状态": {"device": "ac_01", "action": "query", "room": "客厅"},
    # 门禁
    "开门": {"device": "door_01", "action": "on", "room": "客厅"},
    "关门": {"device": "door_01", "action": "off", "room": "客厅"},
    "打开门": {"device": "door_01", "action": "on", "room": "客厅"},
    "关上门": {"device": "door_01", "action": "off", "room": "客厅"},
    "解锁": {"device": "door_01", "action": "on", "room": "客厅"},
    "锁门": {"device": "door_01", "action": "off", "room": "客厅"},
    "门禁": {"device": "door_01", "action": "query", "room": "客厅"},
    # 蜂鸣器
    "开警报": {"device": "alarm_01", "action": "on", "room": "客厅"},
    "关警报": {"device": "alarm_01", "action": "off", "room": "客厅"},
    "启动警报": {"device": "alarm_01", "action": "on", "room": "客厅"},
    "关闭警报": {"device": "alarm_01", "action": "off", "room": "客厅"},
    "蜂鸣器开": {"device": "alarm_01", "action": "on", "room": "客厅"},
    "蜂鸣器关": {"device": "alarm_01", "action": "off", "room": "客厅"},
    # 厨房灯
    "开厨房灯": {"device": "light_02", "action": "on", "room": "厨房"},
    "关厨房灯": {"device": "light_02", "action": "off", "room": "厨房"},
    "厨房灯开": {"device": "light_02", "action": "on", "room": "厨房"},
    "厨房灯关": {"device": "light_02", "action": "off", "room": "厨房"},
    # 卫生间灯
    "开卫生间灯": {"device": "light_04", "action": "on", "room": "卫生间"},
    "关卫生间灯": {"device": "light_04", "action": "off", "room": "卫生间"},
    # 换气扇
    "开换气扇": {"device": "fan_02", "action": "on", "room": "卫生间"},
    "关换气扇": {"device": "fan_02", "action": "off", "room": "卫生间"},
    "开排风扇": {"device": "fan_02", "action": "on", "room": "卫生间"},
    "关排风扇": {"device": "fan_02", "action": "off", "room": "卫生间"},
    # 卧室灯
    "开卧室灯": {"device": "light_03", "action": "on", "room": "卧室"},
    "关卧室灯": {"device": "light_03", "action": "off", "room": "卧室"},
    # 窗帘
    "开窗帘": {"device": "curtain_01", "action": "on", "room": "卧室"},
    "关窗帘": {"device": "curtain_01", "action": "off", "room": "卧室"},
    "打开窗帘": {"device": "curtain_01", "action": "on", "room": "卧室"},
    "关闭窗帘": {"device": "curtain_01", "action": "off", "room": "卧室"},
    "窗帘全开": {"device": "curtain_01", "action": "on", "room": "卧室"},
    "窗帘全关": {"device": "curtain_01", "action": "off", "room": "卧室"},
    "窗帘位置": {"device": "curtain_01", "action": "query", "room": "卧室"},
    "窗帘状态": {"device": "curtain_01", "action": "query", "room": "卧室"},
    # 状态查询
    "温度": {"sensor": "temp_01", "action": "query", "room": "客厅"},
    "湿度": {"sensor": "humid_01", "action": "query", "room": "客厅"},
    "室内温度": {"sensor": "temp_01", "action": "query", "room": "客厅"},
    "室内湿度": {"sensor": "humid_01", "action": "query", "room": "客厅"},
    "现在温度": {"sensor": "temp_01", "action": "query", "room": "客厅"},
    "现在湿度": {"sensor": "humid_01", "action": "query", "room": "客厅"},
    "烟雾": {"sensor": "smoke_01", "action": "query", "room": "厨房"},
    "烟雾检测": {"sensor": "smoke_01", "action": "query", "room": "厨房"},
    "厨房安全": {"sensor": "smoke_01", "action": "query", "room": "厨房"},
    "热敏": {"sensor": "heat_01", "action": "query", "room": "厨房"},
    "设备状态": {"action": "status_all"},
    "所有设备": {"action": "status_all"},
    "检查设备": {"action": "status_all"},
    "全屋状态": {"action": "status_all"},
    "全部状态": {"action": "status_all"},
}

# ===== 知识库数据 =====
KNOWLEDGE = [
    # 设备控制命令 - 客厅
    {"id": "cmd_light_on", "text": "打开灯 开灯 灯光开启 把灯打开 turn on light 亮灯", "cat": "device_control", "meta": {"device_type": "light", "action": "on"}},
    {"id": "cmd_light_off", "text": "关灯 关闭灯 灯光关闭 把灯关掉 turn off light 灭灯", "cat": "device_control", "meta": {"device_type": "light", "action": "off"}},
    {"id": "cmd_light_up", "text": "调亮灯 灯光调亮 增加亮度 灯光亮度调到 brightness up 亮一点", "cat": "device_control", "meta": {"device_type": "light", "action": "set_brightness", "dir": "up"}},
    {"id": "cmd_light_down", "text": "调暗灯 灯光调暗 降低亮度 灯光暗一点 dim brightness down 暗一点", "cat": "device_control", "meta": {"device_type": "light", "action": "set_brightness", "dir": "down"}},
    {"id": "cmd_ac_on", "text": "打开空调 开空调 空调开启 turn on AC air conditioner 制冷", "cat": "device_control", "meta": {"device_type": "ac", "action": "on"}},
    {"id": "cmd_ac_off", "text": "关空调 关闭空调 空调关闭 turn off AC", "cat": "device_control", "meta": {"device_type": "ac", "action": "off"}},
    {"id": "cmd_ac_temp_up", "text": "空调温度调高 升温 温度升高 温度加 temperature up", "cat": "device_control", "meta": {"device_type": "ac", "action": "set_temp", "dir": "up"}},
    {"id": "cmd_ac_temp_down", "text": "空调温度调低 降温 温度降低 温度减 temperature down", "cat": "device_control", "meta": {"device_type": "ac", "action": "set_temp", "dir": "down"}},
    {"id": "cmd_ac_cool", "text": "制冷模式 空调制冷 冷气 cool mode", "cat": "device_control", "meta": {"device_type": "ac", "action": "set_mode", "mode": "制冷"}},
    {"id": "cmd_ac_heat", "text": "制热模式 空调制热 暖气 heat mode", "cat": "device_control", "meta": {"device_type": "ac", "action": "set_mode", "mode": "制热"}},
    {"id": "cmd_fan_on", "text": "打开风扇 开风扇 风扇开启 turn on fan 换气扇开 排风扇开", "cat": "device_control", "meta": {"device_type": "fan", "action": "on"}},
    {"id": "cmd_fan_off", "text": "关风扇 关闭风扇 turn off fan 换气扇关 排风扇关", "cat": "device_control", "meta": {"device_type": "fan", "action": "off"}},
    {"id": "cmd_fan_up", "text": "风扇加速 风速加大 档位调高 fan speed up", "cat": "device_control", "meta": {"device_type": "fan", "action": "set_speed", "dir": "up"}},
    {"id": "cmd_fan_down", "text": "风扇减速 风速减小 档位调低 fan speed down", "cat": "device_control", "meta": {"device_type": "fan", "action": "set_speed", "dir": "down"}},
    {"id": "cmd_door_open", "text": "开门 开锁 解锁门 门禁打开 unlock open door", "cat": "device_control", "meta": {"device_type": "door", "action": "on"}},
    {"id": "cmd_door_close", "text": "关门 锁门 门禁锁定 lock close door", "cat": "device_control", "meta": {"device_type": "door", "action": "off"}},
    {"id": "cmd_curtain_open", "text": "打开窗帘 窗帘全开 拉开窗帘 open curtain", "cat": "device_control", "meta": {"device_type": "curtain", "action": "on"}},
    {"id": "cmd_curtain_close", "text": "关闭窗帘 窗帘全关 拉上窗帘 close curtain", "cat": "device_control", "meta": {"device_type": "curtain", "action": "off"}},
    {"id": "cmd_alarm_on", "text": "开启警报 蜂鸣器开 启动报警 alarm on", "cat": "device_control", "meta": {"device_type": "alarm", "action": "on"}},
    {"id": "cmd_alarm_off", "text": "关闭警报 蜂鸣器关 取消报警 alarm off", "cat": "device_control", "meta": {"device_type": "alarm", "action": "off"}},
    # 场景触发
    {"id": "scene_home", "text": "回家模式 回家 我回来了 到家 welcome home", "cat": "scene", "meta": {"scene_id": "s1", "scene_name": "回家"}},
    {"id": "scene_away", "text": "离家模式 离家 出门 走了 away leave", "cat": "scene", "meta": {"scene_id": "s2", "scene_name": "离家"}},
    {"id": "scene_sleep", "text": "睡眠模式 睡觉 晚安 休息 就寝 sleep night", "cat": "scene", "meta": {"scene_id": "s3", "scene_name": "睡眠"}},
    {"id": "scene_movie", "text": "观影模式 看电影 电视时间 电影模式 movie film", "cat": "scene", "meta": {"scene_id": "s4", "scene_name": "观影"}},
    {"id": "scene_dinner", "text": "用餐模式 吃饭 晚餐 午餐 dinner meal", "cat": "scene", "meta": {"scene_id": "s5", "scene_name": "用餐"}},
    # 传感器查询 - 按交接文档格式
    {"id": "q_temp", "text": "现在温度多少 室内温度 温度查询 当前温度 temperature 多少度", "cat": "sensor", "meta": {"sensor_type": "temperature", "format": "温度: {X}°C"}},
    {"id": "q_humid", "text": "现在湿度多少 室内湿度 湿度查询 当前湿度 humidity", "cat": "sensor", "meta": {"sensor_type": "humidity", "format": "湿度: {X}%RH"}},
    {"id": "q_air", "text": "空气质量 PM2.5 空气指数 AQI air quality 厨房安全", "cat": "sensor", "meta": {"sensor_type": "air_quality", "format": "空气质量: {X}"}},
    {"id": "q_smoke", "text": "烟雾检测 有没有烟雾 厨房安全 smoke 烟雾报警 烟雾传感器", "cat": "sensor", "meta": {"sensor_type": "smoke", "format": "烟雾: 正常/报警"}},
    {"id": "q_heat", "text": "热敏温度 热敏火灾 热敏传感器 thermal 过热", "cat": "sensor", "meta": {"sensor_type": "heat", "format": "热敏: {X}mV"}},
    {"id": "q_pir", "text": "有没有人 人体感应 有人吗 presence PIR", "cat": "sensor", "meta": {"sensor_type": "pir", "format": "人体感应: 有人/无人"}},
    {"id": "q_curtain", "text": "窗帘位置 窗帘状态 窗帘开多少 curtain position", "cat": "sensor", "meta": {"sensor_type": "curtain_position", "format": "窗帘位置: {X}%"}},
    {"id": "q_fan", "text": "换气扇状态 排风扇状态 风扇转速 fan status", "cat": "sensor", "meta": {"sensor_type": "fan_status", "format": "换气扇: 开/关(风速{X}%)"}},
    # 全屋状态
    {"id": "q_all_status", "text": "设备状态 所有设备 设备列表 哪些设备在线 全屋状态 全部状态 check all status", "cat": "sensor", "meta": {"sensor_type": "all_status", "format": "全屋状态报告"}},
    # FAQ
    {"id": "faq_weather", "text": "今天天气 天气预报 外面天气 weather forecast", "cat": "faq", "meta": {"tool": "get_local_weather"}},
    {"id": "faq_scenes", "text": "有哪些场景 可用场景 场景列表 scene list", "cat": "faq", "meta": {"tool": "list_scenes"}},
    {"id": "faq_alloff", "text": "全部关闭 关掉所有设备 一键关闭 all off", "cat": "faq", "meta": {"scene_id": "s2"}},
    {"id": "faq_lights_off", "text": "关掉所有灯 全部关灯 all lights off", "cat": "faq", "meta": {"action": "lights_off"}},
    # 房间
    {"id": "room_living", "text": "客厅 客厅灯 客厅空调 客厅风扇 客厅温度 living room", "cat": "room", "meta": {"room": "客厅", "devices": ["light_01", "light_05", "ac_01", "door_01", "alarm_01", "camera_01"], "sensors": ["temp_01", "humid_01"]}},
    {"id": "room_kitchen", "text": "厨房 厨房灯 抽风机 kitchen 厨房安全", "cat": "room", "meta": {"room": "厨房", "devices": ["light_02", "exhaust_01"], "sensors": ["smoke_01", "heat_01", "air_01"]}},
    {"id": "room_bedroom", "text": "卧室 卧室灯 卧室窗帘 bedroom", "cat": "room", "meta": {"room": "卧室", "devices": ["light_03", "curtain_01"], "sensors": []}},
    {"id": "room_bath", "text": "卫生间 卫生间灯 换气扇 排风扇 bathroom", "cat": "room", "meta": {"room": "卫生间", "devices": ["light_04", "fan_02"], "sensors": []}},
    {"id": "room_out", "text": "室外 门口 NFC门禁 outdoor", "cat": "room", "meta": {"room": "室外", "devices": ["nfc_01"], "sensors": ["door_s_01"]}},
    # 报警联动
    {"id": "alarm_linkage", "text": "报警联动 厨房报警 蜂鸣器联动 烟雾报警联动 alarm linkage", "cat": "faq", "meta": {"tool": "alarm_linkage", "desc": "厨房报警上升沿自动触发客厅蜂鸣器，恢复后自动关闭"}},
]

FIXED_REPLIES = [
    {"keyword": "ciallo", "reply": "Ciallo～(∠・ω< )⌒★"},
]


def _tokenize(text):
    """简单分词：中文按字拆分，英文按空格拆分"""
    tokens = []
    for word in re.findall(r'[a-zA-Z]+', text.lower()):
        tokens.append(word)
    cn = re.findall(r'[一-鿿]+', text)
    for segment in cn:
        for i in range(len(segment)):
            tokens.append(segment[i])
            if i + 1 < len(segment):
                tokens.append(segment[i:i+2])
    return tokens


class SimpleRAG:
    """纯标准库的简易 RAG：精确映射 + TF-IDF + 关键词匹配"""

    def __init__(self):
        self.docs = KNOWLEDGE
        self._idf = {}
        self._doc_tf = []
        self._build_index()

    def _build_index(self):
        all_tokens = Counter()
        doc_count = len(self.docs)
        for doc in self.docs:
            tokens = _tokenize(doc["text"])
            tf = Counter(tokens)
            self._doc_tf.append(tf)
            for t in set(tokens):
                all_tokens[t] += 1
        for t, df in all_tokens.items():
            self._idf[t] = math.log((doc_count + 1) / (df + 1)) + 1

    def search(self, query, n=5, category=None):
        q_tokens = _tokenize(query)
        q_tf = Counter(q_tokens)
        scores = []
        for i, doc in enumerate(self.docs):
            if category and doc["cat"] != category:
                continue
            score = 0
            for t in q_tokens:
                if t in self._doc_tf[i]:
                    score += q_tf[t] * self._doc_tf[i][t] * self._idf.get(t, 1)
            for t in q_tokens:
                if t in doc["text"].lower():
                    score += 2.0
            scores.append((score, i))
        scores.sort(reverse=True)
        results = []
        for score, idx in scores[:n]:
            if score > 0:
                results.append({
                    "text": self.docs[idx]["text"],
                    "category": self.docs[idx]["cat"],
                    "meta": self.docs[idx]["meta"],
                    "score": score,
                })
        return results

    def search_scene(self, query):
        results = self.search(query, n=3, category="scene")
        if results and results[0]["score"] > 1.0:
            return results[0]["meta"]
        return None

    def match_reply(self, query):
        q = (query or "").lower()
        for item in FIXED_REPLIES:
            if item["keyword"] in q:
                return item["reply"]
        return None

    def search_device(self, query):
        results = self.search(query, n=3, category="device_control")
        if results and results[0]["score"] > 1.0:
            return results[0]["meta"]
        return None

    def exact_match(self, query):
        """精确命令匹配（优先级最高）"""
        q = query.strip()
        # 直接命中
        if q in EXACT_COMMAND_MAP:
            return EXACT_COMMAND_MAP[q]
        # 去掉标点后再试
        q_clean = re.sub(r'[，。！？、\s]', '', q)
        if q_clean in EXACT_COMMAND_MAP:
            return EXACT_COMMAND_MAP[q_clean]
        return None

    def get_context(self, query):
        # 先尝试精确匹配
        exact = self.exact_match(query)
        if exact:
            parts = []
            if "device" in exact:
                parts.append(f"精确设备:{exact['device']}→{exact['action']}")
            elif "sensor" in exact:
                parts.append(f"精确传感器:{exact['sensor']}→{exact['action']}")
            elif "action" in exact:
                parts.append(f"精确动作:{exact['action']}")
            if "room" in exact:
                parts.append(f"房间:{exact['room']}")
            return "精确:" + "|".join(parts)

        # 退回 TF-IDF
        results = self.search(query, n=3)
        if not results:
            return ""
        parts = []
        for r in results:
            cat = r["category"]
            meta = r["meta"]
            if cat == "scene":
                parts.append(f"场景:{meta.get('scene_name', '')}({meta.get('scene_id', '')})")
            elif cat == "device_control":
                parts.append(f"设备:{meta.get('device_type', '')}→{meta.get('action', '')}")
            elif cat == "sensor":
                parts.append(f"传感器:{meta.get('sensor_type', '')}")
            elif cat == "room":
                parts.append(f"房间:{meta.get('room', '')}")
            elif cat == "faq":
                parts.append(f"FAQ:工具{meta.get('tool', '')}")
        return "相关:" + "|".join(parts) if parts else ""

    def get_stats(self):
        return {
            "total": len(self.docs),
            "exact_commands": len(EXACT_COMMAND_MAP),
            "categories": list(set(d["cat"] for d in self.docs)),
        }
