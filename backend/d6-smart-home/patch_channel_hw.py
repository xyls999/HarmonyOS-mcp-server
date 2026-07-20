#!/usr/bin/env python3
"""
Patch channel.py to integrate hardware_bridge
- Add hw_toggle/hw_control/hw_scene_execute calls
- Replace tts_offline_alert with proper success/failure voice feedback
- Set hardwareOnline based on actual hardware results
"""
import re

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    src = f.read()

# 1. Add hardware_bridge import after the existing imports
if "from hardware_bridge import" not in src:
    # Add after "from urllib.request import Request, urlopen"
    src = src.replace(
        "from urllib.request import Request, urlopen\n",
        "from urllib.request import Request, urlopen\n\n# 硬件控制桥接\nfrom hardware_bridge import hw_toggle, hw_control, hw_scene_execute\n"
    )
    print("[1] Added hardware_bridge import")

# 2. Patch toggle_device handler
# Find the toggle_device block and replace the offline logic with hardware calls
old_toggle = '''            if r:

                # ★ 设备级保底: 数据库写入成功但硬件未接入

                dev_msg = _device_offline_msg(device_id, "开关")

                tts_offline_alert(_DEV_TTS_KEY.get(device_id, device_id) + "_toggle")

                result = {"msgId": msg_id, "success": True, "data": {

                    "id": r[0], "name": r[1], "type": r[2], "room": r[3],

                    "primaryValue": r[4], "isOn": bool(r[5])

                }, "hardwareOnline": False, "message": dev_msg}'''

new_toggle = '''            if r:
                # ★ 调用真实硬件
                hw_result = hw_toggle(device_id, is_on)
                hw_ok = hw_result["success"]
                dev_name = _DEVICE_NAMES.get(device_id, r[1])
                if hw_ok:
                    vs_text = f"{dev_name}已{'开启' if is_on else '关闭'}"
                    dev_msg = ""
                else:
                    vs_text = f"{dev_name}调用失败"
                    dev_msg = f"{dev_name}硬件调用失败: {hw_result.get('error', '未知')}"
                tts_speak(vs_text)
                vs_h = hashlib.md5(f"{vs_text}_7".encode()).hexdigest()
                voice_seq = [{"text": vs_text, "audioUrl": f"/api/tts/audio/{vs_h}.mp3"}]
                result = {"msgId": msg_id, "success": True, "data": {
                    "id": r[0], "name": r[1], "type": r[2], "room": r[3],
                    "primaryValue": r[4], "isOn": bool(r[5])
                }, "hardwareOnline": hw_ok, "message": dev_msg, "voiceSequence": voice_seq}'''

if old_toggle in src:
    src = src.replace(old_toggle, new_toggle)
    print("[2] Patched toggle_device handler")
else:
    print("[2] WARNING: toggle_device pattern not found, trying flexible match")
    # Try with flexible whitespace
    pat = r'if r:\s+# ★ 设备级保底.*?tts_offline_alert\(_DEV_TTS_KEY\.get\(device_id, device_id\).*?\+ "_toggle"\).*?"hardwareOnline": False.*?"message": dev_msg\}'
    m = re.search(pat, src, re.DOTALL)
    if m:
        src = src[:m.start()] + new_toggle + src[m.end():]
        print("[2] Patched toggle_device (flexible match)")
    else:
        print("[2] ERROR: Could not find toggle_device pattern")

# 3. Patch control_device handler
old_control = '''            if r:

                # ★ 设备级保底

                act_desc = {"set_temp": "调温", "set_speed": "调速", "set_brightness": "调光", "set_mode": "模式切换"}.get(act, "控制")

                dev_msg = _device_offline_msg(device_id, act_desc)

                tts_offline_alert(_DEV_TTS_KEY.get(device_id, device_id) + "_" + act)

                # voiceSequence

                ctrl_key = _DEV_TTS_KEY.get(device_id, device_id) + "_" + act

                ctrl_text = _TTS_TEXT_MAP.get(ctrl_key, "")

                if ctrl_key in _TTS_DYNAMIC_TEMPLATES:

                    pv_val = params.get("value", params.get("mode", None))

                    try: ctrl_text = _TTS_DYNAMIC_TEMPLATES[ctrl_key](bool(r[4]), pv_val)

                    except: pass

                voice_seq = _build_voice_sequence([ctrl_text]) if ctrl_text else []

                result = {"msgId": msg_id, "success": True, "data": {

                    "id": r[0], "name": r[1], "type": r[2], "primaryValue": r[3], "isOn": bool(r[4])

                }, "hardwareOnline": False, "message": dev_msg, "voiceSequence": voice_seq}'''

new_control = '''            if r:
                # ★ 调用真实硬件
                hw_result = hw_control(device_id, act, params)
                hw_ok = hw_result["success"]
                dev_name = _DEVICE_NAMES.get(device_id, r[1])
                act_desc = {"set_temp": "调温", "set_speed": "调速", "set_brightness": "调光", "set_mode": "模式切换"}.get(act, "控制")
                if hw_ok:
                    # 成功: 用动态模板生成语音文本
                    ctrl_key = _DEV_TTS_KEY.get(device_id, device_id) + "_" + act
                    ctrl_text = _TTS_TEXT_MAP.get(ctrl_key, "")
                    if ctrl_key in _TTS_DYNAMIC_TEMPLATES:
                        pv_val = params.get("value", params.get("mode", None))
                        try: ctrl_text = _TTS_DYNAMIC_TEMPLATES[ctrl_key](bool(r[4]), pv_val)
                        except: pass
                    if not ctrl_text:
                        ctrl_text = f"{dev_name}{act_desc}成功"
                    dev_msg = ""
                else:
                    ctrl_text = f"{dev_name}调用失败"
                    dev_msg = f"{dev_name}硬件调用失败: {hw_result.get('error', '未知')}"
                tts_speak(ctrl_text)
                vs_h = hashlib.md5(f"{ctrl_text}_7".encode()).hexdigest()
                voice_seq = [{"text": ctrl_text, "audioUrl": f"/api/tts/audio/{vs_h}.mp3"}]
                result = {"msgId": msg_id, "success": True, "data": {
                    "id": r[0], "name": r[1], "type": r[2], "primaryValue": r[3], "isOn": bool(r[4])
                }, "hardwareOnline": hw_ok, "message": dev_msg, "voiceSequence": voice_seq}'''

if old_control in src:
    src = src.replace(old_control, new_control)
    print("[3] Patched control_device handler")
else:
    print("[3] WARNING: control_device pattern not found, trying flexible match")
    pat = r'if r:\s+# ★ 设备级保底.*?tts_offline_alert\(_DEV_TTS_KEY\.get\(device_id, device_id\).*?\+ "_" \+ act\).*?"hardwareOnline": False.*?"voiceSequence": voice_seq\}'
    m = re.search(pat, src, re.DOTALL)
    if m:
        src = src[:m.start()] + new_control + src[m.end():]
        print("[3] Patched control_device (flexible match)")
    else:
        print("[3] ERROR: Could not find control_device pattern")

# 4. Patch activate_scene handler
# Replace the scene offline logic with hardware calls
old_scene = '''                # ★ 场景级保底: 场景激活成功但所有设备硬件未接入

                scene_name = _SCENE_NAMES.get(scene_id, name_r[0])

                scene_msg = f"{scene_name}场景激活离线，连通测试成功"

                tts_offline_alert(scene_id + "_activate")

                # voiceSequence

                scene_voice = _TTS_TEXT_MAP.get(scene_id + "_activate", "")

                voice_texts = [scene_voice] if scene_voice else []

                for dev_id2, dev_is_on2, dev_pv2 in actions:

                    dev_key2 = _DEV_TTS_KEY.get(dev_id2, dev_id2) + "_toggle"

                    dev_text2 = _TTS_TEXT_MAP.get(dev_key2, "")

                    if dev_key2 in _TTS_DYNAMIC_TEMPLATES:

                        try: dev_text2 = _TTS_DYNAMIC_TEMPLATES[dev_key2](dev_is_on2, dev_pv2)

                        except: pass

                    if dev_text2: voice_texts.append(dev_text2)

                voice_seq = _build_voice_sequence(voice_texts, 500) if voice_texts else []

                result = {"msgId": msg_id, "success": True, "data": {

                    "sceneName": name_r[0], "affectedCount": count,

                    "affectedDevices": affected_devices

                }, "hardwareOnline": False, "message": scene_msg, "voiceSequence": voice_seq}'''

new_scene = '''                # ★ 调用真实硬件执行场景
                hw_actions = [(dev_id, is_on, pv) for dev_id, is_on, pv in actions]
                hw_results = hw_scene_execute(hw_actions)
                hw_fail_count = sum(1 for hr in hw_results if not hr["success"])
                hw_any_ok = any(hr["success"] for hr in hw_results)

                scene_name = _SCENE_NAMES.get(scene_id, name_r[0])
                scene_voice = _TTS_TEXT_MAP.get(scene_id + "_activate", "")

                # 语音反馈: 根据硬件结果
                voice_texts = []
                if hw_fail_count == 0:
                    # 全部成功
                    if scene_voice:
                        voice_texts.append(scene_voice)
                    for dev_id2, dev_is_on2, dev_pv2 in actions:
                        dev_key2 = _DEV_TTS_KEY.get(dev_id2, dev_id2) + "_toggle"
                        dev_text2 = _TTS_TEXT_MAP.get(dev_key2, "")
                        if dev_key2 in _TTS_DYNAMIC_TEMPLATES:
                            try: dev_text2 = _TTS_DYNAMIC_TEMPLATES[dev_key2](dev_is_on2, dev_pv2)
                            except: pass
                        if dev_text2: voice_texts.append(dev_text2)
                    scene_msg = ""
                elif hw_fail_count > 0 and hw_any_ok:
                    # 部分失败
                    if scene_voice:
                        voice_texts.append(f"{scene_voice}，{hw_fail_count}台设备调用失败")
                    else:
                        voice_texts.append(f"{scene_name}模式已激活，{hw_fail_count}台设备调用失败")
                    for dev_id2, dev_is_on2, dev_pv2 in actions:
                        dev_name2 = _DEVICE_NAMES.get(dev_id2, dev_id2)
                        hr2 = next((hr for hr in hw_results if hr["device_id"] == dev_id2), None)
                        if hr2 and hr2["success"]:
                            dev_key2 = _DEV_TTS_KEY.get(dev_id2, dev_id2) + "_toggle"
                            dev_text2 = _TTS_TEXT_MAP.get(dev_key2, "")
                            if dev_key2 in _TTS_DYNAMIC_TEMPLATES:
                                try: dev_text2 = _TTS_DYNAMIC_TEMPLATES[dev_key2](dev_is_on2, dev_pv2)
                                except: pass
                            if dev_text2: voice_texts.append(dev_text2)
                        else:
                            voice_texts.append(f"{dev_name2}调用失败")
                    scene_msg = f"{hw_fail_count}台设备硬件调用失败"
                else:
                    # 全部失败
                    voice_texts = [f"{scene_name}模式调用失败"]
                    scene_msg = f"{scene_name}模式全部设备调用失败"

                # 播报语音
                for vt in voice_texts:
                    tts_speak(vt)

                voice_seq = _build_voice_sequence(voice_texts, 500) if voice_texts else []

                result = {"msgId": msg_id, "success": True, "data": {
                    "sceneName": name_r[0], "affectedCount": count,
                    "affectedDevices": affected_devices
                }, "hardwareOnline": hw_any_ok, "message": scene_msg, "voiceSequence": voice_seq}'''

if old_scene in src:
    src = src.replace(old_scene, new_scene)
    print("[4] Patched activate_scene handler")
else:
    print("[4] WARNING: activate_scene pattern not found, trying flexible match")
    pat = r'# ★ 场景级保底.*?tts_offline_alert\(scene_id \+ "_activate"\).*?"hardwareOnline": False.*?"voiceSequence": voice_seq\}'
    m = re.search(pat, src, re.DOTALL)
    if m:
        src = src[:m.start()] + new_scene + src[m.end():]
        print("[4] Patched activate_scene (flexible match)")
    else:
        print("[4] ERROR: Could not find activate_scene pattern")

# 5. Patch send_chat scene match - add hw_scene_execute
# In send_chat, when scene matches, also call hardware
old_chat_scene = '''                for dev_id, is_on, pv in actions:

                    conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))

                    if pv is not None:

                        conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?", (pv, dev_id))

                    conn.execute("INSERT INTO device_operations(device_id,action,params_json,source,scene_id) VALUES(?,?,?,?,?)",

                                (dev_id, "scene_toggle", json.dumps({"isOn": bool(is_on), "primaryValue": pv}), "remote", sid))

                sname = SCENE_META.get(sid, {}).get("name", sid)

                reply = f"已切换到「{sname}」模式，控制 {len(actions)} 台设备"'''

new_chat_scene = '''                for dev_id, is_on, pv in actions:

                    conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))

                    if pv is not None:

                        conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?", (pv, dev_id))

                    conn.execute("INSERT INTO device_operations(device_id,action,params_json,source,scene_id) VALUES(?,?,?,?,?)",

                                (dev_id, "scene_toggle", json.dumps({"isOn": bool(is_on), "primaryValue": pv}), "remote", sid))

                # ★ 调用真实硬件执行场景
                hw_chat_results = hw_scene_execute([(dev_id, is_on, pv) for dev_id, is_on, pv in actions])
                hw_chat_fail = sum(1 for hr in hw_chat_results if not hr["success"])
                hw_chat_ok = any(hr["success"] for hr in hw_chat_results)

                sname = SCENE_META.get(sid, {}).get("name", sid)
                if hw_chat_fail == 0:
                    reply = f"已切换到「{sname}」模式，控制 {len(actions)} 台设备"
                elif hw_chat_ok:
                    reply = f"已切换到「{sname}」模式，{hw_chat_fail}台设备调用失败"
                else:
                    reply = f"「{sname}」模式调用失败"'''

if old_chat_scene in src:
    src = src.replace(old_chat_scene, new_chat_scene)
    print("[5] Patched send_chat scene match with hardware calls")
else:
    print("[5] WARNING: send_chat scene pattern not found")

# 6. Fix send_chat result - set hardwareOnline based on actual results
old_chat_result = '''            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id, "voiceSequence": _vs_seq},
                     "hardwareOnline": hw_online, "message": "AI对话在线，设备控制离线，连通测试成功"}'''

new_chat_result = '''            # 确定硬件在线状态
            if scene_id:
                hw_online = hw_chat_ok if 'hw_chat_ok' in dir() else False
                chat_msg = "" if hw_online else "部分设备调用失败" if 'hw_chat_ok' in dir() and hw_chat_ok else "设备调用失败"
            else:
                hw_online = True  # AI对话不需要硬件
                chat_msg = ""
            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id, "voiceSequence": _vs_seq},
                     "hardwareOnline": hw_online, "message": chat_msg}'''

if old_chat_result in src:
    src = src.replace(old_chat_result, new_chat_result)
    print("[6] Patched send_chat result with proper hardwareOnline")
else:
    print("[6] WARNING: send_chat result pattern not found")

# Write patched file
with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(src)

print("\n=== channel.py patch complete ===")
