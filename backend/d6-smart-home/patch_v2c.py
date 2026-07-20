#!/usr/bin/env python3
"""Patch v2c: Fix tts_offline_alert leftover code in channel.py"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# Remove the leftover old else block code
old_leftover = '''    if not played:
        # 在线失败，蜂鸣降级
        played = _play_beep(frequency=660, duration=0.5)
        play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"

            play_type = "🔊语音" if played else "🔇语音"

        else:

            played = _play_beep(frequency=660, duration=0.5)

            play_type = "🔊蜂鸣" if played else "🔇蜂鸣"'''

new_clean = '''    if not played:
        # 在线失败，蜂鸣降级
        played = _play_beep(frequency=660, duration=0.5)
        play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"'''

if old_leftover in ch:
    ch = ch.replace(old_leftover, new_clean)
    print("[CH-FIX] Removed leftover else block from tts_offline_alert")
else:
    print("[CH-FIX] WARNING: leftover pattern not found, trying flexible")
    import re
    pat = r'play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"\s+play_type = "🔊语音".*?play_type = "🔊蜂鸣" if played else "🔇蜂鸣"'
    m = re.search(pat, ch, re.DOTALL)
    if m:
        ch = ch[:m.start()] + 'play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"' + ch[m.end():]
        print("[CH-FIX] Removed leftover (flexible match)")
    else:
        print("[CH-FIX] ERROR: Could not find leftover")

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)
print("channel.py saved")
