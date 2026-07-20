#!/usr/bin/env python3
"""Patch v3: Fix concurrent oh_play issue - add audio lock to _play_mp3"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# Add a global audio lock before _play_mp3
old_play_mp3 = '''def _play_mp3(mp3_path):

    """播放 MP3 文件 (通过 oh_play 播放器, 支持 MP3/WAV 任意格式)"""

    import subprocess as _sp

    import os as _os

    try:

        oh_play = "/data/A9/oh_play_bin"

        if not _os.path.exists(oh_play):

            log("[TTS-ONLINE] oh_play 播放器不存在, 音频已缓存供前端播放")

            return True

        env = _os.environ.copy()

        env["LD_LIBRARY_PATH"] = "/system/lib:/system/lib/ndk:/system/lib/platformsdk:/system/lib/chipset-pub-sdk"

        result = _sp.run([oh_play, mp3_path], timeout=15, capture_output=True, env=env)

        if result.returncode == 0:

            log(f"[TTS-ONLINE] ✓ 播放成功: {mp3_path}")

            return True

        else:

            log(f"[TTS-ONLINE] 播放失败(rc={result.returncode}), 音频已缓存")

            return True  # 缓存仍可用

    except Exception as e:

        log(f"[TTS-ONLINE] 播放异常: {e}")

        return True  # 缓存仍可用'''

new_play_mp3 = '''# 音频播放锁: oh_play 不支持并发, 必须串行播放
_audio_lock = threading.Lock()

def _play_mp3(mp3_path):
    """播放 MP3 文件 (通过 oh_play 播放器, 串行播放避免并发冲突)"""
    import subprocess as _sp
    import os as _os
    with _audio_lock:
        try:
            oh_play = "/data/A9/oh_play_bin"
            if not _os.path.exists(oh_play):
                log("[TTS-ONLINE] oh_play 播放器不存在, 音频已缓存供前端播放")
                return True
            env = _os.environ.copy()
            env["LD_LIBRARY_PATH"] = "/system/lib:/system/lib/ndk:/system/lib/platformsdk:/system/lib/chipset-pub-sdk"
            result = _sp.run([oh_play, mp3_path], timeout=15, capture_output=True, env=env)
            if result.returncode == 0:
                log(f"[TTS-ONLINE] ✓ 播放成功: {mp3_path}")
                return True
            else:
                log(f"[TTS-ONLINE] 播放失败(rc={result.returncode}), 音频已缓存")
                return True
        except Exception as e:
            log(f"[TTS-ONLINE] 播放异常: {e}")
            return True'''

if old_play_mp3 in ch:
    ch = ch.replace(old_play_mp3, new_play_mp3)
    print("[1] Added _audio_lock to _play_mp3 (serial playback)")
else:
    print("[1] WARNING: _play_mp3 pattern not found")

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)
print("channel.py saved")
