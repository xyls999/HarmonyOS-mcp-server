#!/usr/bin/env python3
"""Patch channel.py + gateway_v3.py - Add TTS config API with speed/volume/enabled"""

# ===== Patch channel.py =====
with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# 1. Add TTS config global (after _TTS_WAV_DIR line)
old_dir = '_TTS_WAV_DIR = Path(__file__).resolve().parent / "tts_wav"'
new_dir = '''_TTS_WAV_DIR = Path(__file__).resolve().parent / "tts_wav"

# ===== TTS 全局配置 (前端可调) =====
_TTS_CONFIG = {
    "speed": 1.0,       # 语速倍率: 0.5=慢半, 1.0=正常, 1.5=快半, 2.0=两倍速
    "volume": 1.0,      # 音量: 0.0=静音, 1.0=满音
    "enabled": True,    # 总开关: False=完全静音不播放
    "backend": "wav",   # 播放后端: "wav"=预生成语音, "beep"=蜂鸣音, "none"=静音
}'''
ch = ch.replace(old_dir, new_dir)

# 2. Replace _play_wav to support speed + volume
old_play_wav = '''def _play_wav(wav_path):
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
        return False'''

new_play_wav = '''def _resample_pcm(pcm_data, sample_width, speed):
    """变速播放: speed>1 跳帧加速, speed<1 重复帧减速"""
    if speed <= 0 or abs(speed - 1.0) < 0.01:
        return pcm_data  # 无需变速
    frame_size = sample_width  # mono
    n_frames = len(pcm_data) // frame_size
    if n_frames == 0:
        return pcm_data
    out = bytearray()
    if speed >= 1.0:
        # 加速: 每隔 speed 帧取一帧
        for i in range(int(n_frames / speed)):
            src_i = int(i * speed)
            if src_i < n_frames:
                out.extend(pcm_data[src_i * frame_size:(src_i + 1) * frame_size])
    else:
        # 减速: 每帧重复 1/speed 次 (线性插值)
        repeat = 1.0 / speed
        for i in range(n_frames):
            n_rep = int(repeat) if i < n_frames - 1 else int(repeat) + (1 if repeat % 1 > 0.5 else 0)
            frame = pcm_data[i * frame_size:(i + 1) * frame_size]
            for _ in range(n_rep):
                out.extend(frame)
    return bytes(out)


def _apply_volume(pcm_data, sample_width, volume):
    """调节音量: volume 0.0~1.0"""
    if volume >= 0.99:
        return pcm_data  # 满音无需处理
    import struct as _struct
    out = bytearray(len(pcm_data))
    if sample_width == 2:  # 16-bit
        for i in range(0, len(pcm_data) - 1, 2):
            val = _struct.unpack_from('<h', pcm_data, i)[0]
            _struct.pack_into('<h', out, i, max(-32768, min(32767, int(val * volume))))
    else:
        return pcm_data  # 只处理16bit
    return bytes(out)


def _play_wav(wav_path):
    """播放 WAV 文件 (通过 pacat + PulseAudio, 支持 speed/volume 调节)"""
    import wave as _wave
    import subprocess as _sp
    try:
        with _wave.open(str(wav_path), "rb") as w:
            sr = w.getframerate()
            nch = w.getnchannels()
            sw = w.getsampwidth()
            frames = w.readframes(w.getnframes())
        # 语速变速
        speed = _TTS_CONFIG.get("speed", 1.0)
        if speed != 1.0 and nch == 1:
            frames = _resample_pcm(frames, sw, speed)
            sr_out = sr  # 保持原采样率, 通过跳帧/重复实现变速
        else:
            sr_out = sr
        # 音量调节
        volume = _TTS_CONFIG.get("volume", 1.0)
        if volume < 0.99 and nch == 1:
            frames = _apply_volume(frames, sw, volume)
        fmt = {1: "u8", 2: "s16le", 3: "s24le", 4: "s32le"}.get(sw, "s16le")
        # pacat volume: 0~65536
        pacat_vol = int(min(1.0, max(0.0, volume)) * 65536)
        proc = _sp.Popen(
            ["pacat", "-p", "--rate={}".format(sr_out), "--format={}".format(fmt), "--volume={}".format(pacat_vol)],
            stdin=_sp.PIPE, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
        proc.stdin.write(frames)
        proc.stdin.close()
        proc.wait(timeout=10)
        return True
    except Exception as e:
        log("[TTS] WAV 播放失败: {}".format(e))
        return False'''

ch = ch.replace(old_play_wav, new_play_wav)

# 3. Replace tts_offline_alert to respect enabled/backend config
old_tts_alert = '''def tts_offline_alert(feature_name):
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

new_tts_alert = '''def tts_offline_alert(feature_name):
    """离线保底反馈: 播放中文语音 WAV + 日志 + 返回保底消息 (受 _TTS_CONFIG 控制)"""
    msg = "{}离线，连通测试成功".format(feature_name)

    # 总开关关闭 → 只写日志不播放
    if not _TTS_CONFIG.get("enabled", True):
        log("[TTS] 🔇 静音 离线提示: {} (TTS disabled)".format(feature_name))
        log("[OFFLINE] ⚠ {}".format(msg))
        return msg

    backend = _TTS_CONFIG.get("backend", "wav")
    played = False

    if backend == "none":
        play_type = "🔇静音"
    elif backend == "beep":
        played = _play_beep(frequency=660, duration=0.5)
        play_type = "🔊蜂鸣" if played else "🔇蜂鸣"
    else:  # "wav" or default
        tts_key = _TTS_WAV_MAP.get(feature_name, "")
        wav_path = _TTS_WAV_DIR / "{}.wav".format(tts_key) if tts_key else None
        if wav_path and wav_path.exists():
            played = _play_wav(wav_path)
            play_type = "🔊语音" if played else "🔇语音"
        else:
            played = _play_beep(frequency=660, duration=0.5)
            play_type = "🔊蜂鸣" if played else "🔇蜂鸣"

    speed = _TTS_CONFIG.get("speed", 1.0)
    vol = _TTS_CONFIG.get("volume", 1.0)
    log("[TTS] {} 离线提示: {} (key={} speed={:.1f} vol={:.1f})".format(
        play_type, feature_name, _TTS_WAV_MAP.get(feature_name, "beep"), speed, vol))
    log("[OFFLINE] ⚠ {}".format(msg))
    return msg'''

ch = ch.replace(old_tts_alert, new_tts_alert)

# 4. Add TTS API endpoints to LocalAPI
old_do_get = '''    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/channel/status":'''

new_do_get = '''    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/tts/config":
            # GET /tts/config → 获取 TTS 配置
            self._j(200, {
                "speed": _TTS_CONFIG.get("speed", 1.0),
                "volume": _TTS_CONFIG.get("volume", 1.0),
                "enabled": _TTS_CONFIG.get("enabled", True),
                "backend": _TTS_CONFIG.get("backend", "wav"),
                "availableBackends": ["wav", "beep", "none"],
                "speedRange": {"min": 0.5, "max": 3.0, "step": 0.1},
                "volumeRange": {"min": 0.0, "max": 1.0, "step": 0.05},
                "wavCount": len(list(_TTS_WAV_DIR.glob("*.wav"))) if _TTS_WAV_DIR.exists() else 0
            })
        elif p == "/tts/list":
            # GET /tts/list → 列出所有可用语音
            wavs = []
            if _TTS_WAV_DIR.exists():
                for f in sorted(_TTS_WAV_DIR.glob("*.wav")):
                    wavs.append({"key": f.stem, "file": f.name, "size": f.stat().st_size})
            self._j(200, {"total": len(wavs), "files": wavs, "map": _TTS_WAV_MAP})
        elif p == "/channel/status":'''

ch = ch.replace(old_do_get, new_do_get)

# 5. Add do_POST for /tts/config and /tts/test
old_else_404 = '''        else:
            self._j(404, {"error": "nf"})'''

new_else_404 = '''        else:
            self._j(404, {"error": "nf"})

    def do_POST(self):
        p = self.path.split("?")[0]
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:
            body = {}

        if p == "/tts/config":
            # POST /tts/config → 更新 TTS 配置
            if "speed" in body:
                s = float(body["speed"])
                _TTS_CONFIG["speed"] = max(0.5, min(3.0, s))
            if "volume" in body:
                v = float(body["volume"])
                _TTS_CONFIG["volume"] = max(0.0, min(1.0, v))
            if "enabled" in body:
                _TTS_CONFIG["enabled"] = bool(body["enabled"])
            if "backend" in body:
                b = str(body["backend"])
                if b in ("wav", "beep", "none"):
                    _TTS_CONFIG["backend"] = b
            log("[TTS] 配置已更新: speed={:.1f} volume={:.1f} enabled={} backend={}".format(
                _TTS_CONFIG["speed"], _TTS_CONFIG["volume"], _TTS_CONFIG["enabled"], _TTS_CONFIG["backend"]))
            self._j(200, {
                "ok": True,
                "config": {
                    "speed": _TTS_CONFIG["speed"],
                    "volume": _TTS_CONFIG["volume"],
                    "enabled": _TTS_CONFIG["enabled"],
                    "backend": _TTS_CONFIG["backend"]
                }
            })
        elif p == "/tts/test":
            # POST /tts/test → 测试播放指定语音
            key = body.get("key", "ping")
            tts_offline_alert(key)
            self._j(200, {"ok": True, "played": key, "config": {
                "speed": _TTS_CONFIG["speed"],
                "volume": _TTS_CONFIG["volume"],
                "enabled": _TTS_CONFIG["enabled"],
                "backend": _TTS_CONFIG["backend"]
            }})
        else:
            self._j(404, {"error": "nf"})'''

ch = ch.replace(old_else_404, new_else_404)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)

print("channel.py patched: TTS config + API endpoints added")

# ===== Patch gateway_v3.py =====
with open("/data/A9/smart_home/gateway_v3.py", "r", encoding="utf-8") as f:
    gw = f.read()

# Add TTS config proxy endpoints to gateway
# Find the GET section and add /api/tts/config and /api/tts/list
old_gw_get = '            elif p=="/api/rag/stats": self._j(200,_rag.get_stats())'
new_gw_get = '''            elif p=="/api/rag/stats": self._j(200,_rag.get_stats())
            elif p=="/api/tts/config":
                # 代理: 从 channel 的 LocalAPI 获取 TTS 配置
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/config", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"speed":1.0,"volume":1.0,"enabled":True,"backend":"wav","error":str(_e)})
            elif p=="/api/tts/list":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/list", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"total":0,"files":[],"error":str(_e)})'''

gw = gw.replace(old_gw_get, new_gw_get)

# Add POST endpoints for TTS
old_gw_post = '            if p=="/api/rag/search": self._j(200,{"results":_rag.search(body.get("query",""),n=body.get("n_results",5))}); return'
new_gw_post = '''            if p=="/api/rag/search": self._j(200,{"results":_rag.search(body.get("query",""),n=body.get("n_results",5))}); return
            if p=="/api/tts/config":
                # 代理: 更新 TTS 配置
                try:
                    import urllib.request as _ureq
                    _bd = json.dumps(body, ensure_ascii=False).encode()
                    _req = _ureq.Request("http://127.0.0.1:8081/tts/config", data=_bd, headers={"Content-Type":"application/json"})
                    with _ureq.urlopen(_req, timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(500, {"ok":False,"error":str(_e)})
            if p=="/api/tts/test":
                try:
                    import urllib.request as _ureq
                    _bd = json.dumps(body, ensure_ascii=False).encode()
                    _req = _ureq.Request("http://127.0.0.1:8081/tts/test", data=_bd, headers={"Content-Type":"application/json"})
                    with _ureq.urlopen(_req, timeout=5) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(500, {"ok":False,"error":str(_e)})'''

gw = gw.replace(old_gw_post, new_gw_post)

with open("/data/A9/smart_home/gateway_v3.py", "w", encoding="utf-8") as f:
    f.write(gw)

print("gateway_v3.py patched: TTS config proxy endpoints added")
print("Done!")
