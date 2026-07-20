#!/usr/bin/env python3
"""Patch channel.py - update all tts_offline_alert calls to use TTS keys"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. toggle_device: use device_id + "_toggle" key
old = 'tts_offline_alert(_DEVICE_NAMES.get(device_id, device_id) + "开关")'
new = 'tts_offline_alert(_DEV_TTS_KEY.get(device_id, device_id) + "_toggle")'
code = code.replace(old, new)

# 2. control_device: use device_id + "_" + subAction key
old = 'tts_offline_alert(_DEVICE_NAMES.get(device_id, device_id) + act_desc)'
new = 'tts_offline_alert(_DEV_TTS_KEY.get(device_id, device_id) + "_" + act)'
code = code.replace(old, new)

# 3. activate_scene: use scene_id + "_activate" key
old = 'tts_offline_alert(scene_name + "场景")'
new = 'tts_offline_alert(scene_id + "_activate")'
code = code.replace(old, new)

# 4. send_chat with scene: use scene_id + "_activate"
old = 'tts_offline_alert(_SCENE_NAMES.get(scene_id, "") + "场景联动")'
new = 'tts_offline_alert(scene_id + "_activate" if scene_id else "send_chat")'
code = code.replace(old, new)

# 5. send_chat without scene
old = 'tts_offline_alert("AI对话")'
new = 'tts_offline_alert("send_chat")'
code = code.replace(old, new)

# 6. add_device
old = 'tts_offline_alert("添加设备")'
new = 'tts_offline_alert("add_device")'
code = code.replace(old, new)

# 7. remove_device: use device_id + "_remove"
old = 'tts_offline_alert(dev_display + "移除")'
new = 'tts_offline_alert(_DEV_TTS_KEY.get(device_id, device_id) + "_remove")'
code = code.replace(old, new)

# 8. get_alerts
old = 'tts_offline_alert("告警查询")'
new = 'tts_offline_alert("get_alerts")'
code = code.replace(old, new)

# 9. get_cameras
old = 'tts_offline_alert("摄像头查询")'
new = 'tts_offline_alert("get_cameras")'
code = code.replace(old, new)

# 10. activate_scene_by_name error
old = 'tts_offline_alert("场景激活")'
new = 'tts_offline_alert("offline_generic")'
code = code.replace(old, new)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patch 5 applied: all tts_offline_alert calls now use TTS keys!")
