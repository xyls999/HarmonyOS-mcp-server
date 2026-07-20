#!/usr/bin/env python3
"""Patch channel.py - fix finally block to pass action as TTS key"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    code = f.read()

# Fix finally block: pass action (English key) instead of action_name (Chinese)
old = '''            tts_offline_alert(action_name)
            result["hardwareOnline"] = False
            result["message"] = f"{action_name}成功，硬件未接入，连通测试成功"'''

new = '''            tts_offline_alert(action)  # 传英文 action key, 匹配 _TTS_WAV_MAP
            result["hardwareOnline"] = False
            result["message"] = f"{action_name}成功，硬件未接入，连通测试成功"'''

code = code.replace(old, new)

# Also fix the except block
old2 = '''        offline_msg = tts_offline_alert(action_name)'''
new2 = '''        offline_msg = tts_offline_alert(action)  # 传英文 action key'''

code = code.replace(old2, new2)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patch 6 applied: finally and except blocks now pass action key!")
