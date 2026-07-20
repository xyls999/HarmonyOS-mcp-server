#!/usr/bin/env python3
"""Patch channel.py to add TTS voice feedback to ALL commands"""
import re

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace the finally block to add universal TTS + message for all commands
old_finally = """    finally:
        # ★ 保底: 确保数据库连接关闭
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return result"""

new_finally = """    finally:
        # ★ 保底: 确保数据库连接关闭
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        # ★★★ 统一语音回馈: 每个指令都保证有 TTS 蜂鸣 + message
        if isinstance(result, dict) and "message" not in result:
            # 查询类指令: 数据在线但硬件未接入
            tts_offline_alert(action_name)
            result["hardwareOnline"] = False
            result["message"] = f"{action_name}查询成功，硬件未接入，连通测试成功"

    return result"""

code = code.replace(old_finally, new_finally)

# 2. Fix remove_device: use device name from DB instead of raw device_id
# Current: tts_offline_alert(_DEVICE_NAMES.get(device_id, device_id) + "移除")
# The issue is that test_dev_01 is not in _DEVICE_NAMES, so it shows the raw ID
# Fix: also try to get name from DB before falling back to ID
old_remove_tts = '''                dev_msg = _device_offline_msg(device_id, "移除")
                tts_offline_alert(_DEVICE_NAMES.get(device_id, device_id) + "移除")'''

new_remove_tts = '''                # 先查数据库拿设备中文名
                dev_name_r = conn.execute("SELECT name FROM devices WHERE id=?", (device_id,)).fetchone()
                dev_display = (dev_name_r[0] if dev_name_r else None) or _DEVICE_NAMES.get(device_id, device_id)
                dev_msg = f"{dev_display}移除离线，连通测试成功"
                tts_offline_alert(dev_display + "移除")'''

code = code.replace(old_remove_tts, new_remove_tts)

# 3. Add TTS beep to get_alerts and get_cameras (they have message but no TTS)
old_alerts = '''            result = {"msgId": msg_id, "success": True, "data": alerts,
                     "hardwareOnline": False, "message": "告警数据为模拟数据，连通测试成功"}'''

new_alerts = '''            tts_offline_alert("告警查询")
            result = {"msgId": msg_id, "success": True, "data": alerts,
                     "hardwareOnline": False, "message": "告警数据为模拟数据，连通测试成功"}'''

code = code.replace(old_alerts, new_alerts)

old_cameras = '''            result = {"msgId": msg_id, "success": True, "data": cameras,
                     "hardwareOnline": False, "message": "摄像头数据为模拟数据，连通测试成功"}'''

new_cameras = '''            tts_offline_alert("摄像头查询")
            result = {"msgId": msg_id, "success": True, "data": cameras,
                     "hardwareOnline": False, "message": "摄像头数据为模拟数据，连通测试成功"}'''

code = code.replace(old_cameras, new_cameras)

# 4. Fix send_chat: add TTS beep even when no scene match
old_send_chat_msg = '''            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id},
                     "hardwareOnline": hw_online, "message": "AI对话在线，设备控制离线，连通测试成功"}'''

new_send_chat_msg = '''            if not scene_id:
                tts_offline_alert("AI对话")
            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id},
                     "hardwareOnline": hw_online, "message": "AI对话在线，设备控制离线，连通测试成功"}'''

code = code.replace(old_send_chat_msg, new_send_chat_msg)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patched successfully!")
print("Changes:")
print("  1. finally block: universal TTS + message for all commands without message")
print("  2. remove_device: use DB name instead of raw device_id")
print("  3. get_alerts: added TTS beep")
print("  4. get_cameras: added TTS beep")
print("  5. send_chat: added TTS beep when no scene match")
