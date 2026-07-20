#!/usr/bin/env python3
"""
智慧家居 HTTP 网关 v3 · 纯标准库实现 + 真实硬件控制
在 /data/A9/ 设备上运行，前端 D:/Harmon 直接对接

替代 smart_home_gateway_v2.py，新增:
  - 数据库持久化(SQLite 8表)
  - RAG知识库搜索
  - 场景联动对话
  - 操作记录存储
  - 传感器历史
  - 用户信息管理
  - 真实硬件控制(通过 central_controller.py)
"""
from __future__ import annotations
import json, os, re, socket, sqlite3, subprocess, threading, time, zlib, sys, ssl, hashlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

HOST = "0.0.0.0"; PORT = 8080
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "control" / "data" / "smart_home.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "db" / "schema.sql"
LOG_PATH = ROOT / "gateway_v3.log"
REGISTRY_PATH = ROOT / "device_registry.json"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# ===== AI 对话后端配置 =====
_AI_CONFIG = {
    "provider": "astron",
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
    },
}

# 导入场景和 RAG
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenes.scene_config import SCENE_ACTIONS, SCENE_META, SCENE_ALIASES, get_scene_id_by_name, get_scene_summary
from rag.rag_service import SimpleRAG

_rag = SimpleRAG()

# 硬件控制桥接
try:
    from hardware_bridge import hw_toggle, hw_control, hw_sensor_read, hw_scene_execute, _DEVICE_NAMES as _HW_DEV_NAMES
    _DEVICE_NAMES = _HW_DEV_NAMES
    _HW_OK = True
    log_hw = lambda m: None  # will be replaced after log() is defined
except ImportError:
    _HW_OK = False
    hw_toggle = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_control = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_sensor_read = lambda *a, **kw: {"success": False, "data": {}, "error": "硬件模块未加载"}
    hw_scene_execute = lambda *a, **kw: []
    _HW_DEV_NAMES = {}

# 设备注册表
REGISTRY = {
    "door_main": {"name":"入户门禁","mac":"","last_ip":"","port":8000,"offline":True},
    "temp_humidity": {"name":"温湿度DHT11","mac":"94:c9:60:e6:8b:70","last_ip":"192.168.1.62","port":8000},
    "dev_board": {"name":"开发板","mac":"f0:a8:82:21:08:84","last_ip":"192.168.1.81","port":8080},
}
LIVE = {"temp":24.6,"humidity":52.0,"last_update":0}

CAMS = [
    {"id":"cam_01","name":"客厅摄像头","room":"客厅","status":"online","isRecording":True,"resolution":"1080P","previewColor":"#1D7F68"},
    {"id":"cam_02","name":"门口摄像头","room":"室外","status":"online","isRecording":False,"resolution":"1080P","previewColor":"#7A6DE8"},
]
ALERTS = [
    {"id":"a1","source":"门口摄像头","content":"门口有人停留，检测到异常移动","level":"warning","isRead":False,"timestamp":int(time.time()*1000)-1380000},
    {"id":"a2","source":"卧室窗帘","content":"电量剩余 15%，建议更换电池","level":"info","isRead":True,"timestamp":int(time.time()*1000)-7200000},
    {"id":"a3","source":"客厅湿度","content":"当前湿度 72%，建议开启除湿","level":"info","isRead":True,"timestamp":int(time.time()*1000)-14400000},
]

def log(m):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        with open(LOG_PATH,"a",encoding="utf-8") as f: f.write(line+"\n")
    except: pass

def now_ms(): return int(time.time()*1000)

# ===== TTS 语音 =====
def _tts_speak(text):
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
    _th.Thread(target=_speak, daemon=True).start()

# ===== MAC→IP 发现 =====
def find_ip_by_mac(mac):
    try:
        with open("/proc/net/arp") as f:
            for line in f:
                p=line.split()
                if len(p)>=4 and p[3].lower()==mac.lower(): return p[0]
    except: pass
    return None

def _reachable(ip,port,timeout=1.0):
    try:
        s=socket.create_connection((ip,port),timeout=timeout); s.close(); return True
    except: return False

def get_device_ip(key):
    dev=REGISTRY.get(key)
    if not dev: return None
    if dev["last_ip"] and _reachable(dev["last_ip"],dev["port"]): return dev["last_ip"]
    nip=find_ip_by_mac(dev["mac"])
    if nip and _reachable(nip,dev["port"]):
        dev["last_ip"]=nip; _save_reg(); return nip
    return None

def refresh_arp():
    def _sw():
        for i in range(1,255):
            try:
                s=socket.socket(); s.settimeout(0.05); s.connect_ex(("192.168.1."+str(i),80)); s.close()
            except: pass
    threading.Thread(target=_sw,daemon=True).start()

def _save_reg():
    try:
        with open(REGISTRY_PATH,"w",encoding="utf-8") as f: json.dump(REGISTRY,f,indent=2,ensure_ascii=False)
    except: pass

# ===== BearPi =====
HDR=bytes([0xAA,0x55]); TAIL=bytes([0x55,0xAA]); PKT_SZ=32
def _bearpi_pkt(cmd,room,val):
    c=bytearray(24); c[0]=cmd; c[1]=room; c[2]=val
    crc=zlib.crc32(bytes(c))&0xFFFFFFFF
    return HDR+crc.to_bytes(4,"little")+bytes(c)+TAIL

def bearpi_brightness(room,value):
    host=REGISTRY.get("dev_board",{}).get("last_ip","192.168.1.81")
    pkt=_bearpi_pkt(1,room,value)
    try:
        with socket.create_connection((host,8000),timeout=5) as s: s.sendall(pkt); resp=s.recv(PKT_SZ)
        log(f"[BEARPI] brightness room={room} value={value}")
        return {"success":True,"host":host,"room":room,"value":value}
    except Exception as e: return {"success":False,"error":str(e)}

# ===== 传感器轮询 (真实硬件) =====
_SENSOR_CACHE = {}  # sensor_id -> {"value": ..., "unit": ..., "ts": float}
_SENSOR_LOCK = threading.Lock()

def _update_sensor_cache(sensor_id, value, unit=""):
    with _SENSOR_LOCK:
        _SENSOR_CACHE[sensor_id] = {"value": value, "unit": unit, "ts": time.time()}

def sensor_poll_thread():
    """后台线程: 每30秒从真实硬件读取传感器数据"""
    while True:
        try:
            # 温湿度 (客厅)
            r = hw_sensor_read("temp_01")
            if r["success"] and "temp" in r.get("data", {}):
                _update_sensor_cache("temp_01", r["data"]["temp"], "°C")
            r2 = hw_sensor_read("humid_01")
            if r2["success"] and "humidity" in r2.get("data", {}):
                _update_sensor_cache("humid_01", r2["data"]["humidity"], "%RH")
            # 厨房烟雾/热敏
            r3 = hw_sensor_read("smoke_01")
            if r3["success"]:
                d = r3.get("data", {})
                if "smoke_alarm" in d:
                    _update_sensor_cache("smoke_01", d["smoke_alarm"], "报警")
            r4 = hw_sensor_read("heat_01")
            if r4["success"]:
                d = r4.get("data", {})
                if "thermal_mv" in d:
                    _update_sensor_cache("heat_01", d["thermal_mv"], "mV")
        except Exception as e:
            log(f"[SENSOR-POLL] {e}")
        time.sleep(30)

# ===== 数据库 =====
def db_init():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(str(DB_PATH))
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text("utf-8"))
    cur=conn.cursor()
    cur.execute("SELECT COUNT(*) FROM devices")
    if cur.fetchone()[0]==0: _seed_data(conn)
    conn.commit(); conn.close()

def _seed_data(conn):
    devices=[
        ("ac_01","客厅空调","ac","active","客厅","air_fill",24,1,"制冷",None,"wifi"),
        ("fan_01","客厅吊扇","fan","online","客厅","fan_fill_1",2,1,None,92,"wifi"),
        ("door_01","客厅大门","door","online","客厅","lock",0,0,None,88,"wifi"),
        ("alarm_01","蜂鸣警报","alarm","online","客厅","bell_fill",0,0,None,None,"wifi"),
        ("light_01","客厅主灯","light","online","客厅","lightbulb",80,1,None,None,"wifi"),
        ("light_05","客厅氛围灯","light","online","客厅","lightbulb",45,0,None,None,"wifi"),
        ("camera_01","客厅摄像头","camera","online","客厅","camera_fill",0,1,None,None,"wifi"),
        ("light_02","厨房灯","light","online","厨房","lightbulb",70,1,None,None,"wifi"),
        ("exhaust_01","抽风机","fan","online","厨房","fan_fill_1",1,0,None,None,"wifi"),
        ("curtain_01","智能窗帘","curtain","online","卧室","lock_open_fill",100,1,None,95,"wifi"),
        ("light_03","卧室灯","light","online","卧室","lightbulb",50,0,None,None,"wifi"),
        ("fan_02","换气扇","fan","online","卫生间","fan_fill_1",1,0,None,None,"wifi"),
        ("light_04","卫生间灯","light","online","卫生间","lightbulb",60,0,None,None,"wifi"),
        ("nfc_01","NFC门禁","nfc","online","室外","lock",0,0,None,None,"wifi"),
        ("voice_01","语音中控","voice","online","全局","mic_fill",0,1,None,None,"wifi"),
        ("radar_01","毫米波雷达","radar","active","全局","wifi",0,1,None,None,"wifi"),
    ]
    conn.executemany("INSERT OR IGNORE INTO devices VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",devices)
    sensors=[
        ("temp_01","客厅温度","temperature","环境监测","客厅","thermometer",24.5,"°C",18,28,"wifi",0),
        ("humid_01","客厅湿度","humidity","环境监测","客厅","drop",58,"%RH",40,70,"wifi",0),
        ("light_s_01","客厅光照","illuminance","环境监测","客厅","sun_max",320,"lx",None,None,"wifi",0),
        ("air_01","空气质量","air_quality","环境监测","客厅","wind",42,"AQI",None,100,"wifi",0),
        ("pir_01","人体感应","pir","安防","客厅","figure_arms_open",1,"有人",None,1,"wifi",0),
        ("smoke_01","烟雾检测","smoke","安防","厨房","flame_fill",0,"正常",None,1,"starflash",0),
        ("heat_01","热敏火灾","heat","安防","厨房","flame_fill",36.2,"°C",None,60,"starflash",0),
        ("door_s_01","门窗感应","door_window","安防","室外","lock",0,"关闭",None,None,"starflash",0),
        ("power_01","总功率","power","能耗","全局","bolt_fill",1.2,"kW",None,None,"wifi",0),
    ]
    conn.executemany("INSERT OR IGNORE INTO sensors VALUES(?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",sensors)
    scenes_data=[("s1","回家","house_fill","#22D3EE",1,"回家模式"),("s2","离家","figure_walk","#F97316",0,"离家模式"),("s3","睡眠","moon_fill","#818CF8",0,"睡眠模式"),("s4","观影","film","#F472B6",0,"观影模式"),("s5","用餐","fork_knife","#34D399",0,"用餐模式")]
    conn.executemany("INSERT OR IGNORE INTO scenes VALUES(?,?,?,?,?,?,datetime('now'),datetime('now'))",scenes_data)
    for sid,actions in SCENE_ACTIONS.items():
        for idx,(dev_id,is_on,pv) in enumerate(actions):
            conn.execute("INSERT OR IGNORE INTO scene_actions(scene_id,device_id,is_on,primary_value,sort_order) VALUES(?,?,?,?,?)",(sid,dev_id,1 if is_on else 0,pv,idx))
    conn.execute("INSERT OR IGNORE INTO users VALUES('u001','用户','我的家',3,'',datetime('now'),datetime('now'))")

def _db(): return sqlite3.connect(str(DB_PATH))

# ===== DeepSeek =====
def chat(msgs):
    provider=_AI_CONFIG.get("provider","deepseek")
    prov_cfg=_AI_CONFIG.get("models",{}).get(provider,{})
    ai_url=prov_cfg.get("url",""); ai_key=prov_cfg.get("key",""); ai_model=prov_cfg.get("model","deepseek-chat")
    ai_max_tokens=prov_cfg.get("maxTokens",200); ai_temp=prov_cfg.get("temperature",0.3)
    if not ai_url or not ai_key: return f"（未配置AI: {provider}）"
    last_msg=msgs[-1].get("content","") if msgs else ""
    rag_ctx=_rag.get_context(last_msg)
    sys_msg="你是智慧家居助手，简洁回答(100字内)。"
    if rag_ctx: sys_msg+=f"\n当前相关上下文: {rag_ctx}"
    body={"model":ai_model,"messages":[{"role":"system","content":sys_msg}]+msgs,"temperature":ai_temp,"max_tokens":ai_max_tokens}
    req=Request(ai_url,data=json.dumps(body,ensure_ascii=False).encode("utf-8"),headers={"Authorization":f"Bearer {ai_key}","Content-Type":"application/json"},method="POST")
    try:
        _ssl_ctx=ssl.create_default_context(cafile="/data/A9/certs/cacert.pem")
        with urlopen(req,timeout=30,context=_ssl_ctx) as r:
            resp=json.loads(r.read().decode("utf-8"))
            reply=resp.get("choices",[{}])[0].get("message",{}).get("content","")
            if not reply: reply=json.dumps(resp,ensure_ascii=False)[:200]
            return reply
    except Exception as e: log(f"[CHAT] {e}"); return f"（AI({provider})暂时不可用: {e}）"

# ===== voiceSequence 辅助 =====
def _vs_entry(text):
    h = hashlib.md5(f"{text}_7".encode()).hexdigest()
    return {"text": text, "audioUrl": f"/api/tts/audio/{h}.mp3"}

# ===== HTTP =====
class H(BaseHTTPRequestHandler):
    def _j(self,c,d):
        b=json.dumps(d,ensure_ascii=False).encode("utf-8")
        self.send_response(c); self.send_header("Content-Type","application/json;charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers(); self.wfile.write(b)
    def _b(self):
        n=int(self.headers.get("Content-Length",0))
        if not n: return {}
        try: return json.loads(self.rfile.read(n).decode("utf-8"))
        except: return {}
    def do_OPTIONS(self): self._j(200,{"ok":True})
    def log_message(self,*a): log(f"{self.command} {self.path}")
    def do_GET(self):
        p=self.path.split("?")[0]
        try:
            if p=="/health": self._j(200,{"ok":True,"v":3,"hardware":_HW_OK})
            elif p=="/api/devices": self._j(200,self._get_devices())
            elif p=="/api/sensors": self._j(200,self._get_sensors())
            elif p=="/api/cameras": self._j(200,CAMS)
            elif p=="/api/alerts": self._j(200,ALERTS)
            elif p=="/api/scenes": self._j(200,self._get_scenes())
            elif p=="/api/user/profile": self._j(200,self._get_user())
            elif p=="/api/server/status": self._j(200,{"host":"192.168.1.81","port":PORT,"isOnline":True,"protocol":"wifi","latency":5,"cpuUsage":25,"memUsage":40,"storageUsage":35,"version":"v3","hardware":_HW_OK})
            elif p=="/api/operations":
                qs=self.path.split("?",1)
                did=None; days=7
                if len(qs)>1:
                    for kv in qs[1].split("&"):
                        k,v=kv.split("=",1) if "=" in kv else (kv,"")
                        if k=="device_id": did=v
                        if k=="days": days=int(v)
                self._j(200,self._get_operations(did,days))
            elif p=="/api/rag/stats": self._j(200,_rag.get_stats())
            elif p=="/api/tts/config":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/config", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"speed":1.0,"volume":1.0,"enabled":True,"backend":"wav","error":str(_e)})
            elif p=="/api/ai/config":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/ai/config", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"provider":"iflytek","models":{},"error":str(_e)})
            elif p=="/api/tts/list":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/list", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"total":0,"files":[],"error":str(_e)})
            elif p=="/api/tts/text_map":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/text_map", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"textMap":{},"error":str(_e)})
            elif p=="/api/tts/cache":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/cache", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"total":0,"files":[],"error":str(_e)})
            elif p.startswith("/api/tts/audio/"):
                try:
                    import urllib.request as _ureq
                    fname = p.split("/")[-1]
                    _req = _ureq.Request(f"http://127.0.0.1:8081/tts/audio/{fname}")
                    with _ureq.urlopen(_req, timeout=5) as _ur:
                        mp3_data = _ur.read()
                        ct = _ur.headers.get("Content-Type", "audio/mpeg")
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(mp3_data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(mp3_data)
                except Exception as _e:
                    self._j(404, {"error": str(_e)})
            elif p=="/api/hardware/status":
                self._j(200,{"available":_HW_OK,"message":"硬件控制已启用" if _HW_OK else "硬件控制未加载"})
            else: self._j(404,{"error":"nf"})
        except Exception as e: self._j(500,{"error":str(e)})

    def do_POST(self):
        p=self.path.split("?")[0]; body=self._b()
        try:
            if p=="/api/chat/send": self._j(200,self._chat(body)); return
            if p=="/api/bearpi/command": self._j(200,self._bearpi(body)); return
            m=re.match(r"^/api/scenes/([\w_]+)/activate$",p)
            if m: self._j(200,self._activate_scene(m.group(1))); return
            m=re.match(r"^/api/devices/([\w_]+)/control$",p)
            if m: self._j(200,self._control_device(m.group(1),body)); return
            m=re.match(r"^/api/devices/([\w_]+)/toggle$",p)
            if m: self._j(200,self._toggle_device(m.group(1),body)); return
            if p=="/api/devices": self._j(200,self._add_device(body)); return
            if p=="/api/rag/search": self._j(200,{"results":_rag.search(body.get("query",""),n=body.get("n_results",5))}); return
            if p=="/api/ai/config":
                try:
                    import urllib.request as _ureq
                    _bd = json.dumps(body, ensure_ascii=False).encode()
                    _req = _ureq.Request("http://127.0.0.1:8081/ai/config", data=_bd, headers={"Content-Type":"application/json"})
                    with _ureq.urlopen(_req, timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(500, {"ok":False,"error":str(_e)})
            if p=="/api/ai/test":
                try:
                    import urllib.request as _ureq
                    _bd = json.dumps(body, ensure_ascii=False).encode()
                    _req = _ureq.Request("http://127.0.0.1:8081/ai/test", data=_bd, headers={"Content-Type":"application/json"})
                    with _ureq.urlopen(_req, timeout=15) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(500, {"ok":False,"error":str(_e)})
            if p=="/api/tts/config":
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
                    with _ureq.urlopen(_req, timeout=30) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(500, {"ok":False,"error":str(_e)})
            if p=="/api/tts/speak":
                try:
                    import urllib.request as _ureq
                    _bd = json.dumps(body, ensure_ascii=False).encode()
                    _req = _ureq.Request("http://127.0.0.1:8081/tts/speak", data=_bd, headers={"Content-Type":"application/json"})
                    with _ureq.urlopen(_req, timeout=30) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(500, {"ok":False,"error":str(_e)})
            if p=="/api/user/profile": self._j(200,self._update_user(body)); return
            if p=="/api/door/control": self._j(200,{"success":True,"state":"open" if body.get("action")=="open" else "closed"}); return
            self._j(404,{"error":"nf"})
        except Exception as e: self._j(500,{"error":str(e)})

    # ---- 数据库操作方法 ----
    def _get_devices(self):
        conn=_db(); rows=conn.execute("SELECT id,name,type,status,room,icon,primary_value,is_on,mode,battery,protocol FROM devices").fetchall(); conn.close()
        result=[]
        for r in rows:
            d={"id":r[0],"name":r[1],"type":r[2],"status":r[3],"room":r[4],"icon":r[5],"primaryValue":r[6],"isOn":bool(r[7])}
            if r[8]: d["mode"]=r[8]
            if r[9]: d["battery"]=r[9]
            if r[10]: d["protocol"]=r[10]
            result.append(d)
        return result

    def _get_sensors(self):
        conn=_db(); rows=conn.execute("SELECT id,name,type,sensor_group,room,icon,current_value,unit,threshold_min,threshold_max,protocol,is_alert FROM sensors").fetchall(); conn.close()
        result=[]
        for r in rows:
            s={"id":r[0],"name":r[1],"type":r[2],"group":r[3],"room":r[4],"icon":r[5],"current":{"value":r[6],"unit":r[7]},"protocol":r[10],"isAlert":bool(r[11])}
            if r[8] is not None: s["thresholdMin"]=r[8]
            if r[9] is not None: s["thresholdMax"]=r[9]
            # 用真实传感器数据覆盖
            with _SENSOR_LOCK:
                cached = _SENSOR_CACHE.get(r[0])
            if cached and (time.time() - cached["ts"]) < 120:
                s["current"] = {"value": cached["value"], "unit": cached["unit"]}
            result.append(s)
        return result

    def _get_scenes(self):
        conn=_db(); scenes=[]
        for s in conn.execute("SELECT id,name,icon,color,is_active,description FROM scenes").fetchall():
            actions=[]
            for a in conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order",(s[0],)).fetchall():
                act={"deviceId":a[0],"isOn":bool(a[1])}
                if a[2] is not None: act["primaryValue"]=a[2]
                actions.append(act)
            scenes.append({"id":s[0],"name":s[1],"icon":s[2],"color":s[3],"isActive":bool(s[4]),"description":s[5],"actions":actions})
        conn.close(); return scenes

    def _get_user(self):
        conn=_db()
        r=conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        dc=conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        conn.close()
        if not r: return {"id":"u001","nickname":"用户","homeName":"我的家","memberCount":3,"deviceCount":dc}
        return {"id":r[0],"nickname":r[1],"homeName":r[2],"memberCount":r[3],"deviceCount":dc}

    def _get_operations(self,device_id=None,days=7):
        conn=_db()
        time_filter = f"datetime('now','-{days} days')"
        if device_id:
            rows=conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE device_id=? AND created_at>={time_filter} ORDER BY created_at DESC LIMIT 200",(device_id,)).fetchall()
        else:
            rows=conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE created_at>={time_filter} ORDER BY created_at DESC LIMIT 200").fetchall()
        conn.close()
        return [{"device_id":r[0],"action":r[1],"params":r[2],"result":r[3],"source":r[4],"scene_id":r[5],"timestamp":r[6]} for r in rows]

    def _activate_scene(self,scene_id):
        conn=_db()
        conn.execute("UPDATE scenes SET is_active=0")
        conn.execute("UPDATE scenes SET is_active=1, updated_at=datetime('now') WHERE id=?", (scene_id,))
        name_r=conn.execute("SELECT name FROM scenes WHERE id=?", (scene_id,)).fetchone()
        if not name_r: conn.commit(); conn.close(); return {"success":False,"error":"场景不存在"}
        actions=conn.execute("SELECT device_id,is_on,primary_value FROM scene_actions WHERE scene_id=? ORDER BY sort_order",(scene_id,)).fetchall()
        count=0
        for dev_id,is_on,pv in actions:
            conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?",(1 if is_on else 0,dev_id))
            if pv is not None:
                conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?",(pv,dev_id))
            conn.execute("INSERT INTO device_operations(device_id,action,params_json,source,scene_id) VALUES(?,?,?,?,?)",
                         (dev_id,"scene_toggle",json.dumps({"isOn":bool(is_on),"primaryValue":pv},ensure_ascii=False),"scene",scene_id))
            count+=1
        conn.execute("INSERT INTO chat_history(user_id,role,content,scene_id) VALUES('u001','assistant',?,?)",
                     (f"已切换到「{name_r[0]}」模式，控制 {count} 台设备",scene_id))
        conn.commit(); conn.close()

        # 真实硬件执行
        hw_results = hw_scene_execute(actions)
        hw_ok_count = sum(1 for r in hw_results if r["success"])
        hw_fail_count = len(hw_results) - hw_ok_count
        hw_any_ok = hw_ok_count > 0

        # 语音反馈
        _vs_scene_map = {"s1":"欢迎回家，回家模式已激活","s2":"离家模式已激活，注意安全","s3":"睡眠模式已激活，晚安","s4":"观影模式已激活，请享受","s5":"用餐模式已激活，请慢用"}
        scene_text = _vs_scene_map.get(scene_id, f"{name_r[0]}模式已激活")

        if hw_fail_count > 0 and hw_any_ok:
            tts_text = f"{scene_text}，{hw_fail_count}台设备调用失败"
        elif hw_fail_count > 0 and not hw_any_ok:
            tts_text = f"{name_r[0]}模式调用失败"
        else:
            tts_text = scene_text

        _tts_speak(tts_text)

        # voiceSequence
        _vs_texts = [scene_text]
        for _d,_io,_pv in actions:
            _dn = {"light_01":"客厅主灯","light_02":"厨房灯","light_03":"卧室灯","light_04":"卫生间灯","light_05":"客厅氛围灯","ac_01":"客厅空调","fan_01":"客厅吊扇","fan_02":"换气扇","curtain_01":"智能窗帘","door_01":"客厅大门","alarm_01":"蜂鸣警报","camera_01":"客厅摄像头","exhaust_01":"抽风机","nfc_01":"NFC门禁","voice_01":"语音中控","radar_01":"毫米波雷达"}.get(_d, _d)
            # 检查该设备硬件是否失败
            hw_r = next((r for r in hw_results if r["device_id"] == _d), None)
            if hw_r and not hw_r["success"]:
                _vs_texts.append(f"{_dn}调用失败")
            else:
                _vs_texts.append(f"{_dn}已{'开启' if _io else '关闭'}")
        _vs_seq = []
        for i, _t in enumerate(_vs_texts):
            _entry = _vs_entry(_t)
            if i > 0: _entry["delay"] = 500
            _vs_seq.append(_entry)

        return {"success":True,"scene_name":name_r[0],"affected_count":count,"voiceSequence":_vs_seq,"hardwareOnline":hw_any_ok}

    def _toggle_device(self,device_id,body):
        conn=_db()
        is_on=bool(body.get("isOn",False))
        conn.execute("UPDATE devices SET is_on=?, updated_at=datetime('now') WHERE id=?",(1 if is_on else 0,device_id))
        conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                     (device_id,"toggle",json.dumps({"isOn":is_on}),"api"))
        r=conn.execute("SELECT id,name,type,room,icon,primary_value,is_on FROM devices WHERE id=?", (device_id,)).fetchone()
        conn.commit(); conn.close()
        if not r: return {"success":False,"error":"设备不存在"}

        # 真实硬件调用
        hw_result = hw_toggle(device_id, is_on)
        dev_name = r[1]

        # 语音反馈: 成功/失败都播报
        if hw_result["success"]:
            vs_text = f"{dev_name}已{'开启' if is_on else '关闭'}"
        else:
            vs_text = f"{dev_name}调用失败"
        _tts_speak(vs_text)

        return {"success":True,"device":{"id":r[0],"name":r[1],"type":r[2],"room":r[3],"icon":r[4],"primaryValue":r[5],"isOn":bool(r[6])},"voiceSequence":[_vs_entry(vs_text)],"hardwareOnline":hw_result["success"]}

    def _control_device(self,device_id,body):
        conn=_db()
        action=body.get("action",""); ps=body.get("params",{})
        if action in ("set_speed","set_temp","set_brightness") and "value" in ps:
            conn.execute("UPDATE devices SET primary_value=?, updated_at=datetime('now') WHERE id=?",(ps["value"],device_id))
        if action=="set_mode" and "mode" in ps:
            conn.execute("UPDATE devices SET mode=?, updated_at=datetime('now') WHERE id=?",(ps["mode"],device_id))
        conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                     (device_id,action,json.dumps(ps,ensure_ascii=False),"api"))
        r=conn.execute("SELECT id,name,type,primary_value,is_on FROM devices WHERE id=?", (device_id,)).fetchone()
        conn.commit(); conn.close()
        if not r: return {"success":False,"error":"设备不存在"}

        # 真实硬件调用
        hw_result = hw_control(device_id, action, ps)
        dev_name = r[1]

        # 语音反馈
        if hw_result["success"]:
            _vs_text_map = {"set_temp":f"空调温度已设置为{ps.get('value','')}度","set_mode":f"空调模式已切换为{ps.get('mode','')}","set_speed":f"风速已设置为{ps.get('value','')}","set_brightness":f"灯光亮度已设置为{ps.get('value','')}%","toggle":f"{dev_name}已{'开启' if bool(r[4]) else '关闭'}"}
            vs_text = _vs_text_map.get(action, f"{dev_name}已控制")
        else:
            vs_text = f"{dev_name}调用失败"
        _tts_speak(vs_text)

        return {"success":True,"device":{"id":r[0],"name":r[1],"type":r[2],"primaryValue":r[3],"isOn":bool(r[4])},"voiceSequence":[_vs_entry(vs_text)],"hardwareOnline":hw_result["success"]}

    def _add_device(self,body):
        did=body.get("id",f"d{int(time.time())%10000}")
        conn=_db()
        conn.execute("INSERT OR IGNORE INTO devices(id,name,type,room,icon,primary_value,is_on,status) VALUES(?,?,?,?,?,0,0,'online')",
                     (did,body.get("name","新设备"),body.get("type","light"),body.get("room","客厅"),body.get("icon","lightbulb")))
        r=conn.execute("SELECT id,name,type,room FROM devices WHERE id=?", (did,)).fetchone()
        conn.commit(); conn.close()
        return {"success":True,"device":{"id":r[0],"name":r[1],"type":r[2],"room":r[3]}}

    def _update_user(self,body):
        conn=_db()
        if "nickname" in body: conn.execute("UPDATE users SET nickname=? WHERE id='u001'",(body["nickname"],))
        if "homeName" in body: conn.execute("UPDATE users SET home_name=? WHERE id='u001'",(body["homeName"],))
        if "memberCount" in body: conn.execute("UPDATE users SET member_count=? WHERE id='u001'",(body["memberCount"],))
        r=conn.execute("SELECT id,nickname,home_name,member_count FROM users WHERE id='u001'").fetchone()
        conn.commit(); conn.close()
        return {"id":r[0],"nickname":r[1],"homeName":r[2],"memberCount":r[3]}

    def _chat(self,body):
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
                "hardwareOnline": hw_ok}

    def _bearpi(self,body):
        cmd=body.get("command","").strip()
        if not cmd: return {"success":False,"error":"missing command"}
        if cmd.startswith("brightness:"):
            _,room,value=cmd.split(":")
            return bearpi_brightness(int(room),int(value))
        return {"success":False,"error":"unsupported command"}

def load_env():
    global DEEPSEEK_API_KEY
    ep=ROOT/"HarmonyOS-mcp-server"/".deepseek_env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if line.startswith("export "): line=line[7:]
            if "=" in line:
                k,v=line.split("=",1); os.environ[k.strip()]=v.strip()
                if k.strip()=="DEEPSEEK_API_KEY": DEEPSEEK_API_KEY=v.strip()

def main():
    load_env(); db_init(); _save_reg()
    # 传感器轮询线程
    threading.Thread(target=sensor_poll_thread, daemon=True).start()
    refresh_arp()
    # 启动数据推送服务
    try:
        from data_pusher import start_pusher
        start_pusher()
        log("[PUSHER] 数据推送服务已启动 → yuanzhe.tech")
    except Exception as e:
        log(f"[PUSHER] 推送服务启动失败: {e}")
    # 启动网络通道服务 (WebSocket 长连接)
    try:
        from channel import start_channel, tts_speak_key, tts_speak
        start_channel()
        log("[CHANNEL] 网络通道服务已启动 → yuanzhe.tech")
    except ImportError:
        tts_speak_key = lambda *a, **kw: False
        tts_speak = lambda *a, **kw: False
        log("[CHANNEL] 通道模块不可用，TTS 降级为静音")
    except Exception as e:
        log(f"[CHANNEL] 通道服务启动失败: {e}")
    # 硬件状态
    if _HW_OK:
        log("[HW] ✓ 硬件控制已加载 (central_controller)")
    else:
        log("[HW] ✗ 硬件控制未加载，降级为数据库模式")
    srv=ThreadingHTTPServer((HOST,PORT),H)
    log("="*50)
    log(f"智慧家居网关v3 :{PORT} {DEEPSEEK_MODEL}")
    log(f"硬件控制: {'已启用' if _HW_OK else '未加载'}")
    log(f"RAG知识库: {_rag.get_stats()}")
    log(f"数据库: {DB_PATH}")
    log("="*50)
    srv.serve_forever()

if __name__=="__main__":
    main()
