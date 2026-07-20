#!/usr/bin/env python3
"""Patch channel.py - Make AI chat backend configurable (DeepSeek / iFlytek / any OpenAI-compatible)"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    ch = f.read()

# 1. Add AI config global (near _TTS_CONFIG)
old_tts_config_end = '''    "backend": "wav",   # 播放后端: "wav"=预生成语音, "beep"=蜂鸣音, "none"=静音
}'''

new_ai_config = '''    "backend": "wav",   # 播放后端: "wav"=预生成语音, "beep"=蜂鸣音, "none"=静音
}

# ===== AI 对话后端配置 (前端可调) =====
_AI_CONFIG = {
    "provider": "iflytek",  # 当前使用的 AI 后端: "deepseek" / "iflytek" / "custom"
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
            "key": "b1d05a56fad383dd48b6e0a19a195075:YjQzY2E4MmMwMDQ4ZTViYzM4MWQ0Y2I0",
            "model": "4.0Ultra",
            "maxTokens": 200,
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
}'''

ch = ch.replace(old_tts_config_end, new_ai_config)

# 2. Replace the DeepSeek call in send_chat with configurable AI backend
old_deepseek_call = '''                # DeepSeek
                api_key = os.environ.get("DEEPSEEK_API_KEY", "")
                if api_key:
                    try:
                        body = json.dumps({
                            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                            "messages": [{"role": "user", "content": content}],
                            "temperature": 0.3, "max_tokens": 200
                        }, ensure_ascii=False).encode()
                        req = Request("https://api.deepseek.com/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
                        with urlopen(req, timeout=30) as r:
                            reply = json.loads(r.read().decode())["choices"][0]["message"]["content"]
                    except Exception as e:
                        reply = f"大模型不可用: {e}"
                else:
                    reply = "未配置AI"'''

new_ai_call = '''                # AI 对话后端 (可配置: DeepSeek / 讯飞 / 自定义)
                provider = _AI_CONFIG.get("provider", "deepseek")
                prov_cfg = _AI_CONFIG.get("models", {}).get(provider, {})
                ai_url = prov_cfg.get("url", "")
                ai_key = prov_cfg.get("key", "")
                ai_model = prov_cfg.get("model", "deepseek-chat")
                ai_max_tokens = prov_cfg.get("maxTokens", 200)
                ai_temp = prov_cfg.get("temperature", 0.3)
                if ai_url and ai_key:
                    try:
                        body = json.dumps({
                            "model": ai_model,
                            "messages": [{"role": "user", "content": content}],
                            "temperature": ai_temp, "max_tokens": ai_max_tokens
                        }, ensure_ascii=False).encode()
                        req = Request(ai_url, data=body,
                                     headers={"Authorization": f"Bearer {ai_key}", "Content-Type": "application/json"}, method="POST")
                        with urlopen(req, timeout=30) as r:
                            resp = json.loads(r.read().decode())
                            reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                            if not reply:
                                reply = json.dumps(resp, ensure_ascii=False)[:200]
                    except Exception as e:
                        reply = f"AI({provider})不可用: {e}"
                else:
                    reply = f"未配置AI({provider})"'''

ch = ch.replace(old_deepseek_call, new_ai_call)

# 3. Add AI config API endpoints to LocalAPI do_GET
old_tts_list_get = '''        elif p == "/tts/list":'''

new_ai_get = '''        elif p == "/ai/config":
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
        elif p == "/tts/list":'''

ch = ch.replace(old_tts_list_get, new_ai_get)

# 4. Add AI config API to do_POST
old_tts_test_post = '''        elif p == "/tts/test":'''

new_ai_post = '''        elif p == "/ai/config":
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
        elif p == "/tts/test":'''

ch = ch.replace(old_tts_test_post, new_ai_post)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(ch)

print("channel.py patched: AI config + API endpoints added")
