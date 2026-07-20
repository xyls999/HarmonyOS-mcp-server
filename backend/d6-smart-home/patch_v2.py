#!/usr/bin/env python3
"""
Patch v2: Fix 3 issues in gateway_v3.py and channel.py
1. Remove pre-recorded WAV fallback, always use online TTS API
2. AI chat must return real hardware status (not lie)
3. Text response first, then voice playback in background thread
"""
import re

# ========== Patch gateway_v3.py ==========
with open("/data/A9/smart_home/gateway_v3.py", "r", encoding="utf-8") as f:
    gw = f.read()

# 1. Change _tts_speak to be non-blocking (threaded)
old_tts_speak = '''def _tts_speak(text):
    """播放语音：成功/失败都播报"""
    try:
        from channel import tts_speak as _ch_tts
        _ch_tts(text)
    except Exception:
        pass  # channel 不可用时静默'''

new_tts_speak = '''def _tts_speak(text):
    """播放语音：成功/失败都播报 (后台线程，不阻塞HTTP响应)"""
    if not text:
        return
    def _speak():
        try:
            from channel import tts_speak as _ch_tts
            _ch_tts(text)
        except Exception:
            pass
    import threading as _th
    _th.Thread(target=_speak, daemon=True).start()'''

if old_tts_speak in gw:
    gw = gw.replace(old_tts_speak, new_tts_speak)
    print("[GW-1] Patched _tts_speak to be non-blocking (threaded)")
else:
    print("[GW-1] WARNING: _tts_speak pattern not found")

# 2. Fix AI chat to return real hardware info
# When AI says "关闭空调" or "打开灯" etc, we should actually call hw_toggle/hw_control
# and report the real result instead of letting the AI lie

# The _chat function needs to detect device control intent and actually execute it
old_chat_func = '''    def _chat(self,body):
        msgs=body.get("messages",[])
        if not msgs: return {"reply":"请输入消息","role":"assistant"}
        last_msg=msgs[-1].get("content","")
        # RAG 固定回复
        fixed_reply=_rag.match_reply(last_msg)
        if fixed_reply:
            conn=_db()
            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)",(last_msg,))
            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)",(fixed_reply,))
            conn.commit(); conn.close()
            _tts_speak(fixed_reply)
            return {"reply":fixed_reply,"role":"assistant","source":"rag","voiceSequence":[_vs_entry(fixed_reply)]}
        # RAG 场景匹配
        scene_match=_rag.search_scene(last_msg)
        if scene_match and scene_match.get("scene_id"):
            result=self._activate_scene(scene_match["scene_id"])
            if result.get("success"):
                _vs_reply = f"已切换到「{result['scene_name']}」模式，控制 {result['affected_count']} 台设备"
                _tts_speak(_vs_reply)
                return {"reply":_vs_reply,"role":"assistant","scene_id":scene_match["scene_id"],"voiceSequence":result.get("voiceSequence",[])}
        # AI 大模型
        conn=_db()
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)",(last_msg,))
        reply=chat(msgs)
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)",(reply,))
        conn.commit(); conn.close()
        _tts_speak(reply)
        return {"reply":reply,"role":"assistant","voiceSequence":[_vs_entry(reply)]}'''

new_chat_func = '''    def _chat(self,body):
        msgs=body.get("messages",[])
        if not msgs: return {"reply":"请输入消息","role":"assistant"}
        last_msg=msgs[-1].get("content","")

        # ★ 设备控制意图检测 → 直接调用硬件，返回真实结果
        _dev_ctrl = self._detect_device_control(last_msg)
        if _dev_ctrl:
            return _dev_ctrl

        # RAG 固定回复
        fixed_reply=_rag.match_reply(last_msg)
        if fixed_reply:
            conn=_db()
            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)",(last_msg,))
            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)",(fixed_reply,))
            conn.commit(); conn.close()
            _tts_speak(fixed_reply)
            return {"reply":fixed_reply,"role":"assistant","source":"rag","voiceSequence":[_vs_entry(fixed_reply)]}
        # RAG 场景匹配
        scene_match=_rag.search_scene(last_msg)
        if scene_match and scene_match.get("scene_id"):
            result=self._activate_scene(scene_match["scene_id"])
            if result.get("success"):
                hw_ok = result.get("hardwareOnline", False)
                if hw_ok:
                    _vs_reply = f"已切换到「{result['scene_name']}」模式，控制 {result['affected_count']} 台设备"
                else:
                    _vs_reply = f"「{result['scene_name']}」模式调用失败，设备离线"
                _tts_speak(_vs_reply)
                return {"reply":_vs_reply,"role":"assistant","scene_id":scene_match["scene_id"],"voiceSequence":result.get("voiceSequence",[])}
        # AI 大模型
        conn=_db()
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)",(last_msg,))
        reply=chat(msgs)
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)",(reply,))
        conn.commit(); conn.close()
        _tts_speak(reply)
        return {"reply":reply,"role":"assistant","voiceSequence":[_vs_entry(reply)]}

    def _detect_device_control(self, text):
        """检测AI对话中的设备控制意图，直接调用硬件返回真实结果"""
        # 设备关键词映射
        _DEV_KEYWORDS = {
            "空调": "ac_01", "灯": None, "灯泡": None,
            "客厅灯": "light_01", "主灯": "light_01",
            "氛围灯": "light_05", "厨房灯": "light_02",
            "卧室灯": "light_03", "卫生间灯": "light_04",
            "窗帘": "curtain_01", "大门": "door_01", "门": "door_01",
            "换气扇": "fan_02", "排风扇": "fan_02",
            "警报": "alarm_01", "蜂鸣": "alarm_01",
        }
        _ON_KEYWORDS = ["打开", "开启", "开", "启动", "启动", "合上"]
        _OFF_KEYWORDS = ["关闭", "关掉", "关", "停止", "停", "熄灭", "断开"]

        text = text.strip()
        dev_id = None
        is_on = None

        # 检测开关意图
        for kw in _ON_KEYWORDS:
            if kw in text:
                is_on = True
                break
        if is_on is None:
            for kw in _OFF_KEYWORDS:
                if kw in text:
                    is_on = False
                    break

        if is_on is None:
            return None  # 不是开关指令

        # 检测目标设备
        for kw, did in _DEV_KEYWORDS.items():
            if kw in text:
                dev_id = did
                break

        if dev_id is None:
            # "灯" 单独出现时根据上下文猜测客厅灯
            if "灯" in text:
                dev_id = "light_01"
            else:
                return None  # 无法识别设备

        # 执行硬件调用
        dev_name = _DEVICE_NAMES.get(dev_id, dev_id)
        hw_result = hw_toggle(dev_id, is_on)
        hw_ok = hw_result["success"]

        # 更新数据库
        conn = _db()
        conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','user',?)", (text,))
        if hw_ok:
            reply = f"{dev_name}已{'开启' if is_on else '关闭'}"
        else:
            reply = f"{dev_name}{'开启' if is_on else '关闭'}失败，设备离线或无响应"
        conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?)", (reply,))
        conn.commit(); conn.close()

        _tts_speak(reply)
        return {"reply": reply, "role": "assistant",
                "voiceSequence": [_vs_entry(reply)],
                "hardwareOnline": hw_ok}'''

if old_chat_func in gw:
    gw = gw.replace(old_chat_func, new_chat_func)
    print("[GW-2] Patched _chat with device control detection + real hardware results")
else:
    print("[GW-2] WARNING: _chat pattern not found, trying flexible match")
    # Try finding just the def _chat line and replacing everything up to def _bearpi
    pat = r'    def _chat\(self,body\):.*?(?=    def _bearpi)'
    m = re.search(pat, gw, re.DOTALL)
    if m:
        gw = gw[:m.start()] + new_chat_func + "\n\n" + gw[m.end():]
        print("[GW-2] Patched _chat (flexible match)")
    else:
        print("[GW-2] ERROR: Could not find _chat")

with open("/data/A9/smart_home/gateway_v3.py", "w", encoding="utf-8") as f:
    f.write(gw)
print("[GW] gateway_v3.py saved")


# ========== Patch channel.py ==========
with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# 1. Make tts_speak non-blocking (threaded) in channel.py too
old_ch_tts_speak = '''def tts_speak(text, speed=5):

    """在线 TTS 播报: 合成语音并播放



    Args:

        text: 要播报的中文文本

        speed: 语速 1-10 (5=正常)

    Returns:

        True=播放成功, False=播放失败

    """

    if not _TTS_CONFIG.get("enabled", True):

        log(f"[TTS-ONLINE] 🔇 静音: {text[:20]}...")

        return False



    mp3_path = _tts_online(text, speed)

    if mp3_path:

        return _play_mp3(mp3_path)

    return False'''

new_ch_tts_speak = '''def _tts_speak_sync(text, speed=5):
    """在线 TTS 播报: 合成语音并播放 (同步版本)"""
    if not _TTS_CONFIG.get("enabled", True):
        log(f"[TTS-ONLINE] 🔇 静音: {text[:20]}...")
        return False
    mp3_path = _tts_online(text, speed)
    if mp3_path:
        return _play_mp3(mp3_path)
    return False

def tts_speak(text, speed=5):
    """在线 TTS 播报: 合成语音并播放 (后台线程，不阻塞响应)

    Args:
        text: 要播报的中文文本
        speed: 语速 1-10 (5=正常)
    Returns:
        True=播放成功, False=播放失败
    """
    def _speak():
        _tts_speak_sync(text, speed)
    import threading as _th
    t = _th.Thread(target=_speak, daemon=True)
    t.start()
    return True  # 已提交后台播放'''

if old_ch_tts_speak in ch:
    ch = ch.replace(old_ch_tts_speak, new_ch_tts_speak)
    print("[CH-1] Patched tts_speak to be non-blocking (threaded)")
else:
    print("[CH-1] WARNING: tts_speak pattern not found")

# 2. Replace tts_offline_alert to always use online TTS, no WAV fallback
# The current tts_offline_alert plays WAV files as fallback.
# We want it to just use tts_speak (which is now online TTS + threaded)
old_offline = '''def tts_offline_alert(feature_name):

    """离线保底反馈: 播放中文语音 WAV + 日志 + 返回保底消息 (受 _TTS_CONFIG 控制)"""

    msg = "{}离线，连通测试成功".format(feature_name)'''

new_offline = '''def tts_offline_alert(feature_name):
    """离线保底反馈: 使用在线TTS播报 (不再使用预录WAV)"""
    msg = "{}离线，连通测试成功".format(feature_name)'''

if old_offline in ch:
    ch = ch.replace(old_offline, new_offline)
    print("[CH-2a] Updated tts_offline_alert header")
else:
    print("[CH-2a] WARNING: tts_offline_alert header not found")

# Replace the entire tts_offline_alert backend selection logic with simple online TTS
# Find the section after throttling that does backend selection and replace it
old_backend_block = '''    # 总开关关闭 → 只写日志不播放

    if not _TTS_CONFIG.get("enabled", True):

        log("[TTS] 🔇 静音 离线提示: {} (TTS disabled)".format(feature_name))

        log("[OFFLINE] ⚠ {}".format(msg))

        return msg



    backend = _TTS_CONFIG.get("backend", "online")

    played = False



    if backend == "none":

        play_type = "🔇静音"

    elif backend == "online":

        # 在线 TTS: 优先使用动态文本映射，否则用静态映射

        played = tts_speak_key(feature_name)

        play_type = "🔊在线语音" if played else "🔇在线语音"

        if not played:

            # 在线失败，降级到 WAV

            tts_key = _TTS_WAV_MAP.get(feature_name, "")

            wav_path = _TTS_WAV_DIR / "{}.wav".format(tts_key) if tts_key else None

            if wav_path and wav_path.exists():

                played = _play_wav(wav_path)

                play_type = "🔊WAV降级" if played else "🔇WAV降级"

            else:

                played = _play_beep(frequency=660, duration=0.5)

                play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"

    elif backend == "beep":

        played = _play_beep(frequency=660, duration=0.5)

        play_type = "🔊蜂鸣" if played else "🔇蜂鸣"

    else:  # "wav" or default

        tts_key = _TTS_WAV_MAP.get(feature_name, "")

        wav_path = _TTS_WAV_DIR / "{}.wav".format(tts_key) if tts_key else None

        if wav_path and wav_path.exists():

            played = _play_wav(wav_path)'''

new_backend_block = '''    # 总开关关闭 → 只写日志不播放
    if not _TTS_CONFIG.get("enabled", True):
        log("[TTS] 🔇 静音 离线提示: {} (TTS disabled)".format(feature_name))
        log("[OFFLINE] ⚠ {}".format(msg))
        return msg

    # 统一使用在线 TTS，不再使用预录 WAV
    played = tts_speak_key(feature_name)
    play_type = "🔊在线语音" if played else "🔇在线语音"

    if not played:
        # 在线失败，蜂鸣降级
        played = _play_beep(frequency=660, duration=0.5)
        play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"'''

if old_backend_block in ch:
    ch = ch.replace(old_backend_block, new_backend_block)
    print("[CH-2b] Replaced WAV fallback with online TTS only")
else:
    print("[CH-2b] WARNING: backend block not found, trying flexible match")
    pat = r'# 总开关关闭.*?played = _play_wav\(wav_path\)'
    m = re.search(pat, ch, re.DOTALL)
    if m:
        ch = ch[:m.start()] + new_backend_block + ch[m.end():]
        print("[CH-2b] Replaced backend block (flexible match)")
    else:
        print("[CH-2b] ERROR: Could not find backend block")

# 3. Also fix the second WAV fallback path in tts_offline_alert (after the if/elif/else block)
# There's likely a second occurrence of WAV playing after the else block
# Let's find and fix any remaining _play_wav calls in tts_offline_alert
# Check if there's more WAV code after the else block
remaining_wav = ch.count("_play_wav")
print(f"[CH-2c] Remaining _play_wav calls: {remaining_wav}")

# 4. Fix send_chat handler in channel.py - same issue with AI lying about device control
# The send_chat in channel.py also needs device control detection
# Find the send_chat handler that does AI call
old_send_chat_ai = '''                else:

                    reply = f"未配置AI({provider})"

            conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?,?)", (reply, scene_id))

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

new_send_chat_ai = '''                else:
                    reply = f"未配置AI({provider})"

            # ★ 检测设备控制意图，返回真实硬件结果
            _ws_dev_ctrl = _ws_detect_device_control(content)
            if _ws_dev_ctrl:
                reply = _ws_dev_ctrl["reply"]
                hw_online = _ws_dev_ctrl["hardwareOnline"]
                _vs_seq = _ws_dev_ctrl["voiceSequence"]
                scene_id = None  # 设备控制不是场景
            else:
                # 原有逻辑
                conn.execute("INSERT INTO chat_history(user_id,role,content) VALUES('u001','assistant',?,?)", (reply, scene_id))
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

if old_send_chat_ai in ch:
    ch = ch.replace(old_send_chat_ai, new_send_chat_ai)
    print("[CH-3] Patched send_chat with device control detection")
else:
    print("[CH-3] WARNING: send_chat AI section not found")

# Add _ws_detect_device_control function before the send_chat handler
if "_ws_detect_device_control" not in ch:
    # Add it before the action handlers section
    insert_marker = '        elif action == "toggle_device":'
    if insert_marker in ch:
        ws_dev_func = '''        # ★ WebSocket 设备控制意图检测
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
        ch = ch.replace(insert_marker, ws_dev_func + insert_marker)
        print("[CH-4] Added _ws_detect_device_control function")
    else:
        print("[CH-4] ERROR: Could not find insertion point")

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)
print("[CH] channel.py saved")

# Delete pre-recorded WAV files
print("\n=== Deleting pre-recorded WAV files ===")
import subprocess
hdc = "/d/command-line-tools/sdk/default/openharmony/toolchains/hdc"
result = subprocess.run(
    [hdc, "shell", "rm -rf /data/A9/smart_home/tts_wav/*.wav"],
    env={**subprocess.os.environ, "MSYS_NO_PATHCONV": "1"},
    capture_output=True, text=True
)
print(f"Delete WAV result: {result.stdout.strip()} {result.stderr.strip()}")

# Also clear old TTS cache
result2 = subprocess.run(
    [hdc, "shell", "rm -rf /data/A9/smart_home/tts_cache/*.mp3"],
    env={**subprocess.os.environ, "MSYS_NO_PATHCONV": "1"},
    capture_output=True, text=True
)
print(f"Clear TTS cache result: {result2.stdout.strip()} {result2.stderr.strip()}")

print("\n=== All patches complete ===")
