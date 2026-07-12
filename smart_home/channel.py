#!/usr/bin/env python3

"""

网络通道服务 · WebSocket 长连接 · 纯标准库实现

设备端主动连 yuanzhe.tech，保持长连接，双向实时通信



功能:

  - 设备→云端: 实时推送设备/传感器/场景/操作等数据

  - 云端→设备: 远程下发指令(开关设备/激活场景/查询状态)

  - 断线自动重连 (指数退避)

  - 心跳保活 (30s)

  - 本地 HTTP API 供前端/调试使用



运行环境: HarmonyOS ARM32 + Python 3.14.5 (纯标准库)

部署位置: /data/A9/smart_home/channel.py

"""

from __future__ import annotations

import base64

import hashlib

import json

import os

import socket

import ssl

import struct

import sqlite3

import threading

import time

import sys

from datetime import datetime

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from urllib.request import Request, urlopen

# 硬件控制桥接
from hardware_bridge import hw_toggle, hw_control, hw_scene_execute



# ===== 配置 =====

WS_URL = os.environ.get("WS_URL", "ws://yuanzhe.tech/ws/smart-home")

WS_TOKEN = os.environ.get("WS_TOKEN", "")  # 认证 token

HEARTBEAT_INTERVAL = 30  # 秒

RECONNECT_BASE = 2  # 重连退避基数(秒)

RECONNECT_MAX = 60  # 最大退避(秒)

LOCAL_API_PORT = 8081  # 本地调试 API 端口



ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / "control" / "data" / "smart_home.db"

LOG_PATH = ROOT / "channel.log"



# 状态

_ws = None  # WebSocket 连接

_connected = False

_lock = threading.Lock()

_running = True

_last_msg_id = 0

_pending_responses = {}  # msg_id → {event, result, error}





def log(msg):

    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"

    print(line, flush=True)

    try:

        with open(LOG_PATH, "a", encoding="utf-8") as f:

            f.write(line + "\n")

    except Exception:

        pass





def _db():

    return sqlite3.connect(str(DB_PATH))





def next_msg_id():

    global _last_msg_id

    _last_msg_id += 1

    return _last_msg_id





# ===== WebSocket 协议 (RFC 6455) 纯标准库实现 =====



def _ws_handshake(host, port, path, token=""):

    """WebSocket 握手，返回 socket"""

    key = base64.b64encode(os.urandom(16)).decode()

    headers = [

        f"GET {path} HTTP/1.1",

        f"Host: {host}",

        "Upgrade: websocket",

        "Connection: Upgrade",

        f"Sec-WebSocket-Key: {key}",

        "Sec-WebSocket-Version: 13",

    ]

    if token:

        headers.append(f"Authorization: Bearer {token}")

    headers.append("")

    headers.append("")



    sock = socket.create_connection((host, port), timeout=15)

    sock.sendall("\r\n".join(headers).encode())



    # 读取握手响应

    resp = b""

    while b"\r\n\r\n" not in resp:

        chunk = sock.recv(4096)

        if not chunk:

            sock.close()

            raise ConnectionError("WebSocket 握手失败: 连接关闭")

        resp += chunk



    status_line = resp.split(b"\r\n")[0].decode()

    if "101" not in status_line:

        sock.close()

        raise ConnectionError(f"WebSocket 握手失败: {status_line}")



    # 验证 Sec-WebSocket-Accept

    accept_key = base64.b64encode(

        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-5AB5A865B1D7").encode()).digest()

    ).decode()

    if accept_key.encode() not in resp:

        log("[WS] ⚠ Accept key 不匹配，继续使用")



    return sock





def _ws_send(sock, data, opcode=0x1):

    """发送 WebSocket 帧 (opcode=0x1 文本, 0x8 关闭, 0x9 ping, 0xA pong)"""

    payload = data.encode("utf-8") if isinstance(data, str) else data

    mask = os.urandom(4)

    masked = bytearray(len(payload))

    for i in range(len(payload)):

        masked[i] = payload[i] ^ mask[i % 4]



    frame = bytearray()

    frame.append(0x80 | opcode)  # FIN + opcode



    length = len(payload)

    if length < 126:

        frame.append(0x80 | length)  # MASK + length

    elif length < 65536:

        frame.append(0x80 | 126)

        frame.extend(struct.pack("!H", length))

    else:

        frame.append(0x80 | 127)

        frame.extend(struct.pack("!Q", length))



    frame.extend(mask)

    frame.extend(masked)



    try:

        sock.sendall(bytes(frame))

    except OSError as e:

        log(f"[WS] 发送失败: {e} (opcode={opcode} size={len(payload)})")

        raise





def _ws_recv(sock):

    """接收一帧 WebSocket 数据，返回 (opcode, payload) 或 None"""

    header = _recv_exact(sock, 2)

    if not header:

        return None



    opcode = header[0] & 0x0F

    masked = bool(header[1] & 0x80)

    length = header[1] & 0x7F



    if length == 126:

        ext = _recv_exact(sock, 2)

        if not ext:

            return None

        length = struct.unpack("!H", ext)[0]

    elif length == 127:

        ext = _recv_exact(sock, 8)

        if not ext:

            return None

        length = struct.unpack("!Q", ext)[0]



    mask_key = None

    if masked:

        mask_key = _recv_exact(sock, 4)

        if not mask_key:

            return None



    payload = _recv_exact(sock, length)

    if payload is None:

        return None



    if masked and mask_key:

        unmasked = bytearray(length)

        for i in range(length):

            unmasked[i] = payload[i] ^ mask_key[i % 4]

        payload = bytes(unmasked)



    return opcode, payload





def _recv_exact(sock, n):

    """精确接收 n 字节"""

    buf = bytearray()

    while len(buf) < n:

        try:

            chunk = sock.recv(n - len(buf))

            if not chunk:

                return None

            buf.extend(chunk)

        except (socket.timeout, OSError):

            return None

    return bytes(buf)





# ===== 数据采集 (复用 data_pusher 的逻辑) =====



def collect_all():

    """采集全量数据"""

    conn = _db()

    # 设备

    devices = []

    for r in conn.execute("SELECT id,name,type,status,room,icon,primary_value,is_on,mode,battery,protocol,updated_at FROM devices").fetchall():

        d = {"id": r[0], "name": r[1], "type": r[2], "status": r[3], "room": r[4], "icon": r[5],

             "primaryValue": r[6], "isOn": bool(r[7]), "updatedAt": r[11]}

        if r[8] is not None: d["mode"] = r[8]

        if r[9] is not None: d["battery"] = r[9]

        if r[10] is not None: d["protocol"] = r[10]

        devices.append(d)



    # 传感器

    sensors = []

    for r in conn.execute("SELECT id,name,type,sensor_group,room,icon,current_value,unit,threshold_min,threshold_max,protocol,is_alert,updated_at FROM sensors").fetchall():

        s = {"id": r[0], "name": r[1], "type": r[2], "group": r[3], "room": r[4], "icon": r[5],

             "current": {"value": r[6], "unit": r[7]}, "isAlert": bool(r[11]), "updatedAt": r[12]}

        if r[8] is not None: s["thresholdMin"] = r[8]

        if r[9] is not None: s["thresholdMax"] = r[9]

        if r[10] is not None: s["protocol"] = r[10]

        sensors.append(s)



    # 场景

    scenes = []

    for s in conn.execute("SELECT id,name,icon,color,is_active,description,updated_at FROM scenes").fetchall():

        actions = []

        for a in conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order", (s[0],)).fetchall():

            act = {"deviceId": a[0], "isOn": bool(a[1])}

            if a[2] is not None: act["primaryValue"] = a[2]

            actions.append(act)

        scenes.append({"id": s[0], "name": s[1], "icon": s[2], "color": s[3],

                       "isActive": bool(s[4]), "description": s[5], "actions": actions, "updatedAt": s[6]})



    # 操作记录

    operations = []

    for r in conn.execute("SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations ORDER BY created_at DESC LIMIT 200").fetchall():

        operations.append({"deviceId": r[0], "action": r[1], "params": r[2],

                          "result": r[3], "source": r[4], "sceneId": r[5], "timestamp": r[6]})



    # 对话历史

    chat_history = []

    for r in conn.execute("SELECT user_id,role,content,scene_id,tools_used,created_at FROM chat_history ORDER BY created_at DESC LIMIT 100").fetchall():

        chat_history.append({"userId": r[0], "role": r[1], "content": r[2],

                            "sceneId": r[3], "toolsUsed": r[4], "timestamp": r[5]})



    # 用户

    u = conn.execute("SELECT id,nickname,home_name,member_count,avatar,updated_at FROM users WHERE id='u001'").fetchone()

    dc = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]

    user = {"id": u[0], "nickname": u[1], "homeName": u[2], "memberCount": u[3],

            "avatar": u[4], "deviceCount": dc, "updatedAt": u[5]} if u else {"id": "u001", "deviceCount": dc}



    conn.close()



    return {

        "devices": devices, "sensors": sensors, "scenes": scenes,

        "operations": operations, "chatHistory": chat_history, "user": user,

        "serverStatus": {

            "host": "192.168.1.81", "port": 8080, "isOnline": True,

            "protocol": "wifi", "version": "v3", "channelVersion": "1.0.0",

            "python": sys.version.split()[0]

        }

    }





# ===== TTS / 音频反馈 (纯标准库) =====



# 设备中文名映射 (用于设备级离线提示)

_DEVICE_NAMES = {

    "ac_01": "客厅空调", "fan_01": "客厅吊扇", "door_01": "客厅大门",

    "alarm_01": "蜂鸣警报", "light_01": "客厅主灯", "light_05": "客厅氛围灯",

    "camera_01": "客厅摄像头", "light_02": "厨房灯", "exhaust_01": "抽风机",

    "curtain_01": "智能窗帘", "light_03": "卧室灯", "fan_02": "换气扇",

    "light_04": "卫生间灯", "nfc_01": "NFC门禁", "voice_01": "语音中控",

    "radar_01": "毫米波雷达",

    # 传感器

    "temp_01": "客厅温度", "humid_01": "客厅湿度", "light_s_01": "客厅光照",

    "air_01": "空气质量", "pir_01": "人体感应", "smoke_01": "烟雾检测",

    "heat_01": "热敏火灾", "door_s_01": "门窗感应", "power_01": "总功率",

    # 摄像头

    "cam_01": "客厅摄像头", "cam_02": "门口摄像头",

}



# 场景中文名映射

_SCENE_NAMES = {

    "s1": "回家", "s2": "离家", "s3": "睡眠", "s4": "观影", "s5": "用餐",

}





def _make_beep_wav(filename, frequency=880, duration=0.3, sample_rate=8000):

    """生成蜂鸣 WAV 文件 (纯 Python, 无需第三方库)"""

    import struct as _struct

    import math as _math

    n_samples = int(sample_rate * duration)

    samples = bytearray()

    for i in range(n_samples):

        # 正弦波 + 淡入淡出

        t = i / sample_rate

        env = min(1.0, min(i, n_samples - i) / (sample_rate * 0.02))  # 20ms 淡入淡出

        val = int(32767 * 0.5 * env * _math.sin(2 * _math.pi * frequency * t))

        samples.extend(_struct.pack('<h', max(-32768, min(32767, val))))

    data = bytes(samples)

    header = _struct.pack('<4sI4s', b'RIFF', 36 + len(data), b'WAVE')

    fmt_chunk = _struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)

    data_chunk = _struct.pack('<4sI', b'data', len(data))

    with open(filename, 'wb') as f:

        f.write(header + fmt_chunk + data_chunk + data)





# ===== TTS 语音映射表 =====

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



# ===== TTS 全局配置 (前端可调) =====

_TTS_CONFIG = {

    "speed": 1.0,       # 语速倍率: 0.5=慢半, 1.0=正常, 1.5=快半, 2.0=两倍速

    "volume": 1.0,      # 音量: 0.0=静音, 1.0=满音

    "enabled": True,    # 总开关: False=完全静音不播放

    "backend": "online", # 播放后端: "online"=在线语音合成, "wav"=预生成语音, "beep"=蜂鸣音, "none"=静音

}



# ===== AI 对话后端配置 (前端可调) =====

_AI_CONFIG = {

    "provider": "astron",  # 当前使用的 AI 后端: "deepseek" / "iflytek" / "astron" / "custom"

    "models": {

        "deepseek": {

            "url": "https://api.deepseek.com/chat/completions",

            "key": os.environ.get("DEEPSEEK_API_KEY", ""),

            "model": "deepseek-chat",

            "maxTokens": 200,

            "temperature": 0.3,

        },

        "iflytek": {

            "url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",

            "key": os.environ.get("IFLYTEK_API_KEY", ""),

            "model": "4.0Ultra",

            "maxTokens": 200,

            "temperature": 0.3,

        },

        "astron": {

            "url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",

            "key": os.environ.get("ASTRON_API_KEY", ""),

            "model": "astron-code-latest",

            "maxTokens": 32768,

            "temperature": 0.3,

        },

        "custom": {

            "url": "",

            "key": "",

            "model": "",

            "maxTokens": 200,

            "temperature": 0.3,

        },

    },

}





def _resample_pcm(pcm_data, sample_width, speed):

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

        return False





def _play_beep(frequency=660, duration=0.5, sample_rate=8000):

    """蜂鸣音后备 (WAV 文件不存在时使用)"""

    import struct as _struct

    import math as _math

    import subprocess as _sp

    # Note: primary audio playback now uses oh_play

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









# ===== 在线 TTS (百度翻译语音合成) =====

_TTS_CACHE_DIR = Path(__file__).resolve().parent / "tts_cache"



# 语音文本映射表: 每个操作对应的中文播报文本

_TTS_TEXT_MAP = {

    # --- 查询类 ---

    "ping": "连通测试成功",

    "get_server_status": "服务状态正常",

    "get_status": "全量状态查询完成",

    "get_devices": "设备列表查询完成",

    "get_sensors": "传感器数据查询完成",

    "get_scenes": "场景列表查询完成",

    "get_user": "用户信息查询完成",

    "get_operations": "操作记录查询完成",

    "get_chat_history": "对话历史查询完成",

    "rag_search": "知识搜索完成",

    "update_user": "用户信息已更新",

    "get_alerts": "告警信息查询完成",

    "get_cameras": "摄像头状态查询完成",

    # --- 设备开关 ---

    "light_01_toggle": "客厅主灯已切换",

    "door_01_toggle": "客厅大门已切换",

    "alarm_01_toggle": "蜂鸣警报已切换",

    "light_02_toggle": "厨房灯已切换",

    "curtain_01_toggle": "智能窗帘已切换",

    "light_03_toggle": "卧室灯已切换",

    "fan_02_toggle": "换气扇已切换",

    "light_04_toggle": "卫生间灯已切换",

    "nfc_01_toggle": "NFC门禁已切换",

    "voice_01_toggle": "语音中控已切换",

    "radar_01_toggle": "毫米波雷达已切换",

    "fan_01_toggle": "客厅吊扇已切换",

    "exhaust_01_toggle": "抽风机已切换",

    "light_05_toggle": "客厅氛围灯已切换",

    "camera_01_toggle": "客厅摄像头已切换",

    "ac_01_toggle": "客厅空调已切换",

    # --- 设备控制 ---

    "ac_01_set_temp": "空调温度已调节",

    "ac_01_set_mode": "空调模式已切换",

    "ac_01_set_speed": "空调风速已调节",

    "light_set_brightness": "灯光亮度已调节",

    "curtain_01_ctrl": "窗帘开合度已调节",

    # --- 场景 ---

    "s1_activate": "欢迎回家，回家模式已激活",

    "s2_activate": "离家模式已激活，注意安全",

    "s3_activate": "睡眠模式已激活，晚安",

    "s4_activate": "观影模式已激活，请享受",

    "s5_activate": "用餐模式已激活，请慢用",

    # --- 特殊 ---

    "add_device": "新设备已添加",

    "remove_device": "设备已移除",

    "send_chat": "AI对话完成",  # 仅作为离线保底key，实际对话播报用 tts_speak(reply)

    # --- 通用 ---

    "offline_generic": "操作完成",

    "channel_ok": "通道连接正常",

}



# 设备操作动态语音模板 (根据实际状态生成)

_TTS_DYNAMIC_TEMPLATES = {

    "light_01_toggle": lambda is_on, pv: f"客厅主灯已{'开启' if is_on else '关闭'}",

    "door_01_toggle": lambda is_on, pv: f"客厅大门已{'解锁' if is_on else '锁定'}",

    "alarm_01_toggle": lambda is_on, pv: f"蜂鸣警报已{'开启' if is_on else '关闭'}",

    "light_02_toggle": lambda is_on, pv: f"厨房灯已{'开启' if is_on else '关闭'}",

    "curtain_01_toggle": lambda is_on, pv: f"智能窗帘已{'开启' if is_on else '关闭'}",

    "light_03_toggle": lambda is_on, pv: f"卧室灯已{'开启' if is_on else '关闭'}",

    "fan_02_toggle": lambda is_on, pv: f"换气扇已{'开启' if is_on else '关闭'}",

    "light_04_toggle": lambda is_on, pv: f"卫生间灯已{'开启' if is_on else '关闭'}",

    "nfc_01_toggle": lambda is_on, pv: f"NFC门禁已{'开启' if is_on else '关闭'}",

    "voice_01_toggle": lambda is_on, pv: f"语音中控已{'开启' if is_on else '关闭'}",

    "radar_01_toggle": lambda is_on, pv: f"毫米波雷达已{'开启' if is_on else '关闭'}",

    "fan_01_toggle": lambda is_on, pv: f"客厅吊扇已{'开启' if is_on else '关闭'}",

    "exhaust_01_toggle": lambda is_on, pv: f"抽风机已{'开启' if is_on else '关闭'}",

    "light_05_toggle": lambda is_on, pv: f"客厅氛围灯已{'开启' if is_on else '关闭'}",

    "camera_01_toggle": lambda is_on, pv: f"客厅摄像头已{'开启' if is_on else '关闭'}",

    "ac_01_toggle": lambda is_on, pv: f"客厅空调已{'开启' if is_on else '关闭'}",

    "ac_01_set_temp": lambda is_on, pv: f"空调温度已设置为{pv}度" if pv else "空调温度已调节",

    "ac_01_set_mode": lambda is_on, pv: f"空调模式已切换为{pv}" if pv else "空调模式已切换",

    "ac_01_set_speed": lambda is_on, pv: f"空调风速已设置为{pv}" if pv else "空调风速已调节",

    "light_set_brightness": lambda is_on, pv: f"灯光亮度已设置为{pv}%" if pv else "灯光亮度已调节",

    "curtain_01_ctrl": lambda is_on, pv: f"窗帘开合度已设置为{pv}%" if pv else "窗帘开合度已调节",

}







def _voice_url(text, speed=5):

    """Get audio URL for frontend playback"""

    import hashlib as _hl

    cfg_speed = _TTS_CONFIG.get("speed", 1.0)

    if speed == 5:

        speed = max(1, min(10, int(3 + cfg_speed * 4)))

    cache_key = _hl.md5(f"{text}_{speed}".encode()).hexdigest()

    cache_file = _TTS_CACHE_DIR / f"{cache_key}.mp3"

    if cache_file.exists() and cache_file.stat().st_size > 500:

        return f"/api/tts/audio/{cache_key}.mp3"

    return None



def _build_voice_sequence(texts, interval_ms=500):

    """Build voiceSequence for frontend playback"""

    seq = []

    for i, text in enumerate(texts):

        url = _voice_url(text)

        entry = {"text": text}

        if url:

            entry["audioUrl"] = url

        if i > 0:

            entry["delay"] = interval_ms

        seq.append(entry)

    return seq



def _tts_online(text, speed=5):

    """在线 TTS: 调用百度翻译语音合成 API，返回 MP3 文件路径或 None



    API: https://fanyi.baidu.com/gettts?lan=zh&text=...&spd=N&source=web

    - lan: 语言 (zh=中文)

    - text: 要合成的文本 (URL编码)

    - spd: 语速 (1-10, 5=正常)

    - source: 固定 "web"

    返回: MP3 文件路径 或 None

    """

    import ssl as _ssl

    from urllib.parse import quote as _quote



    if not text or not text.strip():

        return None



    # 语速映射: _TTS_CONFIG.speed (0.5-3.0) → baidu spd (1-10)

    cfg_speed = _TTS_CONFIG.get("speed", 1.0)

    if speed == 5:  # 使用默认映射

        speed = max(1, min(10, int(3 + cfg_speed * 4)))  # 0.5→5, 1.0→7, 2.0→11→10



    # 缓存: 用 text+speed 做 key

    _TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_key = hashlib.md5(f"{text}_{speed}".encode()).hexdigest()

    cache_file = _TTS_CACHE_DIR / f"{cache_key}.mp3"



    # 命中缓存

    if cache_file.exists() and cache_file.stat().st_size > 500:

        log(f"[TTS-ONLINE] 缓存命中: {text[:20]}...")

        return str(cache_file)



    # 调用百度翻译 TTS

    try:

        ctx = _ssl.create_default_context(cafile="/data/A9/certs/cacert.pem")

        encoded = _quote(text)

        url = f"https://fanyi.baidu.com/gettts?lan=zh&text={encoded}&spd={speed}&source=web"

        req = Request(url)

        req.add_header("User-Agent", "Mozilla/5.0 (Linux; HarmonyOS) Chrome/120.0")

        req.add_header("Referer", "https://fanyi.baidu.com/")



        with urlopen(req, timeout=15, context=ctx) as r:

            data = r.read()

            ct = r.headers.get("Content-Type", "")



            if len(data) < 500 or "audio" not in ct:

                log(f"[TTS-ONLINE] 响应异常: {len(data)} bytes, type={ct}")

                return None



            # 保存缓存

            with open(cache_file, "wb") as f:

                f.write(data)

            log(f"[TTS-ONLINE] 合成成功: {text[:20]}... ({len(data)} bytes)")

            return str(cache_file)



    except Exception as e:

        log(f"[TTS-ONLINE] 合成失败: {e}")

        return None





# 音频播放锁: oh_play 不支持并发, 必须串行播放
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
            return True





def _tts_speak_sync(text, speed=5):
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
    return True  # 已提交后台播放





def tts_speak_key(key, is_on=None, primary_value=None):

    """按操作 key 播报语音 (支持动态文本)



    Args:

        key: 操作 key (如 "light_01_toggle", "s1_activate")

        is_on: 设备开关状态 (用于动态模板)

        primary_value: 设备主值 (用于动态模板)

    Returns:

        True=播放成功, False=播放失败

    """

    # 优先使用动态模板

    if is_on is not None and key in _TTS_DYNAMIC_TEMPLATES:

        try:

            text = _TTS_DYNAMIC_TEMPLATES[key](is_on, primary_value)

        except Exception:

            text = _TTS_TEXT_MAP.get(key, "")

    else:

        text = _TTS_TEXT_MAP.get(key, "")



    if not text:

        log(f"[TTS-ONLINE] 无语音映射: {key}")

        return False



    return tts_speak(text)



# 离线播报节流: 同一 key 在 _OFFLINE_THROTTLE_SEC 秒内只播报一次

_OFFLINE_THROTTLE_SEC = 60  # 秒

_OFFLINE_LAST_SPOKEN = {}  # key -> last_spoken_timestamp



def tts_offline_alert(feature_name):
    """离线保底反馈: 使用在线TTS播报 (不再使用预录WAV)"""
    msg = "{}离线，连通测试成功".format(feature_name)



    # 节流: 同一 key 在 60 秒内不重复播报语音

    import time as _time

    _now = _time.time()

    _last = _OFFLINE_LAST_SPOKEN.get(feature_name, 0)

    _throttled = (_now - _last) < _OFFLINE_THROTTLE_SEC

    if _throttled:

        # 只写日志，不播报

        log("[OFFLINE] ⚠ {} (节流，{}秒内已播报)".format(msg, int(_OFFLINE_THROTTLE_SEC)))

        return msg

    _OFFLINE_LAST_SPOKEN[feature_name] = _now



    # 总开关关闭 → 只写日志不播放
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
        play_type = "🔊蜂鸣降级" if played else "🔇蜂鸣降级"



    speed = _TTS_CONFIG.get("speed", 1.0)

    vol = _TTS_CONFIG.get("volume", 1.0)

    log("[TTS] {} 离线提示: {} (key={} speed={:.1f} vol={:.1f})".format(

        play_type, feature_name, _TTS_WAV_MAP.get(feature_name, "beep"), speed, vol))

    log("[OFFLINE] ⚠ {}".format(msg))

    return msg





def _device_offline_msg(device_id, action_desc="操作"):

    """设备级离线提示: 返回带设备名的保底消息"""

    dev_name = _DEVICE_NAMES.get(device_id, device_id)

    return f"{dev_name}{action_desc}离线，连通测试成功"





# ===== 远程指令执行 =====



# 指令中文名映射 (用于离线提示)

_ACTION_NAMES = {

    "ping": "连通测试",

    "get_status": "状态查询",

    "get_devices": "设备查询",

    "get_sensors": "传感器查询",

    "get_scenes": "场景查询",

    "get_user": "用户查询",

    "get_operations": "操作记录查询",

    "get_chat_history": "对话历史查询",

    "get_alerts": "告警查询",

    "get_cameras": "摄像头查询",

    "get_server_status": "服务状态查询",

    "rag_search": "知识搜索",

    "toggle_device": "设备开关",

    "control_device": "设备控制",

    "add_device": "添加设备",

    "remove_device": "删除设备",

    "activate_scene": "场景激活",

    "activate_scene_by_name": "场景激活",

    "update_user": "用户更新",

    "send_chat": "AI对话",

}





def execute_command(cmd):

    """执行云端下发的指令 (带 finally 保底)"""

    action = cmd.get("action", "")

    msg_id = cmd.get("msgId", 0)

    action_name = _ACTION_NAMES.get(action, action)

    result = {"msgId": msg_id, "success": False, "error": "unknown action"}

    conn = None



    try:

        # ★ 不需要数据库的指令，提前处理

        if action == "ping":

            result = {"msgId": msg_id, "success": True, "data": {"pong": True, "time": datetime.now().isoformat()}}

            return result



        elif action == "get_server_status":

            result = {"msgId": msg_id, "success": True, "data": {

                "host": "192.168.1.81", "port": 8080, "isOnline": True,

                "protocol": "wifi", "version": "v3", "channelVersion": "1.0.0",

                "python": sys.version.split()[0],

                "dbSize": DB_PATH.stat().st_size if DB_PATH.exists() else 0,

                "connectedClients": 1

            }}

            return result



        # 需要数据库的指令

        conn = _db()



        if action == "get_status":

            result = {"msgId": msg_id, "success": True, "data": collect_all()}



        elif action == "get_devices":

            rows = conn.execute("SELECT id,name,type,status,room,icon,primary_value,is_on,mode,battery,updated_at FROM devices").fetchall()

            devices = []

            for r in rows:

                d = {"id": r[0], "name": r[1], "type": r[2], "status": r[3], "room": r[4],

                     "icon": r[5], "primaryValue": r[6], "isOn": bool(r[7]), "updatedAt": r[10]}

                if r[8] is not None: d["mode"] = r[8]

                if r[9] is not None: d["battery"] = r[9]

                devices.append(d)

            result = {"msgId": msg_id, "success": True, "data": devices}



        elif action == "toggle_device":

            device_id = cmd.get("deviceId", "")

            is_on = bool(cmd.get("isOn", False))

            conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, device_id))

            conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",

                        (device_id, "toggle", json.dumps({"isOn": is_on}), "remote"))

            r = conn.execute("SELECT id,name,type,room,primary_value,is_on FROM devices WHERE id=?", (device_id,)).fetchone()

            conn.commit()

            if r:
                # ★ 调用真实硬件
                hw_result = hw_toggle(device_id, is_on)
                hw_ok = hw_result["success"]
                dev_name = _DEVICE_NAMES.get(device_id, r[1])
                if hw_ok:
                    vs_text = f"{dev_name}已{'开启' if is_on else '关闭'}"
                    dev_msg = ""
                else:
                    vs_text = f"{dev_name}调用失败"
                    dev_msg = f"{dev_name}硬件调用失败: {hw_result.get('error', '未知')}"
                tts_speak(vs_text)
                vs_h = hashlib.md5(f"{vs_text}_7".encode()).hexdigest()
                voice_seq = [{"text": vs_text, "audioUrl": f"/api/tts/audio/{vs_h}.mp3"}]
                result = {"msgId": msg_id, "success": True, "data": {
                    "id": r[0], "name": r[1], "type": r[2], "room": r[3],
                    "primaryValue": r[4], "isOn": bool(r[5])
                }, "hardwareOnline": hw_ok, "message": dev_msg, "voiceSequence": voice_seq}

            else:

                result = {"msgId": msg_id, "success": False, "error": "设备不存在"}



        elif action == "control_device":

            device_id = cmd.get("deviceId", "")

            params = cmd.get("params", {})

            act = cmd.get("subAction", "")

            if act in ("set_speed", "set_temp", "set_brightness") and "value" in params:

                conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?", (params["value"], device_id))

            if act == "set_mode" and "mode" in params:

                conn.execute("UPDATE devices SET mode=?, updated_at=datetime('now') WHERE id=?", (params["mode"], device_id))

            conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",

                        (device_id, act, json.dumps(params, ensure_ascii=False), "remote"))

            r = conn.execute("SELECT id,name,type,primary_value,is_on FROM devices WHERE id=?", (device_id,)).fetchone()

            conn.commit()

            if r:
                # ★ 调用真实硬件
                hw_result = hw_control(device_id, act, params)
                hw_ok = hw_result["success"]
                dev_name = _DEVICE_NAMES.get(device_id, r[1])
                act_desc = {"set_temp": "调温", "set_speed": "调速", "set_brightness": "调光", "set_mode": "模式切换"}.get(act, "控制")
                if hw_ok:
                    # 成功: 用动态模板生成语音文本
                    ctrl_key = _DEV_TTS_KEY.get(device_id, device_id) + "_" + act
                    ctrl_text = _TTS_TEXT_MAP.get(ctrl_key, "")
                    if ctrl_key in _TTS_DYNAMIC_TEMPLATES:
                        pv_val = params.get("value", params.get("mode", None))
                        try: ctrl_text = _TTS_DYNAMIC_TEMPLATES[ctrl_key](bool(r[4]), pv_val)
                        except: pass
                    if not ctrl_text:
                        ctrl_text = f"{dev_name}{act_desc}成功"
                    dev_msg = ""
                else:
                    ctrl_text = f"{dev_name}调用失败"
                    dev_msg = f"{dev_name}硬件调用失败: {hw_result.get('error', '未知')}"
                tts_speak(ctrl_text)
                vs_h = hashlib.md5(f"{ctrl_text}_7".encode()).hexdigest()
                voice_seq = [{"text": ctrl_text, "audioUrl": f"/api/tts/audio/{vs_h}.mp3"}]
                result = {"msgId": msg_id, "success": True, "data": {
                    "id": r[0], "name": r[1], "type": r[2], "primaryValue": r[3], "isOn": bool(r[4])
                }, "hardwareOnline": hw_ok, "message": dev_msg, "voiceSequence": voice_seq}

            else:

                result = {"msgId": msg_id, "success": False, "error": "设备不存在"}



        elif action == "activate_scene":

            scene_id = cmd.get("sceneId", "")

            conn.execute("UPDATE scenes SET is_active=0")

            conn.execute("UPDATE scenes SET is_active=1, updated_at=datetime('now') WHERE id=?", (scene_id,))

            name_r = conn.execute("SELECT name FROM scenes WHERE id=?", (scene_id,)).fetchone()

            if not name_r:

                conn.commit()

                result = {"msgId": msg_id, "success": False, "error": "场景不存在"}

            else:

                actions = conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order", (scene_id,)).fetchall()

                count = 0

                affected_devices = []

                for dev_id, is_on, pv in actions:

                    conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))

                    if pv is not None:

                        conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?", (pv, dev_id))

                    conn.execute("INSERT INTO device_operations(device_id,action,params_json,source,scene_id) VALUES(?,?,?,?,?)",

                                (dev_id, "scene_toggle", json.dumps({"isOn": bool(is_on), "primaryValue": pv}, ensure_ascii=False), "remote", scene_id))

                    count += 1

                    affected_devices.append(_DEVICE_NAMES.get(dev_id, dev_id))

                conn.commit()

                # ★ 调用真实硬件执行场景
                hw_actions = [(dev_id, is_on, pv) for dev_id, is_on, pv in actions]
                hw_results = hw_scene_execute(hw_actions)
                hw_fail_count = sum(1 for hr in hw_results if not hr["success"])
                hw_any_ok = any(hr["success"] for hr in hw_results)

                scene_name = _SCENE_NAMES.get(scene_id, name_r[0])
                scene_voice = _TTS_TEXT_MAP.get(scene_id + "_activate", "")

                # 语音反馈: 根据硬件结果
                voice_texts = []
                if hw_fail_count == 0:
                    # 全部成功
                    if scene_voice:
                        voice_texts.append(scene_voice)
                    for dev_id2, dev_is_on2, dev_pv2 in actions:
                        dev_key2 = _DEV_TTS_KEY.get(dev_id2, dev_id2) + "_toggle"
                        dev_text2 = _TTS_TEXT_MAP.get(dev_key2, "")
                        if dev_key2 in _TTS_DYNAMIC_TEMPLATES:
                            try: dev_text2 = _TTS_DYNAMIC_TEMPLATES[dev_key2](dev_is_on2, dev_pv2)
                            except: pass
                        if dev_text2: voice_texts.append(dev_text2)
                    scene_msg = ""
                elif hw_fail_count > 0 and hw_any_ok:
                    # 部分失败
                    if scene_voice:
                        voice_texts.append(f"{scene_voice}，{hw_fail_count}台设备调用失败")
                    else:
                        voice_texts.append(f"{scene_name}模式已激活，{hw_fail_count}台设备调用失败")
                    for dev_id2, dev_is_on2, dev_pv2 in actions:
                        dev_name2 = _DEVICE_NAMES.get(dev_id2, dev_id2)
                        hr2 = next((hr for hr in hw_results if hr["device_id"] == dev_id2), None)
                        if hr2 and hr2["success"]:
                            dev_key2 = _DEV_TTS_KEY.get(dev_id2, dev_id2) + "_toggle"
                            dev_text2 = _TTS_TEXT_MAP.get(dev_key2, "")
                            if dev_key2 in _TTS_DYNAMIC_TEMPLATES:
                                try: dev_text2 = _TTS_DYNAMIC_TEMPLATES[dev_key2](dev_is_on2, dev_pv2)
                                except: pass
                            if dev_text2: voice_texts.append(dev_text2)
                        else:
                            voice_texts.append(f"{dev_name2}调用失败")
                    scene_msg = f"{hw_fail_count}台设备硬件调用失败"
                else:
                    # 全部失败
                    voice_texts = [f"{scene_name}模式调用失败"]
                    scene_msg = f"{scene_name}模式全部设备调用失败"

                # 播报语音
                for vt in voice_texts:
                    tts_speak(vt)

                voice_seq = _build_voice_sequence(voice_texts, 500) if voice_texts else []

                result = {"msgId": msg_id, "success": True, "data": {
                    "sceneName": name_r[0], "affectedCount": count,
                    "affectedDevices": affected_devices
                }, "hardwareOnline": hw_any_ok, "message": scene_msg, "voiceSequence": voice_seq}



        elif action == "get_sensors":

            rows = conn.execute("SELECT id,name,type,sensor_group,room,current_value,unit,is_alert,updated_at FROM sensors").fetchall()

            sensors = []

            for r in rows:

                sensors.append({"id": r[0], "name": r[1], "type": r[2], "group": r[3],

                               "room": r[4], "current": {"value": r[5], "unit": r[6]},

                               "isAlert": bool(r[7]), "updatedAt": r[8]})

            result = {"msgId": msg_id, "success": True, "data": sensors}



        elif action == "get_scenes":

            scenes = []

            for s in conn.execute("SELECT id,name,icon,color,is_active,description FROM scenes").fetchall():

                actions = []

                for a in conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order", (s[0],)).fetchall():

                    act = {"deviceId": a[0], "isOn": bool(a[1])}

                    if a[2] is not None: act["primaryValue"] = a[2]

                    actions.append(act)

                scenes.append({"id": s[0], "name": s[1], "icon": s[2], "color": s[3],

                              "isActive": bool(s[4]), "description": s[5], "actions": actions})

            result = {"msgId": msg_id, "success": True, "data": scenes}



        elif action == "get_operations":

            limit = cmd.get("limit", 50)

            rows = conn.execute("SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

            ops = [{"deviceId": r[0], "action": r[1], "params": r[2], "result": r[3],

                    "source": r[4], "sceneId": r[5], "timestamp": r[6]} for r in rows]

            result = {"msgId": msg_id, "success": True, "data": ops}



        elif action == "get_chat_history":

            limit = cmd.get("limit", 50)

            rows = conn.execute("SELECT user_id,role,content,scene_id,created_at FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

            chats = [{"userId": r[0], "role": r[1], "content": r[2], "sceneId": r[3], "timestamp": r[4]} for r in rows]

            result = {"msgId": msg_id, "success": True, "data": chats}



        elif action == "send_chat":

            content = cmd.get("content", "")

            # 保存用户消息

            conn.execute("INSERT INTO chat_history(user_id,role,content,scene_id) VALUES('u001','user',?,?)", (content, None))

            # RAG 场景匹配

            sys.path.insert(0, str(Path(__file__).resolve().parent))

            from rag.rag_service import SimpleRAG

            from scenes.scene_config import get_scene_id_by_name, SCENE_META

            rag = SimpleRAG()

            scene_match = rag.search_scene(content)

            reply = ""

            scene_id = None

            if scene_match and scene_match.get("scene_id"):

                sid = scene_match["scene_id"]

                # 激活场景

                conn.execute("UPDATE scenes SET is_active=0")

                conn.execute("UPDATE scenes SET is_active=1, updated_at=datetime('now') WHERE id=?", (sid,))

                actions = conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order", (sid,)).fetchall()

                for dev_id, is_on, pv in actions:

                    conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?", (1 if is_on else 0, dev_id))

                    if pv is not None:

                        conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?", (pv, dev_id))

                    conn.execute("INSERT INTO device_operations(device_id,action,params_json,source,scene_id) VALUES(?,?,?,?,?)",

                                (dev_id, "scene_toggle", json.dumps({"isOn": bool(is_on), "primaryValue": pv}), "remote", sid))

                # ★ 调用真实硬件执行场景
                hw_chat_results = hw_scene_execute([(dev_id, is_on, pv) for dev_id, is_on, pv in actions])
                hw_chat_fail = sum(1 for hr in hw_chat_results if not hr["success"])
                hw_chat_ok = any(hr["success"] for hr in hw_chat_results)

                sname = SCENE_META.get(sid, {}).get("name", sid)
                if hw_chat_fail == 0:
                    reply = f"已切换到「{sname}」模式，控制 {len(actions)} 台设备"
                elif hw_chat_ok:
                    reply = f"已切换到「{sname}」模式，{hw_chat_fail}台设备调用失败"
                else:
                    reply = f"「{sname}」模式调用失败"

                scene_id = sid

            else:
                # call gateway /api/chat/send for unified processing
                try:
                    _gw_body = json.dumps({"messages": [{"role": "user", "content": content}]}, ensure_ascii=False).encode()
                    _gw_req = Request("http://127.0.0.1:8080/api/chat/send", data=_gw_body,
                                     headers={"Content-Type": "application/json"}, method="POST")
                    with urlopen(_gw_req, timeout=30) as _gw_r:
                        _gw_resp = json.loads(_gw_r.read().decode())
                    _gw_data = _gw_resp.get("data", _gw_resp)
                    reply = _gw_data.get("reply", "gateway no response")
                    hw_online = _gw_data.get("hardwareOnline", True)
                    _vs_seq = _gw_data.get("voiceSequence", [])
                    scene_id = _gw_data.get("sceneId", None)
                    log(f"[CHAT-GW] gateway ok: {reply[:40]}...")
                except Exception as _e:
                    reply = f"gateway call failed: {_e}"
                    hw_online = False
                    _vs_seq = []
                    log(f"[CHAT-GW] failed: {_e}")
                conn.execute("INSERT INTO chat_history(user_id,role,content,scene_id) VALUES(?,?,?,?)", ("u001","assistant",reply, scene_id))
                conn.commit()
            chat_msg = "" if hw_online else "device call failed"
            result = {"msgId": msg_id, "success": True, "data": {"reply": reply, "sceneId": scene_id, "voiceSequence": _vs_seq},
                     "hardwareOnline": hw_online, "message": chat_msg}



        elif action == "add_device":

            did = cmd.get("id", f"d{int(time.time())%10000}")

            conn.execute("INSERT OR IGNORE INTO devices(id,name,type,room,icon,primary_value,is_on,status) VALUES(?,?,?,?,?,0,0,'online')",

                        (did, cmd.get("name", "新设备"), cmd.get("type", "light"), cmd.get("room", "客厅"), cmd.get("icon", "lightbulb")))

            r = conn.execute("SELECT id,name,type,room FROM devices WHERE id=?", (did,)).fetchone()

            conn.commit()

            if r:

                tts_offline_alert("add_device")

                result = {"msgId": msg_id, "success": True, "data": {"id": r[0], "name": r[1], "type": r[2], "room": r[3]},

                         "hardwareOnline": False, "message": "设备已注册但硬件未接入，连通测试成功"}

            else:

                result = {"msgId": msg_id, "success": False, "error": "添加失败"}



        elif action == "remove_device":

            device_id = cmd.get("deviceId", "")

            r = conn.execute("SELECT id, name FROM devices WHERE id=?", (device_id,)).fetchone()

            if r:

                # 先保存设备名，删除后就查不到了

                dev_display = r[1] or _DEVICE_NAMES.get(device_id, device_id)

                conn.execute("DELETE FROM devices WHERE id=?", (device_id,))

                conn.execute("DELETE FROM scene_actions WHERE device_id=?", (device_id,))

                conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",

                            (device_id, "remove", "{}", "remote"))

                conn.commit()

                dev_msg = f"{dev_display}移除离线，连通测试成功"

                tts_offline_alert(_DEV_TTS_KEY.get(device_id, device_id) + "_remove")

                result = {"msgId": msg_id, "success": True, "data": {"removed": device_id, "removedName": dev_display},

                         "hardwareOnline": False, "message": dev_msg}

            else:

                result = {"msgId": msg_id, "success": False, "error": "设备不存在"}



        elif action == "update_user":

            if "nickname" in cmd: conn.execute("UPDATE users SET nickname=? WHERE id='u001'", (cmd["nickname"],))

            if "homeName" in cmd: conn.execute("UPDATE users SET home_name=? WHERE id='u001'", (cmd["homeName"],))

            if "memberCount" in cmd: conn.execute("UPDATE users SET member_count=? WHERE id='u001'", (cmd["memberCount"],))

            r = conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()

            conn.commit()

            if r:

                result = {"msgId": msg_id, "success": True, "data": {"id": r[0], "nickname": r[1], "homeName": r[2], "memberCount": r[3]}}

            else:

                result = {"msgId": msg_id, "success": False, "error": "用户不存在"}



        elif action == "get_alerts":

            alerts = [

                {"id": "a1", "source": "门口摄像头", "content": "门口有人停留，检测到异常移动",

                 "level": "warning", "isRead": False, "timestamp": int(time.time()*1000)-1380000},

                {"id": "a2", "source": "卧室窗帘", "content": "电量剩余 15%，建议更换电池",

                 "level": "info", "isRead": True, "timestamp": int(time.time()*1000)-7200000},

                {"id": "a3", "source": "客厅湿度", "content": "当前湿度 72%，建议开启除湿",

                 "level": "info", "isRead": True, "timestamp": int(time.time()*1000)-14400000},

            ]

            tts_offline_alert("get_alerts")

            result = {"msgId": msg_id, "success": True, "data": alerts,

                     "hardwareOnline": False, "message": "告警数据为模拟数据，连通测试成功"}



        elif action == "get_cameras":

            cameras = [

                {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online", "isRecording": True, "resolution": "1080P"},

                {"id": "cam_02", "name": "门口摄像头", "room": "室外", "status": "online", "isRecording": False, "resolution": "1080P"},

            ]

            tts_offline_alert("get_cameras")

            result = {"msgId": msg_id, "success": True, "data": cameras,

                     "hardwareOnline": False, "message": "摄像头数据为模拟数据，连通测试成功"}



        elif action == "rag_search":

            query = cmd.get("query", "")

            n = cmd.get("n_results", 5)

            sys.path.insert(0, str(Path(__file__).resolve().parent))

            from rag.rag_service import SimpleRAG

            rag = SimpleRAG()

            results = rag.search(query, n=n)

            result = {"msgId": msg_id, "success": True, "data": results}



        elif action == "get_user":

            r = conn.execute("SELECT id,nickname,home_name,member_count,avatar FROM users WHERE id='u001'").fetchone()

            dc = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]

            if r:

                result = {"msgId": msg_id, "success": True, "data": {

                    "id": r[0], "nickname": r[1], "homeName": r[2],

                    "memberCount": r[3], "avatar": r[4], "deviceCount": dc

                }}

            else:

                result = {"msgId": msg_id, "success": True, "data": {"id": "u001", "deviceCount": dc}}



        elif action == "activate_scene_by_name":

            name = cmd.get("name", "")

            sys.path.insert(0, str(Path(__file__).resolve().parent))

            from scenes.scene_config import get_scene_id_by_name, SCENE_META

            sid = get_scene_id_by_name(name)

            if sid:

                # 复用 activate_scene 逻辑 (它自带 TTS + message)

                cmd2 = dict(cmd)

                cmd2["action"] = "activate_scene"

                cmd2["sceneId"] = sid

                if conn:

                    conn.close()

                    conn = None

                result = execute_command(cmd2)

                # 标记已有 message，防止 finally 重复加 TTS

                return result

            else:

                tts_offline_alert("offline_generic")

                result = {"msgId": msg_id, "success": False, "error": f"未找到场景: {name}",

                         "hardwareOnline": False, "message": f"场景{name}未找到，连通测试成功"}



        else:

            result = {"msgId": msg_id, "success": False, "error": f"未知指令: {action}"}



    except Exception as e:

        # ★ 保底: 指令执行失败 → 离线提示 + 通道连通确认

        offline_msg = tts_offline_alert(action)  # 传英文 action key

        result = {

            "msgId": msg_id,

            "success": False,

            "offline": True,

            "error": str(e),

            "message": offline_msg,

            "channelOk": True  # 通道本身是通的，只是功能离线

        }



    finally:

        # ★ 保底: 确保数据库连接关闭

        if conn:

            try:

                conn.close()

            except Exception:

                pass

        # ★★★ 统一语音回馈: 每个指令都保证有 TTS 蜂鸣 + message

        if isinstance(result, dict) and "message" not in result:

            # 查询类指令: 数据在线但硬件未接入

            tts_offline_alert(action)  # 传英文 action key, 匹配 _TTS_WAV_MAP

            result["hardwareOnline"] = False

            result["message"] = f"{action_name}成功，硬件未接入，连通测试成功"



    return result





# ===== WebSocket 连接管理 =====



def _parse_ws_url(url):

    """解析 ws:// 或 wss:// URL"""

    if url.startswith("wss://"):

        host_port = url[6:].split("/")[0]

        path = "/" + url[6:].split("/", 1)[1] if "/" in url[6:] else "/"

        host = host_port.split(":")[0]

        port = int(host_port.split(":")[1]) if ":" in host_port else 443

        return host, port, path, True

    elif url.startswith("ws://"):

        host_port = url[5:].split("/")[0]

        path = "/" + url[5:].split("/", 1)[1] if "/" in url[5:] else "/"

        host = host_port.split(":")[0]

        port = int(host_port.split(":")[1]) if ":" in host_port else 80

        return host, port, path, False

    else:

        return "yuanzhe.tech", 80, "/ws/smart-home", False





def ws_connect():

    """建立 WebSocket 连接"""

    host, port, path, use_ssl = _parse_ws_url(WS_URL)

    log(f"[WS] 连接 {WS_URL} (host={host} port={port} ssl={use_ssl})")



    sock = _ws_handshake(host, port, path, WS_TOKEN)



    if use_ssl:

        ctx = ssl.create_default_context()

        ctx.check_hostname = False

        ctx.verify_mode = ssl.CERT_NONE

        sock = ctx.wrap_socket(sock, server_hostname=host)



    sock.settimeout(60)  # 读超时

    return sock





def ws_send_json(sock, data):

    """发送 JSON 消息"""

    payload = json.dumps(data, ensure_ascii=False)

    _ws_send(sock, payload, opcode=0x1)





def ws_recv_json(sock):

    """接收 JSON 消息，返回 dict 或 None"""

    while True:

        frame = _ws_recv(sock)

        if frame is None:

            return None

        opcode, payload = frame



        if opcode == 0x1:  # 文本

            try:

                return json.loads(payload.decode("utf-8"))

            except json.JSONDecodeError:

                log(f"[WS] 非JSON消息: {payload[:100]}")

                return None

        elif opcode == 0x8:  # 关闭

            log("[WS] 收到关闭帧")

            return None

        elif opcode == 0x9:  # Ping

            _ws_send(sock, payload, opcode=0xA)  # Pong

        elif opcode == 0xA:  # Pong

            pass  # 心跳响应，忽略

        else:

            pass  # 忽略其他帧





# ===== 主连接循环 =====



def channel_loop():

    """WebSocket 长连接主循环"""

    global _ws, _connected, _running



    reconnect_delay = RECONNECT_BASE



    while _running:

        try:

            # 建立连接

            sock = ws_connect()

            _ws = sock

            _connected = True

            reconnect_delay = RECONNECT_BASE  # 重置退避

            log(f"[WS] ✓ 已连接 {WS_URL}")



            # 发送初始注册消息

            register_msg = {

                "type": "register",

                "deviceId": "harmony_a9",

                "version": "1.0.0",

                "timestamp": datetime.now().isoformat(),

                "capabilities": [

                    "ping", "get_status", "get_devices", "get_sensors", "get_scenes",

                    "get_user", "get_operations", "get_chat_history", "get_alerts",

                    "get_cameras", "get_server_status",

                    "toggle_device", "control_device", "add_device", "remove_device",

                    "activate_scene", "activate_scene_by_name", "update_user",

                    "send_chat", "rag_search"

                ],

                "info": {

                    "host": "192.168.1.81",

                    "port": 8080,

                    "deviceCount": 16,

                    "sensorCount": 9,

                    "sceneCount": 5,

                    "python": sys.version.split()[0]

                }

            }

            ws_send_json(sock, register_msg)

            log("[WS] 注册消息已发送")



            # 发送轻量初始状态（不含操作/聊天历史，对方可按需请求）

            init_data = collect_all()

            init_data["operations"] = init_data["operations"][:20]  # 只发最近20条

            init_data["chatHistory"] = init_data["chatHistory"][:10]  # 只发最近10条

            snapshot = {

                "type": "snapshot",

                "deviceId": "harmony_a9",

                "timestamp": datetime.now().isoformat(),

                "timestampMs": int(time.time() * 1000),

                "data": init_data

            }

            payload_str = json.dumps(snapshot, ensure_ascii=False)

            log(f"[WS] 初始快照大小: {len(payload_str.encode('utf-8'))//1024}KB")

            ws_send_json(sock, snapshot)

            log("[WS] 初始快照已发送")



            # 消息循环

            last_heartbeat = time.time()

            last_snapshot = time.time()



            while _running and _connected:

                # 接收消息 (长超时，对方不一定每次都回消息)

                try:

                    sock.settimeout(30)

                    msg = ws_recv_json(sock)



                    if msg is None:

                        # 区分: 是读超时(对方没发消息)还是真断了

                        # 尝试发一个心跳探测连接是否还活着

                        try:

                            _ws_send(sock, json.dumps({"type": "heartbeat", "timestamp": datetime.now().isoformat()}), opcode=0x1)

                            # 发成功说明连接还活着，继续

                            last_heartbeat = time.time()

                            continue

                        except OSError:

                            log("[WS] ✗ 心跳探测失败，连接已断开")

                            break



                    # 处理云端指令

                    msg_type = msg.get("type", "")

                    if msg_type == "command":

                        log(f"[WS] ← 指令: {msg.get('action', '?')} (msgId={msg.get('msgId', '?')})")

                        result = execute_command(msg)

                        ws_send_json(sock, result)

                        log(f"[WS] → 响应: {result.get('success', False)}")



                    elif msg_type == "ping":

                        ws_send_json(sock, {"type": "pong", "timestamp": datetime.now().isoformat()})



                    elif msg_type == "get_snapshot":

                        snap = {

                            "type": "snapshot",

                            "deviceId": "harmony_a9",

                            "timestamp": datetime.now().isoformat(),

                            "timestampMs": int(time.time() * 1000),

                            "data": collect_all()

                        }

                        ws_send_json(sock, snap)

                        log("[WS] → 快照(按需)")



                    else:

                        log(f"[WS] ← 未知消息: {msg_type}")



                except socket.timeout:

                    pass  # 正常超时，继续心跳检查

                except OSError as e:

                    log(f"[WS] ✗ 连接错误: {e}")

                    break



                # 心跳

                now = time.time()

                if now - last_heartbeat >= HEARTBEAT_INTERVAL:

                    try:

                        _ws_send(sock, json.dumps({"type": "heartbeat", "timestamp": datetime.now().isoformat()}), opcode=0x1)

                        last_heartbeat = now

                    except Exception:

                        break



                # 定时快照 (每5分钟)

                if now - last_snapshot >= 300:

                    try:

                        snap = {

                            "type": "snapshot",

                            "deviceId": "harmony_a9",

                            "timestamp": datetime.now().isoformat(),

                            "timestampMs": int(time.time() * 1000),

                            "data": collect_all()

                        }

                        ws_send_json(sock, snap)

                        last_snapshot = now

                        log("[WS] → 定时快照")

                    except Exception:

                        break



        except Exception as e:

            log(f"[WS] ✗ 连接失败: {e}")



        finally:

            _connected = False

            _ws = None

            try:

                if sock:

                    sock.close()

            except Exception:

                pass



        # 重连退避

        if not _running:

            break

        log(f"[WS] ↻ {reconnect_delay}s 后重连...")

        time.sleep(reconnect_delay)

        reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX)





# ===== 本地调试 API =====



class LocalAPI(BaseHTTPRequestHandler):

    """本地调试 API，查看通道状态"""



    def _j(self, c, d):

        b = json.dumps(d, ensure_ascii=False).encode("utf-8")

        self.send_response(c)

        self.send_header("Content-Type", "application/json;charset=utf-8")

        self.send_header("Access-Control-Allow-Origin", "*")

        self.send_header("Content-Length", str(len(b)))

        self.end_headers()

        self.wfile.write(b)



    def log_message(self, *a):

        pass



    def do_GET(self):

        p = self.path.split("?")[0]

        if p == "/tts/config":

            # GET /tts/config → 获取 TTS 配置

            self._j(200, {

                "speed": _TTS_CONFIG.get("speed", 1.0),

                "volume": _TTS_CONFIG.get("volume", 1.0),

                "enabled": _TTS_CONFIG.get("enabled", True),

                "backend": _TTS_CONFIG.get("backend", "wav"),

                "availableBackends": ["online", "wav", "beep", "none"],

                "speedRange": {"min": 0.5, "max": 3.0, "step": 0.1},

                "volumeRange": {"min": 0.0, "max": 1.0, "step": 0.05},

                "wavCount": len(list(_TTS_WAV_DIR.glob("*.wav"))) if _TTS_WAV_DIR.exists() else 0

            })

        elif p == "/ai/config":

            # GET /ai/config → 获取 AI 对话后端配置

            provider = _AI_CONFIG.get("provider", "deepseek")

            models = {}

            for k, v in _AI_CONFIG.get("models", {}).items():

                models[k] = {

                    "url": v.get("url", ""),

                    "model": v.get("model", ""),

                    "maxTokens": v.get("maxTokens", 200),

                    "temperature": v.get("temperature", 0.3),

                    "hasKey": bool(v.get("key", "")),

                }

            self._j(200, {"provider": provider, "models": models, "availableProviders": list(models.keys())})

        elif p == "/tts/list":

            # GET /tts/list → 列出所有可用语音

            wavs = []

            if _TTS_WAV_DIR.exists():

                for f in sorted(_TTS_WAV_DIR.glob("*.wav")):

                    wavs.append({"key": f.stem, "file": f.name, "size": f.stat().st_size})

            self._j(200, {"total": len(wavs), "files": wavs, "map": _TTS_WAV_MAP})

        elif p == "/channel/status":

            self._j(200, {

                "connected": _connected,

                "wsUrl": WS_URL,

                "deviceId": "harmony_a9",

                "uptime": int(time.time()),

                "lastLog": _read_last_log()

            })

        elif p == "/channel/test":

            # 测试: 通过通道发送一个 ping

            if _connected and _ws:

                try:

                    ws_send_json(_ws, {"type": "ping", "msgId": next_msg_id(), "timestamp": datetime.now().isoformat()})

                    self._j(200, {"ok": True, "message": "ping sent"})

                except Exception as e:

                    self._j(500, {"ok": False, "error": str(e)})

            else:

                self._j(503, {"ok": False, "error": "not connected"})

        elif p == "/tts/text_map":

            # GET /tts/text_map → 获取所有语音文本映射

            self._j(200, {

                "textMap": _TTS_TEXT_MAP,

                "dynamicTemplates": list(_TTS_DYNAMIC_TEMPLATES.keys()),

                "total": len(_TTS_TEXT_MAP),

                "dynamicTotal": len(_TTS_DYNAMIC_TEMPLATES)

            })

        elif p == "/tts/cache":

            # GET /tts/cache → 查看在线 TTS 缓存

            cache_files = []

            if _TTS_CACHE_DIR.exists():

                for f in sorted(_TTS_CACHE_DIR.glob("*.mp3")):

                    cache_files.append({"file": f.name, "size": f.stat().st_size})

            self._j(200, {"total": len(cache_files), "files": cache_files, "cacheDir": str(_TTS_CACHE_DIR)})

        elif p.startswith("/tts/audio/"):

            # GET /tts/audio/<filename> → 获取缓存的 MP3 音频文件

            fname = p.split("/")[-1]

            # 安全检查: 只允许 .mp3 文件名

            if not fname.endswith(".mp3") or "/" in fname or "\\" in fname:

                self._j(400, {"error": "invalid filename"})

                return

            fpath = _TTS_CACHE_DIR / fname

            if fpath.exists():

                try:

                    with open(fpath, "rb") as af:

                        mp3_data = af.read()

                    self.send_response(200)

                    self.send_header("Content-Type", "audio/mpeg")

                    self.send_header("Content-Length", str(len(mp3_data)))

                    self.send_header("Access-Control-Allow-Origin", "*")

                    self.send_header("Cache-Control", "public, max-age=86400")

                    self.end_headers()

                    self.wfile.write(mp3_data)

                except Exception as e:

                    self._j(500, {"error": str(e)})

            else:

                self._j(404, {"error": "audio not found"})

        else:

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

                if b in ("online", "wav", "beep", "none"):

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

        elif p == "/ai/config":

            # POST /ai/config → 更新 AI 对话后端配置

            if "provider" in body:

                p_val = str(body["provider"])

                if p_val in _AI_CONFIG.get("models", {}):

                    _AI_CONFIG["provider"] = p_val

            if "modelConfig" in body:

                mc = body["modelConfig"]

                target = mc.get("target", _AI_CONFIG.get("provider", "deepseek"))

                if target in _AI_CONFIG.get("models", {}):

                    cfg = _AI_CONFIG["models"][target]

                    if "url" in mc: cfg["url"] = str(mc["url"])

                    if "key" in mc: cfg["key"] = str(mc["key"])

                    if "model" in mc: cfg["model"] = str(mc["model"])

                    if "maxTokens" in mc: cfg["maxTokens"] = int(mc["maxTokens"])

                    if "temperature" in mc: cfg["temperature"] = float(mc["temperature"])

            log("[AI] 配置已更新: provider={}".format(_AI_CONFIG.get("provider")))

            self._j(200, {"ok": True, "provider": _AI_CONFIG["provider"],

                         "currentModel": _AI_CONFIG["models"].get(_AI_CONFIG["provider"], {}).get("model", "")})

        elif p == "/ai/test":

            # POST /ai/test → 测试当前 AI 后端

            test_content = body.get("content", "你好")

            provider = _AI_CONFIG.get("provider", "deepseek")

            prov_cfg = _AI_CONFIG.get("models", {}).get(provider, {})

            ai_url = prov_cfg.get("url", "")

            ai_key = prov_cfg.get("key", "")

            ai_model = prov_cfg.get("model", "")

            if ai_url and ai_key:

                try:

                    test_body = json.dumps({

                        "model": ai_model,

                        "messages": [{"role": "user", "content": test_content}],

                        "temperature": prov_cfg.get("temperature", 0.3),

                        "max_tokens": 50

                    }, ensure_ascii=False).encode()

                    req = Request(ai_url, data=test_body,

                                 headers={"Authorization": "Bearer " + ai_key, "Content-Type": "application/json"})

                    with urlopen(req, timeout=15) as r:

                        resp = json.loads(r.read().decode())

                        reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

                    self._j(200, {"ok": True, "provider": provider, "model": ai_model, "reply": reply[:200]})

                except Exception as e:

                    self._j(500, {"ok": False, "provider": provider, "error": str(e)[:200]})

            else:

                self._j(400, {"ok": False, "error": "AI backend not configured"})

        elif p == "/tts/test":

            # POST /tts/test → 测试播放指定语音

            key = body.get("key", "ping")

            text = body.get("text", "")  # 支持自定义文本

            if text:

                # 自定义文本在线合成

                played = tts_speak(text)

                self._j(200, {"ok": True, "played": "custom_text", "text": text, "success": played, "config": {

                    "speed": _TTS_CONFIG["speed"],

                    "volume": _TTS_CONFIG["volume"],

                    "enabled": _TTS_CONFIG["enabled"],

                    "backend": _TTS_CONFIG["backend"]

                }})

            else:

                tts_offline_alert(key)

                self._j(200, {"ok": True, "played": key, "config": {

                    "speed": _TTS_CONFIG["speed"],

                    "volume": _TTS_CONFIG["volume"],

                    "enabled": _TTS_CONFIG["enabled"],

                    "backend": _TTS_CONFIG["backend"]

                }})

        elif p == "/tts/speak":

            # POST /tts/speak → 直接文本转语音播报

            text = body.get("text", "")

            speed = body.get("speed", 5)

            if not text:

                self._j(400, {"ok": False, "error": "text is required"})

            else:

                played = tts_speak(text, speed=speed)

                self._j(200, {"ok": True, "text": text, "speed": speed, "played": played, "backend": _TTS_CONFIG["backend"]})

        else:

            self._j(404, {"error": "nf"})





def _read_last_log():

    try:

        with open(LOG_PATH, "r", encoding="utf-8") as f:

            lines = f.readlines()

            return lines[-1].strip() if lines else ""

    except Exception:

        return ""





def start_local_api():

    """启动本地调试 API"""

    try:

        srv = ThreadingHTTPServer(("0.0.0.0", LOCAL_API_PORT), LocalAPI)

        t = threading.Thread(target=srv.serve_forever, daemon=True)

        t.start()

        log(f"[API] 本地调试 API :{LOCAL_API_PORT}")

    except Exception as e:

        log(f"[API] 调试 API 启动失败: {e}")





# ===== 启动 =====



def start_channel():

    """启动通道服务 (后台线程)"""

    start_local_api()

    t = threading.Thread(target=channel_loop, daemon=True)

    t.start()

    return t





if __name__ == "__main__":

    log("=" * 50)

    log("网络通道服务启动")

    log(f"目标: {WS_URL}")

    log(f"心跳: {HEARTBEAT_INTERVAL}s")

    log(f"认证: {'Bearer ***' if WS_TOKEN else '无'}")

    log("=" * 50)



    start_local_api()

    try:

        channel_loop()

    except KeyboardInterrupt:

        _running = False

        log("通道服务已停止")

