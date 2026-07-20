#!/usr/bin/env python3
"""Patch channel.py - make TTS actually play audio via pacat"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    code = f.read()

# Replace tts_offline_alert to actually play audio
old_tts = '''def tts_offline_alert(feature_name):
    """离线保底反馈: 生成蜂鸣 WAV + 日志输出 + 返回保底消息"""
    wav_dir = Path(__file__).resolve().parent / "tts_cache"
    wav_dir.mkdir(parents=True, exist_ok=True)
    wav_path = wav_dir / f"offline_{int(time.time())}.wav"
    try:
        _make_beep_wav(str(wav_path), frequency=660, duration=0.5)
        log(f"[TTS] 🔔 离线提示音: {wav_path}")
    except Exception as e:
        log(f"[TTS] 生成提示音失败: {e}")
    msg = f"{feature_name}离线，连通测试成功"
    log(f"[OFFLINE] ⚠ {msg}")
    return msg'''

new_tts = '''def _play_beep(frequency=660, duration=0.5, sample_rate=8000):
    """通过 pacat 直接播放蜂鸣音 (HarmonyOS PulseAudio)"""
    import struct as _struct
    import math as _math
    import subprocess as _sp
    n_samples = int(sample_rate * duration)
    samples = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        env = min(1.0, min(i, n_samples - i) / (sample_rate * 0.02))
        val = int(32767 * 0.5 * env * _math.sin(2 * _math.pi * frequency * t))
        samples.extend(_struct.pack('<h', max(-32768, min(32767, val))))
    try:
        proc = _sp.Popen(
            ['pacat', '-p', '--rate={}'.format(sample_rate), '--format=s16le',
             '--volume=65536'],
            stdin=_sp.PIPE, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
        proc.stdin.write(bytes(samples))
        proc.stdin.close()
        proc.wait(timeout=3)
        return True
    except Exception as e:
        log("[TTS] pacat 播放失败: {}".format(e))
        return False


def tts_offline_alert(feature_name):
    """离线保底反馈: 播放蜂鸣音 + 日志输出 + 返回保底消息"""
    # 1. 播放蜂鸣音 (pacat 直出 PCM)
    played = _play_beep(frequency=660, duration=0.5)
    # 2. 同时保存 WAV 备份
    wav_dir = Path(__file__).resolve().parent / "tts_cache"
    wav_dir.mkdir(parents=True, exist_ok=True)
    wav_path = wav_dir / "offline_{}.wav".format(int(time.time()))
    try:
        _make_beep_wav(str(wav_path), frequency=660, duration=0.5)
    except Exception:
        pass
    play_icon = "🔊" if played else "🔇"
    log("[TTS] {} 离线提示: {} (wav={})".format(play_icon, feature_name, wav_path.name))
    msg = "{}离线，连通测试成功".format(feature_name)
    log("[OFFLINE] ⚠ {}".format(msg))
    return msg'''

code = code.replace(old_tts, new_tts)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patch 3 applied: TTS now plays audio via pacat!")
