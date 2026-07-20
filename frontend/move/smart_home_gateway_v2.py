#!/usr/bin/env python3
"""智慧家居 HTTP 网关 v2 · 门禁socket+温湿度TCP+flash对话+MAC自动发现"""
from __future__ import annotations
import json, os, re, socket, sqlite3, subprocess, threading, time, zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

HOST = "0.0.0.0"; PORT = 8080
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "control" / "data" / "control.db"
SCHEMA_PATH = ROOT / "control" / "database" / "schema.sql"
LOG_PATH = ROOT / "gateway.log"
REGISTRY_PATH = ROOT / "device_registry.json"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = "deepseek-v4-flash"

# MAC→IP 注册表（防 IP 变化）
# .62 实际是 DHT11 温湿度传感器（非门禁）。门禁设备当前离线，待发现。
REGISTRY = {
    "door_main": {"name": "入户门禁", "mac": "", "last_ip": "", "port": 8000, "offline": True},
    "temp_humidity": {"name": "温湿度DHT11", "mac": "94:c9:60:e6:8b:70", "last_ip": "192.168.1.62", "port": 8000},
    "dev_board": {"name": "开发板", "mac": "f0:a8:82:21:08:84", "last_ip": "192.168.1.81", "port": 8080},
}
LIVE = {"temp": 24.6, "humidity": 52.0, "last_update": 0}

def log(m):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass

def now_ms(): return int(time.time() * 1000)

# ===== MAC→IP 发现 =====
def find_ip_by_mac(mac):
    try:
        with open("/proc/net/arp") as f:
            for line in f:
                p = line.split()
                if len(p) >= 4 and p[3].lower() == mac.lower(): return p[0]
    except: pass
    try:
        r = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            if mac.lower() in line.lower():
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if m: return m.group(1)
    except: pass
    return None

def _reachable(ip, port, timeout=1.0):
    try:
        s = socket.create_connection((ip, port), timeout=timeout); s.close(); return True
    except: return False

def get_device_ip(key):
    dev = REGISTRY.get(key)
    if not dev: return None
    if _reachable(dev["last_ip"], dev["port"]): return dev["last_ip"]
    nip = find_ip_by_mac(dev["mac"])
    if nip and _reachable(nip, dev["port"]):
        dev["last_ip"] = nip; _save_reg()
        log(f"[DISCOVERY] {key} →{nip}")
        return nip
    return None

def refresh_arp():
    def _sw():
        for i in range(1, 255):
            try:
                s = socket.socket(); s.settimeout(0.05); s.connect_ex(("192.168.1." + str(i), 80)); s.close()
            except: pass
    threading.Thread(target=_sw, daemon=True).start()

def _save_reg():
    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f: json.dump(REGISTRY, f, indent=2, ensure_ascii=False)
    except: pass

# ===== 门禁（二进制帧）=====
HDR = bytes([0xAA, 0x55]); TAIL = bytes([0x55, 0xAA]); PKT_SZ = 32
BEARPI_CMD_REPORT_STATUS = 0
BEARPI_CMD_BRIGHTNESS = 1
BEARPI_CMD_HUMAN_DETECT = 2
BEARPI_CMD_RADAR_PARAM = 3
BEARPI_RADAR_OP_QUERY = 0

def _bearpi_pkt(cmd, room, val):
    c = bytearray(24)
    c[0] = cmd
    c[1] = room
    c[2] = val
    crc = zlib.crc32(bytes(c)) & 0xFFFFFFFF
    return HDR + crc.to_bytes(4, "little") + bytes(c) + TAIL

def _bearpi_host():
    dev = REGISTRY.get("dev_board") or {}
    return dev.get("last_ip") or "192.168.1.81"

def bearpi_brightness(room, value):
    host = _bearpi_host()
    pkt = _bearpi_pkt(BEARPI_CMD_BRIGHTNESS, room, value)
    try:
        with socket.create_connection((host, 8000), timeout=5) as s:
            s.sendall(pkt)
            resp = s.recv(PKT_SZ)
        log(f"[BEARPI] brightness room={room} value={value} host={host} resp={resp.hex(' ')}")
        return {"success": True, "host": host, "room": room, "value": value}
    except Exception as e:
        log(f"[BEARPI] brightness err: {e}")
        return {"success": False, "host": host, "error": str(e)}

def bearpi_human(room, value):
    host = _bearpi_host()
    pkt = _bearpi_pkt(BEARPI_CMD_HUMAN_DETECT, room, value)
    try:
        with socket.create_connection((host, 8000), timeout=5) as s:
            s.sendall(pkt)
            resp = s.recv(PKT_SZ)
        log(f"[BEARPI] human room={room} value={value} host={host} resp={resp.hex(' ')}")
        return {"success": True, "host": host, "room": room, "value": value}
    except Exception as e:
        log(f"[BEARPI] human err: {e}")
        return {"success": False, "host": host, "error": str(e)}

def bearpi_radar_query(param=0x0101):
    host = _bearpi_host()
    c = bytearray(24)
    c[0] = BEARPI_CMD_RADAR_PARAM
    c[1] = BEARPI_RADAR_OP_QUERY
    c[2:4] = int(param).to_bytes(2, "little", signed=False)
    pkt = HDR + (zlib.crc32(bytes(c)) & 0xFFFFFFFF).to_bytes(4, "little") + bytes(c) + TAIL
    try:
        with socket.create_connection((host, 8000), timeout=5) as s:
            s.sendall(pkt)
            resp = s.recv(PKT_SZ)
        log(f"[BEARPI] radar query param=0x{int(param):04x} host={host} resp={resp.hex(' ')}")
        return {"success": True, "host": host, "param": int(param)}
    except Exception as e:
        log(f"[BEARPI] radar err: {e}")
        return {"success": False, "host": host, "error": str(e)}

def _pkt(cmd, room, val):
    c = bytearray(24); c[0]=cmd; c[1]=room; c[2]=val
    crc = zlib.crc32(bytes(c)) & 0xFFFFFFFF
    return HDR + crc.to_bytes(4, "little") + bytes(c) + TAIL

def control_door(action):
    ip = get_device_ip("door_main")
    if not ip: return {"success": False, "error": "门禁离线"}
    pkt = _pkt(0x01, 0, 1) if action == "open" else _pkt(0x01, 0, 0) if action == "close" else _pkt(0x00, 0, 1)
    try:
        with socket.create_connection((ip, 8000), timeout=5) as s:
            s.sendall(pkt); r = s.recv(PKT_SZ)
        state = "open" if (len(r) >= 9 and r[8] == 1) else "closed"
        log(f"[DOOR] {action}→{state} ip={ip}")
        return {"success": True, "state": state, "ip": ip}
    except Exception as e:
        log(f"[DOOR] {action} err: {e}")
        return {"success": False, "error": str(e)}

def control_light_device(dev, on):
    room = 0 if dev["id"] in ("light_01", "fan_01", "ac_01") else 1
    value = 80 if on else 0
    res = bearpi_brightness(room, value)
    if res.get("success"):
        dev["isOn"] = on
        dev["primaryValue"] = value
    return res

# ===== 温湿度监听 =====
def temp_listener():
    while True:
        ip = get_device_ip("temp_humidity")
        if not ip: time.sleep(10); continue
        try:
            s = socket.create_connection((ip, 8000), timeout=5); s.settimeout(10); buf = b""
            while True:
                data = s.recv(1024)
                if not data: break
                buf += data
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    _parse_sensor(line.decode("utf-8", errors="replace"))
        except Exception as e: log(f"[SENSOR] {e}")
        time.sleep(5)

def _parse_sensor(line):
    line = line.strip()
    if line.startswith("DATA"):
        try:
            parts = dict(p.split("=") for p in line.split(",")[1:] if "=" in p)
            if "temp" in parts: LIVE["temp"] = float(parts["temp"])
            if "humid" in parts: LIVE["humidity"] = float(parts["humid"])
            elif "humidity" in parts: LIVE["humidity"] = float(parts["humidity"])
            elif "humi" in parts: LIVE["humidity"] = float(parts["humi"])
            LIVE["last_update"] = time.time()
        except: pass

# ===== DB =====
def db_init():
    if SCHEMA_PATH.exists():
        try:
            with sqlite3.connect(str(DB_PATH)) as c: c.executescript(SCHEMA_PATH.read_text("utf-8"))
        except: pass

def save_cmd(t, cmd, payload, result="ok"):
    try:
        with sqlite3.connect(str(DB_PATH)) as c:
            c.execute("INSERT INTO control_commands(target,command,payload_json,result) VALUES(?,?,?,?)",
                      (t, cmd, json.dumps(payload, ensure_ascii=False), result))
    except: pass

# ===== 数据 =====
DEVICES = [
    {"id": "fan_01", "name": "客厅吊扇", "type": "fan", "status": "online", "room": "客厅", "icon": "fan_fill_1", "primaryValue": 2, "isOn": True, "battery": 100},
    {"id": "fan_02", "name": "卧室循环扇", "type": "fan", "status": "online", "room": "主卧", "icon": "fan_fill_1", "primaryValue": 1, "isOn": False, "battery": 88},
    {"id": "ac_01", "name": "客厅中央空调", "type": "ac", "status": "active", "room": "客厅", "icon": "air_fill", "primaryValue": 24, "isOn": True, "mode": "制冷"},
    {"id": "ac_02", "name": "主卧空调", "type": "ac", "status": "online", "room": "主卧", "icon": "air_fill", "primaryValue": 26, "isOn": False, "mode": "制冷"},
    {"id": "door_01", "name": "入户门禁", "type": "door", "status": "online", "room": "玄关", "icon": "door_service", "primaryValue": 0, "isOn": False, "battery": 92},
    {"id": "light_01", "name": "客厅主灯", "type": "light", "status": "online", "room": "客厅", "icon": "lightbulb", "primaryValue": 80, "isOn": True},
    {"id": "light_02", "name": "卧室氛围灯", "type": "light", "status": "online", "room": "主卧", "icon": "lightbulb", "primaryValue": 40, "isOn": False},
]
DSTATE = {d["id"]: dict(d) for d in DEVICES}
CAMS = [
    {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online", "isRecording": True, "resolution": "2K", "previewColor": "#1A3A5C"},
    {"id": "cam_02", "name": "入户门铃", "room": "玄关", "status": "online", "isRecording": True, "resolution": "1080P", "previewColor": "#3A1A5C"},
]
ALERTS = [
    {"id": "a1", "source": "人体感应", "content": "检测到人体活动", "level": "danger", "isRead": False, "timestamp": now_ms() - 300000},
    {"id": "a2", "source": "门铃", "content": "有人按门铃", "level": "info", "isRead": False, "timestamp": now_ms() - 1800000},
]

def sensors():
    return [
        {"id": "temp_01", "name": "客厅温度", "type": "temperature", "group": "环境监测", "room": "客厅", "icon": "thermometer", "current": {"value": LIVE["temp"], "unit": "°C"}, "thresholdMax": 35, "protocol": "wifi", "isAlert": LIVE["temp"] > 35},
        {"id": "humid_01", "name": "客厅湿度", "type": "humidity", "group": "环境监测", "room": "客厅", "icon": "drop", "current": {"value": LIVE["humidity"], "unit": "%RH"}, "thresholdMax": 70, "protocol": "wifi", "isAlert": False},
        {"id": "air_01", "name": "PM2.5", "type": "air_quality", "group": "环境监测", "room": "客厅", "icon": "wind", "current": {"value": 18, "unit": "μg/m³"}, "thresholdMax": 75, "protocol": "wifi", "isAlert": False},
        {"id": "light_s_01", "name": "光照度", "type": "illuminance", "group": "环境监测", "room": "客厅", "icon": "sun_max", "current": {"value": 842, "unit": "lux"}, "thresholdMax": 2000, "protocol": "starflash", "isAlert": False},
        {"id": "pir_01", "name": "人体感应", "type": "pir", "group": "安防", "room": "客厅", "icon": "figure_arms_open", "current": {"value": 1, "unit": "触发"}, "thresholdMax": 1, "protocol": "starflash", "isAlert": True},
        {"id": "smoke_01", "name": "厨房烟雾", "type": "smoke", "group": "安防", "room": "厨房", "icon": "flame_fill", "current": {"value": 0, "unit": "正常"}, "thresholdMax": 1, "protocol": "wifi", "isAlert": False},
        {"id": "power_01", "name": "实时功率", "type": "power", "group": "能耗", "room": "全屋", "icon": "bolt_fill", "current": {"value": 1.86, "unit": "kW"}, "thresholdMax": 10, "protocol": "wifi", "isAlert": False},
    ]

# ===== DeepSeek flash =====
def chat(msgs):
    if not DEEPSEEK_API_KEY: return "（未配置KEY）"
    body = {"model": DEEPSEEK_MODEL, "messages": [{"role": "system", "content": "你是智慧家居助手，简洁回答(100字内)"}] + msgs, "temperature": 0.3, "max_tokens": 200}
    req = Request(f"{DEEPSEEK_BASE_URL}/chat/completions", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=30) as r: return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
    except Exception as e: log(f"[CHAT] {e}"); return "（大模型暂时不可用）"

# ===== HTTP =====
class H(BaseHTTPRequestHandler):
    def _j(self, c, d):
        b = json.dumps(d, ensure_ascii=False).encode("utf-8")
        self.send_response(c); self.send_header("Content-Type", "application/json;charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b)
    def _b(self):
        n = int(self.headers.get("Content-Length", 0))
        if not n: return {}
        try: return json.loads(self.rfile.read(n).decode("utf-8"))
        except: return {}
    def do_OPTIONS(self): self._j(200, {"ok": True})
    def log_message(self, *a): log(f"{self.command} {self.path}")
    def do_GET(self):
        p = self.path.split("?")[0]
        try:
            if p == "/health": self._j(200, {"ok": True, "v": 2})
            elif p == "/api/devices": self._j(200, list(DSTATE.values()))
            elif p == "/api/sensors": self._j(200, sensors())
            elif p == "/api/cameras": self._j(200, CAMS)
            elif p == "/api/alerts": self._j(200, ALERTS)
            elif p == "/api/user/profile": self._j(200, {"id": "u001", "nickname": "用户", "homeName": "我的家", "memberCount": 3, "deviceCount": len(DSTATE)})
            elif p == "/api/server/status": self._j(200, {"host": "192.168.1.81", "port": PORT, "isOnline": True, "protocol": "wifi", "latency": 8, "cpuUsage": 30, "memUsage": 45, "storageUsage": 38})
            elif p == "/api/door/status": self._j(200, control_door("query"))
            elif p == "/api/devices/discover":
                refresh_arp(); time.sleep(2); r = {}
                for k in REGISTRY:
                    ip = get_device_ip(k); r[k] = {"name": REGISTRY[k]["name"], "ip": ip, "online": ip is not None, "mac": REGISTRY[k]["mac"]}
                self._j(200, r)
            else: self._j(404, {"error": "nf"})
        except Exception as e: self._j(500, {"error": str(e)})
    def do_POST(self):
        p = self.path.split("?")[0]; body = self._b()
        try:
            if p == "/api/door/control": self._j(200, control_door(body.get("action", "query"))); return
            if p == "/api/bearpi/command":
                cmd = str(body.get("command", "")).strip()
                if not cmd:
                    self._j(400, {"success": False, "error": "missing command"}); return
                if cmd.startswith("brightness:"):
                    _, room, value = cmd.split(":")
                    self._j(200, bearpi_brightness(int(room), int(value))); return
                if cmd.startswith("human:"):
                    _, room, value = cmd.split(":")
                    self._j(200, bearpi_human(int(room), int(value))); return
                if cmd.startswith("radar-query:"):
                    _, param = cmd.split(":", 1)
                    self._j(200, bearpi_radar_query(int(param, 0))); return
                self._j(400, {"success": False, "error": "unsupported command"}); return
            m = re.match(r"^/api/devices/([\w_]+)/control$", p)
            if m:
                did = m.group(1); dev = DSTATE.get(did)
                if not dev: self._j(404, {"e": "nf"}); return
                a = body.get("action", ""); ps = body.get("params", {})
                if dev["type"] == "door":
                    r = control_door("open" if ps.get("value", 0) == 1 else "close"); dev["isOn"] = r.get("state") == "open"
                    self._j(200, {"success": r.get("success"), "device": dev}); return
                if dev["type"] == "light" and a in ("set_brightness", "toggle"):
                    r = control_light_device(dev, bool(ps.get("value", dev.get("isOn", False))) if a == "toggle" else ps.get("value", 0) > 0)
                    if not r.get("success"):
                        self._j(502, {"success": False, "device": dev, "error": r.get("error")}); return
                    self._j(200, {"success": True, "device": dev, "result": r}); return
                if a in ("set_speed", "set_temp", "set_brightness") and "value" in ps: dev["primaryValue"] = ps["value"]
                save_cmd(did, a, ps); self._j(200, {"success": True, "device": dev}); return
            m = re.match(r"^/api/devices/([\w_]+)/toggle$", p)
            if m:
                did = m.group(1); dev = DSTATE.get(did)
                if not dev: self._j(404, {"e": "nf"}); return
                on = bool(body.get("isOn", not dev["isOn"]))
                if dev["type"] == "door":
                    r = control_door("open" if on else "close"); on = r.get("state") == "open"
                elif dev["type"] == "light":
                    r = control_light_device(dev, on)
                    if not r.get("success"):
                        self._j(502, {"success": False, "device": dev, "error": r.get("error")}); return
                dev["isOn"] = on; self._j(200, {"success": True, "device": dev}); return
            if p == "/api/devices":
                nd = {"id": body.get("id", f"d{int(time.time())}"), "name": body.get("name", "新设备"), "type": body.get("type", "light"), "status": "online", "room": body.get("room", "客厅"), "icon": body.get("icon", "lightbulb"), "primaryValue": body.get("primaryValue", 0), "isOn": False}
                DSTATE[nd["id"]] = nd; self._j(200, {"success": True, "device": nd}); return
            if p == "/api/chat/send":
                ms = body.get("messages", [])
                ds = [{"role": x.get("role", "user"), "content": x.get("content", "")} for x in ms]
                self._j(200, {"reply": chat(ds), "role": "assistant"}); return
            self._j(404, {"e": "nf"})
        except Exception as e: self._j(500, {"error": str(e)})

def load_env():
    global DEEPSEEK_API_KEY
    ep = ROOT / "HarmonyOS-mcp-server" / ".deepseek_env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "): line = line[7:]
            if "=" in line:
                k, v = line.split("=", 1); os.environ[k.strip()] = v.strip()
                if k.strip() == "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY = v.strip()

def main():
    load_env(); db_init(); _save_reg()
    threading.Thread(target=temp_listener, daemon=True).start(); refresh_arp()
    srv = ThreadingHTTPServer((HOST, PORT), H)
    log("=" * 50)
    log(f"智慧家居网关v2 :{PORT} {DEEPSEEK_MODEL}")
    log(f"门禁 {REGISTRY['door_main']['mac']} @{REGISTRY['door_main']['last_ip']}")
    log(f"温湿度 {REGISTRY['temp_humidity']['mac']} @{REGISTRY['temp_humidity']['last_ip']}")
    log("=" * 50)
    srv.serve_forever()

if __name__ == "__main__":
    main()
