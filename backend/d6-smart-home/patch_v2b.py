#!/usr/bin/env python3
"""Patch v2b: Fix send_chat in channel.py with device control detection"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# Replace the send_chat AI result section
old = '''            conn.execute("INSERT INTO chat_history(user_id,role,content,scene_id) VALUES('u001','assistant',?,?)", (reply, scene_id))

            conn.commit()

            # ★ 播报实际AI回复内容
            hw_online = False
            _vs_seq = []
            try:
                tts_speak(reply)
                _vs_h = hashlib.md5(f"{reply}_7".encode()).hexdigest()
                _vs_entry = {"text": reply, "audioUrl": f"/api/tts/audio/{_vs_h}.mp3"}
                _vs_seq = [_vs_entry]
                log(f"[CHAT-TTS] ✓ AI回复已播报: {reply[:30]}...")
            except Exception as _e:
                log(f"[CHAT-TTS] 播报失败: {_e}")
            if scene_id:
                tts_offline_alert(scene_id + "_activate")
            # 确定硬件在线状态
            if scene_id:
                hw_online = hw_chat_ok if 'hw_chat_ok' in dir() else False
                chat_msg = "" if hw_online else "部分设备调用失败" if 'hw_chat_ok' in dir() and hw_chat_ok else "设备调用失败"
            else:
                hw_online = True  # AI对话不需要硬件
                chat_msg = ""
            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id, "voiceSequence": _vs_seq},
                     "hardwareOnline": hw_online, "message": chat_msg}'''

new = '''            # ★ 检测设备控制意图，返回真实硬件结果
            _ws_dev_ctrl = _ws_detect_device_control(content)
            if _ws_dev_ctrl:
                reply = _ws_dev_ctrl["reply"]
                hw_online = _ws_dev_ctrl["hardwareOnline"]
                _vs_seq = _ws_dev_ctrl["voiceSequence"]
                scene_id = None
            else:
                conn.execute("INSERT INTO chat_history(user_id,role,content,scene_id) VALUES('u001','assistant',?,?)", (reply, scene_id))
                conn.commit()
                # ★ 播报实际AI回复内容
                _vs_seq = []
                try:
                    tts_speak(reply)
                    _vs_h = hashlib.md5(f"{reply}_7".encode()).hexdigest()
                    _vs_entry = {"text": reply, "audioUrl": f"/api/tts/audio/{_vs_h}.mp3"}
                    _vs_seq = [_vs_entry]
                    log(f"[CHAT-TTS] ✓ AI回复已播报: {reply[:30]}...")
                except Exception as _e:
                    log(f"[CHAT-TTS] 播报失败: {_e}")
                if scene_id:
                    hw_online = hw_chat_ok if 'hw_chat_ok' in dir() else False
                else:
                    hw_online = True
            chat_msg = "" if hw_online else "设备调用失败"
            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id, "voiceSequence": _vs_seq},
                     "hardwareOnline": hw_online, "message": chat_msg}'''

if old in ch:
    ch = ch.replace(old, new)
    print("[CH-3b] Patched send_chat with device control detection")
else:
    print("[CH-3b] ERROR: send_chat pattern not found")

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)
print("channel.py saved")
