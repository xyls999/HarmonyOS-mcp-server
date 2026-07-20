#!/usr/bin/env python3
"""Patch channel.py - use pre-generated Chinese TTS WAV files instead of beep"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    code = f.read()

# Replace _play_beep and tts_offline_alert with WAV-based TTS
old_play_beep_and_tts = '''def _play_beep(frequency=660, duration=0.5, sample_rate=8000):
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

new_tts = '''# ===== TTS 语音映射表 =====
# 每个指令/设备/场景对应一个预生成的中文语音 WAV 文件
_TTS_WAV_MAP = {
    # 查询类
    "ping": "ping", "get_server_status": "get_server_status",
    "get_status": "get_status", "get_devices": "get_devices",
    "get_sensors": "get_sensors", "get_scenes": "get_scenes",
    "get_user": "get_user", "get_operations": "get_operations",
    "get_chat_history": "get_chat_history", "rag_search": "rag_search",
    "update_user": "update_user", "get_alerts": "get_alerts",
    "get_cameras": "get_cameras",
    # 设备开关
    "light_01_toggle": "toggle_light_01", "door_01_toggle": "toggle_door_01",
    "alarm_01_toggle": "toggle_alarm_01", "light_02_toggle": "toggle_light_02",
    "curtain_01_toggle": "toggle_curtain_01", "light_03_toggle": "toggle_light_03",
    "fan_02_toggle": "toggle_fan_02", "light_04_toggle": "toggle_light_04",
    "nfc_01_toggle": "toggle_nfc_01", "voice_01_toggle": "toggle_voice_01",
    "radar_01_toggle": "toggle_radar_01", "fan_01_toggle": "toggle_fan_01",
    "exhaust_01_toggle": "toggle_exhaust_01", "light_05_toggle": "toggle_light_05",
    "camera_01_toggle": "toggle_camera_01",
    # 设备控制
    "ac_01_set_temp": "ctrl_ac_temp", "ac_01_set_mode": "ctrl_ac_mode",
    "ac_01_set_speed": "ctrl_ac_speed", "light_set_brightness": "ctrl_light_brightness",
    "curtain_01_ctrl": "ctrl_curtain",
    # 场景
    "s1_activate": "scene_s1", "s2_activate": "scene_s2",
    "s3_activate": "scene_s3", "s4_activate": "scene_s4",
    "s5_activate": "scene_s5",
    # 特殊
    "add_device": "add_device", "remove_device": "remove_device",
    "send_chat": "send_chat",
    # 通用
    "offline_generic": "offline_generic", "channel_ok": "channel_ok",
}

# 设备ID → TTS key 映射
_DEV_TTS_KEY = {
    "light_01": "light_01", "door_01": "door_01", "alarm_01": "alarm_01",
    "light_02": "light_02", "curtain_01": "curtain_01", "light_03": "light_03",
    "fan_02": "fan_02", "light_04": "light_04", "nfc_01": "nfc_01",
    "voice_01": "voice_01", "radar_01": "radar_01", "fan_01": "fan_01",
    "exhaust_01": "exhaust_01", "light_05": "light_05", "camera_01": "camera_01",
    "ac_01": "ac_01",
}

_TTS_WAV_DIR = Path(__file__).resolve().parent / "tts_wav"


def _play_wav(wav_path):
    """播放 WAV 文件 (通过 pacat + PulseAudio)"""
    import wave as _wave
    import subprocess as _sp
    try:
        with _wave.open(str(wav_path), "rb") as w:
            sr = w.getframerate()
            nch = w.getnchannels()
            sw = w.getsampwidth()
            frames = w.readframes(w.getnframes())
        fmt = {1: "u8", 2: "s16le", 3: "s24le", 4: "s32le"}.get(sw, "s16le")
        proc = _sp.Popen(
            ["pacat", "-p", "--rate={}".format(sr), "--format={}".format(fmt), "--volume=65536"],
            stdin=_sp.PIPE, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
        proc.stdin.write(frames)
        proc.stdin.close()
        proc.wait(timeout=10)
        return True
    except Exception as e:
        log("[TTS] WAV 播放失败: {}".format(e))
        return False


def _play_beep(frequency=660, duration=0.5, sample_rate=8000):
    """蜂鸣音后备 (WAV 文件不存在时使用)"""
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
            ['pacat', '-p', '--rate={}'.format(sample_rate), '--format=s16le', '--volume=65536'],
            stdin=_sp.PIPE, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
        proc.stdin.write(bytes(samples))
        proc.stdin.close()
        proc.wait(timeout=3)
        return True
    except Exception as e:
        log("[TTS] 蜂鸣后备失败: {}".format(e))
        return False


def tts_offline_alert(feature_name):
    """离线保底反馈: 播放中文语音 WAV + 日志 + 返回保底消息"""
    # 1. 查找对应的 WAV 文件
    tts_key = _TTS_WAV_MAP.get(feature_name, "")
    wav_path = _TTS_WAV_DIR / "{}.wav".format(tts_key) if tts_key else None

    played = False
    if wav_path and wav_path.exists():
        # 播放预生成的中文语音
        played = _play_wav(wav_path)
        play_type = "🔊语音" if played else "🔇语音"
    else:
        # 后备: 播放蜂鸣音
        played = _play_beep(frequency=660, duration=0.5)
        play_type = "🔊蜂鸣" if played else "🔇蜂鸣"

    log("[TTS] {} 离线提示: {} (key={})".format(play_type, feature_name, tts_key or "beep"))
    msg = "{}离线，连通测试成功".format(feature_name)
    log("[OFFLINE] ⚠ {}".format(msg))
    return msg'''

code = code.replace(old_play_beep_and_tts, new_tts)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patch 4 applied: TTS now plays Chinese voice WAV files!")
print("Fallback to beep if WAV not found.")
