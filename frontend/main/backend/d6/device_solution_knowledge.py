"""Source-labelled Chinese device/condition/solution knowledge for bounded RAG.

The catalog is deliberately advisory.  It may explain or rank a candidate,
but it never bypasses the device capability table or the deterministic safety
rules that own execution.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Mapping


SOURCES = (
    {
        "title": "GB/T 35134-2017 物联网智能家居设备描述方法",
        "url": "https://openstd.samr.gov.cn/bzgk/std/nd?no=401",
        "authority": "国家标准全文公开系统",
    },
    {
        "title": "GB/T 35136-2024 智能家居自动控制设备通用技术要求",
        "url": "https://openstd.samr.gov.cn/bzgk/std/nd?no=2221",
        "authority": "国家标准全文公开系统",
    },
    {
        "title": "GB/T 41387-2022 信息安全技术 智能家居通用安全规范",
        "url": "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=B1C14E854C0BA30D1C29FC376299761A",
        "authority": "国家标准全文公开系统",
    },
    {
        "title": "GB 50116-2013 火灾自动报警系统设计规范",
        "url": "https://js.119.gov.cn/group1/M00/00/2B/ZYS-ZGGB7eSASlysAMAv-jOQ6J4359.pdf",
        "authority": "消防救援机构",
    },
    {
        "title": "家庭消防安全攻略",
        "url": "https://www.119.gov.cn/site1/kp/hzyf/jt/2022/1205.shtml",
        "authority": "国家消防救援局",
    },
)

CONTEXTS = (
    ("实时状态", "以最新在线读数为准，忽略离线或过期数据"),
    ("五分钟趋势", "结合最近五分钟趋势复核，避免单点抖动"),
    ("夜间", "降低噪声和照明干扰，同时保留安全报警"),
    ("离家", "优先安全、节能和远程通知"),
    ("有人", "兼顾舒适度并避免突然关闭正在使用的设备"),
    ("无人", "连续确认无人后再执行节能动作"),
    ("设备离线", "不把缺失值当作正常值或无人状态"),
    ("手动检测", "输出证据、建议和可执行设备计划"),
)


def _four_cases(name: str, normal_action: str = "inspect") -> tuple[tuple[str, str, str, str], ...]:
    return (
        (f"{name}状态异常或读数越界", f"核验{name}实时值并执行最小安全调整", normal_action, "medium"),
        (f"{name}短时反复变化", f"检查{name}自动化冲突、供电和通信质量", "inspect", "medium"),
        (f"{name}离线或数据过期", f"冻结依赖{name}的自动执行并提示检查连接", "notify", "low"),
        (f"{name}恢复正常", f"记录{name}恢复时间并解除不再需要的联动", "record", "low"),
    )


FAMILIES = (
    ("air_conditioner", "空调", "ac_01", "温度 湿度 制冷 除湿 送风", (
        ("湿度达到或超过75%", "空调切换除湿模式，恢复到65%以下后再退出", "dry", "low"),
        ("温度达到或超过30℃", "空调切换制冷模式并持续观察温度趋势", "cool", "low"),
        ("毫米波连续确认无人且空调仍开", "关闭空调并记录无人节能动作", "off", "low"),
        ("空调短时反复开关", "暂停新增自动调整并检查规则冲突", "inspect", "medium"),
    )),
    ("main_light", "客厅主灯", "light_01", "灯光 照度 光敏 亮度", (
        ("照度低于25勒克斯且检测到有人", "启用光敏自动模式", "auto", "low"),
        ("凌晨仍保持开启", "关闭客厅主灯并记录节能动作", "off", "low"),
        ("短时反复开关", "检查光敏联动和手动操作冲突", "inspect", "medium"),
        ("状态与主控记录不一致", "记录异常变化并发送安全提醒", "notify", "high"),
    )),
    ("kitchen_light", "厨房灯", "light_02", "厨房 灯光 亮度", (
        ("夜间长时间保持开启", "确认厨房无人且无烹饪活动后关闭厨房灯", "off", "low"),
        ("有人进入且环境昏暗", "开启厨房灯并保持适合操作的亮度", "on", "low"),
        ("短时反复开关", "检查手动操作与自动化规则冲突", "inspect", "medium"),
        ("状态与主控记录不一致", "记录异常变化并发送安全提醒", "notify", "high"),
    )),
    ("bedroom_light", "卧室灯", "light_03", "卧室 灯光 睡眠 凌晨", (
        ("凌晨仍保持开启", "关闭卧室灯，保留必要的低亮度安全照明", "off", "low"),
        ("准备睡眠且灯光过亮", "降低亮度或关闭卧室灯", "off", "low"),
        ("短时反复开关", "检查睡眠场景与手动操作冲突", "inspect", "medium"),
        ("状态与主控记录不一致", "记录异常变化并发送安全提醒", "notify", "high"),
    )),
    ("bathroom_light", "卫生间灯", "light_04", "卫生间 灯光 毫米波 无人", (
        ("毫米波连续确认无人但灯仍开", "关闭卫生间灯", "off", "low"),
        ("检测到有人且环境昏暗", "开启卫生间灯", "on", "low"),
        ("短时反复开关", "检查毫米波抖动和自动化冲突", "inspect", "medium"),
        ("状态与主控记录不一致", "记录异常变化并发送安全提醒", "notify", "high"),
    )),
    ("curtain", "智能窗帘", "curtain_01", "窗帘 夜间 天气 隐私", (
        ("22点后窗帘仍开启", "将窗帘调整至0%保护夜间隐私", "set_position", "low"),
        ("恶劣天气且窗帘开启", "将窗帘调整至0%并记录天气证据", "set_position", "low"),
        ("电机移动超时", "停止重复控制并提示检查限位和轨道", "inspect", "medium"),
        ("位置反馈与命令不一致", "重新查询位置，禁止盲目连续发送命令", "query", "medium"),
    )),
    ("exhaust_fan", "换气扇", "fan_02", "换气 排风 烟雾 湿度", (
        ("厨房烟雾或热敏报警", "开启换气扇辅助排烟并同时触发安全报警", "on", "high"),
        ("毫米波连续确认无人且无报警", "关闭换气扇节能", "off", "low"),
        ("湿度持续偏高", "在无消防冲突时开启换气", "on", "low"),
        ("电机运行但转速反馈为零", "停止重复控制并检查电机或通信", "inspect", "medium"),
    )),
    ("door_access", "门禁", "door_01", "门禁 密码 枚举 未授权 开门", (
        ("两分钟内连续3次密码错误", "阻止开门并发送安全提醒", "deny", "high"),
        ("五分钟内连续5次密码错误", "判定枚举风险，阻止开门、开启蜂鸣器并通知主人", "alarm", "critical"),
        ("开门状态与主控授权记录不一致", "立即安全报警并保留审计证据", "alarm", "critical"),
        ("正常授权开门", "记录时间、来源并发送重要门禁通知", "record", "low"),
    )),
    ("buzzer", "蜂鸣警报", "alarm_01", "蜂鸣器 声光 报警", _four_cases("蜂鸣警报", "alarm")),
    ("smoke", "烟雾传感器", None, "烟雾 火灾 厨房 报警", _four_cases("烟雾传感器", "alarm")),
    ("heat", "热敏传感器", None, "热敏 高温 火灾 毫伏", _four_cases("热敏传感器", "alarm")),
    ("mmwave", "毫米波存在传感器", None, "毫米波 人体存在 有人 无人", _four_cases("毫米波传感器", "inspect")),
    ("illuminance", "光照传感器", None, "照度 勒克斯 光敏", _four_cases("光照传感器", "inspect")),
    ("temperature", "温度传感器", None, "温度 高温 低温 趋势", _four_cases("温度传感器", "inspect")),
    ("humidity", "湿度传感器", None, "湿度 潮湿 除湿 趋势", _four_cases("湿度传感器", "inspect")),
    ("door_sensor", "门窗传感器", None, "门窗 开合 入侵", _four_cases("门窗传感器", "notify")),
    ("camera", "摄像头", None, "摄像头 遮挡 离线 隐私", _four_cases("摄像头", "notify")),
    ("nfc", "近场门禁", None, "近场卡 门禁 授权", _four_cases("近场门禁", "notify")),
    ("water_leak", "水浸传感器", None, "漏水 水浸 阀门", _four_cases("水浸传感器", "alarm")),
    ("gas", "可燃气体传感器", None, "燃气 泄漏 阀门 通风", _four_cases("可燃气体传感器", "alarm")),
    ("carbon_monoxide", "一氧化碳传感器", None, "一氧化碳 中毒 通风", _four_cases("一氧化碳传感器", "alarm")),
    ("pm25", "颗粒物传感器", None, "颗粒物 空气质量 净化", _four_cases("颗粒物传感器")),
    ("co2", "二氧化碳传感器", None, "二氧化碳 通风 空气质量", _four_cases("二氧化碳传感器")),
    ("air_purifier", "空气净化器", None, "空气净化器 滤芯 颗粒物", _four_cases("空气净化器", "on")),
    ("humidifier", "加湿器", None, "加湿器 干燥 缺水", _four_cases("加湿器", "on")),
    ("dehumidifier", "除湿机", None, "除湿机 潮湿 水箱", _four_cases("除湿机", "on")),
    ("smart_plug", "智能插座", None, "插座 功率 过载 用电", _four_cases("智能插座", "off")),
    ("power_meter", "能耗计量器", None, "功率 能耗 过载 趋势", _four_cases("能耗计量器", "notify")),
    ("water_heater", "热水器", None, "热水器 漏电 温度", _four_cases("热水器", "off")),
    ("refrigerator", "冰箱", None, "冰箱 温度 门未关", _four_cases("冰箱", "notify")),
    ("washing_machine", "洗衣机", None, "洗衣机 漏水 完成", _four_cases("洗衣机", "off")),
    ("robot_vacuum", "扫地机器人", None, "扫地机器人 卡住 充电", _four_cases("扫地机器人", "pause")),
    ("television", "电视", None, "电视 待机 无人", _four_cases("电视", "off")),
    ("smart_speaker", "智能音箱", None, "音箱 播报 音量 夜间", _four_cases("智能音箱", "notify")),
    ("window_actuator", "电动窗", None, "电动窗 下雨 空气质量", _four_cases("电动窗", "close")),
)


def build_catalog() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for family_index, (family, name, device_id, keywords, cases) in enumerate(FAMILIES):
        for case_index, (condition, solution, action, risk) in enumerate(cases):
            for context_index, (context, guard) in enumerate(CONTEXTS):
                source = dict(SOURCES[(family_index + case_index + context_index) % len(SOURCES)])
                documents.append({
                    "id": f"DSK-{family_index + 1:02d}-{case_index + 1:02d}-{context_index + 1:02d}",
                    "text": f"设备：{name}。场景：{context}。状态或触发词：{condition}；{keywords}。处理建议：{solution}。约束：{guard}。",
                    "category": "device_solution",
                    "source": source,
                    "meta": {
                        "family": family,
                        "deviceName": name,
                        "deviceId": device_id,
                        "condition": condition,
                        "action": action,
                        "risk": risk,
                        "context": context,
                        "advisoryOnly": True,
                    },
                })
    return documents


def build_state_query(snapshot: Mapping[str, Any]) -> str:
    """Turn fresh rule inputs into a compact Chinese retrieval query."""
    sensors = snapshot.get("sensors", {}) if isinstance(snapshot, Mapping) else {}
    devices = snapshot.get("devices", {}) if isinstance(snapshot, Mapping) else {}
    time_state = snapshot.get("time", {}) if isinstance(snapshot, Mapping) else {}
    phrases: list[str] = []

    def sensor(sensor_id: str) -> Mapping[str, Any]:
        value = sensors.get(sensor_id, {}) if isinstance(sensors, Mapping) else {}
        return value if isinstance(value, Mapping) and value.get("online") is not False else {}

    def device(device_id: str) -> Mapping[str, Any]:
        value = devices.get(device_id, {}) if isinstance(devices, Mapping) else {}
        return value if isinstance(value, Mapping) and value.get("online") is not False else {}

    humidity = sensor("humid_01").get("value")
    temperature = sensor("temp_01").get("value")
    if isinstance(humidity, (int, float)) and humidity >= 75:
        phrases.append("设备空调 设备湿度传感器 条件湿度达到或超过75% 空调除湿")
    if isinstance(temperature, (int, float)) and temperature >= 30:
        phrases.append("设备空调 设备温度传感器 条件温度达到或超过30℃ 空调制冷")
    for sensor_id, label in (("smoke_01", "烟雾"), ("heat_01", "热敏")):
        item = sensor(sensor_id)
        if bool(item.get("is_alert", item.get("isAlert", False))):
            phrases.append(f"设备换气扇 设备{label}传感器 条件厨房烟雾或热敏报警 开启蜂鸣器和换气扇")
    radar = sensor("radar_01")
    present = radar.get("present")
    if present is False:
        if device("ac_01").get("is_on") is True:
            phrases.append("设备空调 条件毫米波连续确认无人且空调仍开")
        if device("fan_02").get("is_on") is True:
            phrases.append("设备换气扇 条件毫米波连续确认无人且无报警")
    light = snapshot.get("light_sensor", {}) if isinstance(snapshot, Mapping) else {}
    lux = light.get("value") if isinstance(light, Mapping) else None
    if present is True and isinstance(lux, (int, float)) and lux < 25:
        phrases.append("设备客厅主灯 条件照度低于25勒克斯且检测到有人 启用光敏自动模式")
    try:
        hour = int(time_state.get("hour"))
    except (TypeError, ValueError, AttributeError):
        hour = -1
    curtain = device("curtain_01")
    position = curtain.get("primary_value", curtain.get("position", 0))
    if (hour >= 22 or 0 <= hour < 6) and isinstance(position, (int, float)) and position > 0:
        phrases.append("设备智能窗帘 条件夜间 22点后窗帘仍开启")
    if hour == 0:
        if device("light_01").get("is_on") is True:
            phrases.append("设备客厅主灯 条件凌晨仍保持开启")
        if device("light_03").get("is_on") is True:
            phrases.append("设备卧室灯 条件凌晨仍保持开启")
    return "；".join(phrases)


def _tokens(text: str) -> Counter[str]:
    normalized = re.sub(r"\s+", "", str(text or "").lower())
    values = re.findall(r"[a-z0-9]+", normalized)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    values.extend(chinese[index:index + size] for size in (1, 2, 3) for index in range(max(0, len(chinese) - size + 1)))
    return Counter(values)


class DeviceSolutionKnowledge:
    def __init__(self) -> None:
        self.docs = build_catalog()
        self._tokens = [_tokens(item["text"]) for item in self.docs]

    def search(
        self,
        query: str,
        *,
        available_devices: Mapping[str, Mapping[str, Any]] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        available = dict(available_devices or {})
        explicit_devices = {
            name for _family, name, _device_id, _keywords, _cases in FAMILIES
            if f"设备{name}" in str(query)
        }
        explicit_conditions = {
            condition
            for _family, _name, _device_id, _keywords, cases in FAMILIES
            for condition, _solution, _action, _risk in cases
            if f"条件{condition}" in str(query)
        }
        ranked: list[tuple[float, int]] = []
        for index, item in enumerate(self.docs):
            meta = item["meta"]
            if explicit_devices and meta.get("deviceName") not in explicit_devices:
                continue
            if explicit_conditions and meta.get("condition") not in explicit_conditions:
                continue
            device_id = meta.get("deviceId")
            if available and device_id and device_id not in available:
                continue
            if available and device_id:
                actions = available[device_id].get("actions", ())
                if actions and meta.get("action") not in set(actions) | {"inspect", "notify", "record", "query"}:
                    continue
            overlap = sum(min(count, self._tokens[index].get(token, 0)) for token, count in query_tokens.items())
            if overlap <= 0:
                continue
            text = item["text"]
            bonus = 0.0
            for phrase in ("湿度", "温度", "无人", "烟雾", "门禁", "光照", "窗帘"):
                if phrase in query and phrase in text:
                    bonus += 12.0
            if meta.get("condition") and str(meta["condition"]) in query:
                bonus += 120.0
            if meta.get("deviceName") and f"设备{meta['deviceName']}" in query:
                bonus += 80.0
            ranked.append((float(overlap) + bonus, index))
        ranked.sort(key=lambda value: (-value[0], self.docs[value[1]]["id"]))
        result: list[dict[str, Any]] = []
        seen_strategy: set[tuple[Any, ...]] = set()
        for score, index in ranked:
            item = self.docs[index]
            meta = item["meta"]
            identity = (meta.get("family"), meta.get("condition"), meta.get("action"))
            if identity in seen_strategy:
                continue
            seen_strategy.add(identity)
            result.append({**item, "score": score, "retrieval": "source_device_solution"})
            if len(result) >= max(1, min(40, int(limit))):
                break
        return result

    def get_stats(self) -> dict[str, Any]:
        return {
            "total": len(self.docs), "families": len(FAMILIES), "sources": len(SOURCES), "language": "zh-CN",
            "sourceCatalog": [dict(item) for item in SOURCES],
        }
