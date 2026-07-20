#!/usr/bin/env python3
"""Patch gateway_v3.py - Add AI config proxy endpoints"""

with open("/data/A9/smart_home/gateway_v3.py", "r", encoding="utf-8") as f:
    gw = f.read()

# Add GET /api/ai/config
old = '''            elif p=="/api/tts/list":
                try:
                    import urllib.request as _ureq
                    with _ureq.urlopen("http://127.0.0.1:8081/tts/list", timeout=3) as _ur:
                        self._j(200, json.loads(_ur.read().decode()))
                except Exception as _e:
                    self._j(200, {"total":0,"files":[],"error":str(_e)})'''

new = '''            elif p=="/api/ai/config":
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
                    self._j(200, {"total":0,"files":[],"error":str(_e)})'''

gw = gw.replace(old, new)

# Add POST /api/ai/config and /api/ai/test
old2 = '            if p=="/api/tts/config":'
new2 = '''            if p=="/api/ai/config":
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
            if p=="/api/tts/config":'''

gw = gw.replace(old2, new2)

with open("/data/A9/smart_home/gateway_v3.py", "w", encoding="utf-8") as f:
    f.write(gw)

print("gateway_v3.py patched: AI config proxy endpoints added")
