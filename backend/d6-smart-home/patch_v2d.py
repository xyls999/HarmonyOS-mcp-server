#!/usr/bin/env python3
"""Patch v2d: Move _ws_detect_device_control out of if/elif chain"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# 1. Remove the misplaced function definition from inside the if/elif chain
old_func_block = '''        # ★ WebSocket 设备控制意图检测
        def _ws_detect_device_control(text):
            """检测对话中的设备控制意图，调用真实硬件返回真实结果"""
            _DEV_KEYWORDS = {
                "空调": "ac_01", "客厅灯": "light_01", "主灯": "light_01",
                "氛围灯": "light_05", "厨房灯": "light_02",
                "卧室灯": "light_03", "卫生间灯": "light_04",
                "窗帘": "curtain_01", "大门": "door_01", "门": "door_01",
                "换气扇": "fan_02", "排风扇": "fan_02",
                "警报": "alarm_01", "蜂鸣": "alarm_01",
            }
            _ON_KW = ["打开", "开启", "开", "启动", "合上"]
            _OFF_KW = ["关闭", "关掉", "关", "停止", "停", "熄灭", "断开"]
            text = text.strip()
            is_on = None
            for kw in _ON_KW:
                if kw in text: is_on = True; break
            if is_on is None:
                for kw in _OFF_KW:
                    if kw in text: is_on = False; break
            if is_on is None: return None
            dev_id = None
            for kw, did in _DEV_KEYWORDS.items():
                if kw in text: dev_id = did; break
            if dev_id is None:
                if "灯" in text: dev_id = "light_01"
                else: return None
            # 调用真实硬件
            hw_result = hw_toggle(dev_id, is_on)
            hw_ok = hw_result["success"]
            dev_name = _DEVICE_NAMES.get(dev_id, dev_id)
            # 更新DB
            conn2 = sqlite3.connect("/data/A9/control/data/smart_home.db")
            conn2.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))
            if hw_ok:
                reply = f"{dev_name}已{'开启' if is_on else '关闭'}"
            else:
                reply = f"{dev_name}{'开启' if is_on else '关闭'}失败，设备离线或无响应"
            conn2.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (text,))
            conn2.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
            conn2.commit(); conn2.close()
            tts_speak(reply)
            vs_h = hashlib.md5(f"{reply}_7".encode()).hexdigest()
            vs_seq = [{"text": reply, "audioUrl": f"/api/tts/audio/{vs_h}.mp3"}]
            return {"reply": reply, "hardwareOnline": hw_ok, "voiceSequence": vs_seq}

        elif action == "toggle_device":'''

new_func_block = '''        elif action == "toggle_device":'''

if old_func_block in ch:
    ch = ch.replace(old_func_block, new_func_block)
    print("[1] Removed misplaced _ws_detect_device_control from if/elif chain")
else:
    print("[1] WARNING: misplaced function not found")

# 2. Add _ws_detect_device_control as a module-level function before the action handlers
# Find a good insertion point - before the main message handler
# Insert before "def _handle_message" or similar
if "_ws_detect_device_control" not in ch:
    # Add as module-level function before the main handler
    insert_before = "def _device_offline_msg"
    func_code = '''# ★ WebSocket/HTTP 设备控制意图检测 (模块级函数)
def _ws_detect_device_control(text):
    """检测对话中的设备控制意图，调用真实硬件返回真实结果"""
    _DEV_KEYWORDS = {
        "空调": "ac_01", "客厅灯": "light_01", "主灯": "light_01",
        "氛围灯": "light_05", "厨房灯": "light_02",
        "卧室灯": "light_03", "卫生间灯": "light_04",
        "窗帘": "curtain_01", "大门": "door_01", "门": "door_01",
        "换气扇": "fan_02", "排风扇": "fan_02",
        "警报": "alarm_01", "蜂鸣": "alarm_01",
    }
    _ON_KW = ["打开", "开启", "开", "启动", "合上"]
    _OFF_KW = ["关闭", "关掉", "关", "停止", "停", "熄灭", "断开"]
    text = text.strip()
    is_on = None
    for kw in _ON_KW:
        if kw in text: is_on = True; break
    if is_on is None:
        for kw in _OFF_KW:
            if kw in text: is_on = False; break
    if is_on is None: return None
    dev_id = None
    for kw, did in _DEV_KEYWORDS.items():
        if kw in text: dev_id = did; break
    if dev_id is None:
        if "灯" in text: dev_id = "light_01"
        else: return None
    # 调用真实硬件
    hw_result = hw_toggle(dev_id, is_on)
    hw_ok = hw_result["success"]
    dev_name = _DEVICE_NAMES.get(dev_id, dev_id)
    # 更新DB
    conn2 = sqlite3.connect("/data/A9/control/data/smart_home.db")
    conn2.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))
    if hw_ok:
        reply = f"{dev_name}已{'开启' if is_on else '关闭'}"
    else:
        reply = f"{dev_name}{'开启' if is_on else '关闭'}失败，设备离线或无响应"
    conn2.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (text,))
    conn2.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
    conn2.commit(); conn2.close()
    tts_speak(reply)
    vs_h = hashlib.md5(f"{reply}_7".encode()).hexdigest()
    vs_seq = [{"text": reply, "audioUrl": f"/api/tts/audio/{vs_h}.mp3"}]
    return {"reply": reply, "hardwareOnline": hw_ok, "voiceSequence": vs_seq}


'''
    if insert_before in ch:
        ch = ch.replace(insert_before, func_code + insert_before)
        print("[2] Added _ws_detect_device_control as module-level function")
    else:
        print("[2] ERROR: Could not find insertion point")
else:
    print("[2] _ws_detect_device_control already exists as module-level function")

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)
print("channel.py saved")
