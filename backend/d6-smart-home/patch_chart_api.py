#!/usr/bin/env python3
"""Patch gateway_v6.py - Add /api/log/chart with Kimi chart generation"""

PATH = "/data/A9/smart_home/gateway_v6.py"

with open(PATH, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add Kimi model to _AI_CONFIG
if "kimi" not in code:
    old_astron = '''        "astron": {
            "url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",
            "key": os.environ.get("ASTRON_API_KEY", ""),
            "model": "astron-code-latest",
            "maxTokens": 32768,
            "temperature": 0.3,
        },
    },
}'''
    new_astron = '''        "astron": {
            "url": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",
            "key": os.environ.get("ASTRON_API_KEY", ""),
            "model": "astron-code-latest",
            "maxTokens": 32768,
            "temperature": 0.3,
        },
        "kimi": {
            "url": "https://api.moonshot.cn/v1/chat/completions",
            "key": os.environ.get("KIMI_API_KEY", ""),
            "model": "moonshot-v1-8k",
            "maxTokens": 4096,
            "temperature": 0.1,
        },
    },
}'''
    code = code.replace(old_astron, new_astron, 1)
    print("KIMI_CONFIG_ADDED")
else:
    print("KIMI_CONFIG_EXISTS")

# 2. Add /api/log/chart route
if "/api/log/chart" not in code:
    # Insert after /api/log/today route block
    # Find the right spot - after the /api/log/today handler
    old_today_end = '''                    self._j(200, {"today": dict(zip(cols, row)) if row else {"log_date": today}, "realtime": realtime})
                    self._log_remote_access(auth, p)'''
    new_today_end = '''                    self._j(200, {"today": dict(zip(cols, row)) if row else {"log_date": today}, "realtime": realtime})
                    self._log_remote_access(auth, p)
            elif p == "/api/log/chart":
                auth = self._require_auth("read")
                if auth:
                    qs = self.path.split("?", 1); chart_type = "auto"; days = 7
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                            if k == "type": chart_type = v
                            if k == "days": days = int(v)
                    self._j(200, self._generate_chart(chart_type, days))
                    self._log_remote_access(auth, p)'''
    code = code.replace(old_today_end, new_today_end, 1)
    print("CHART_ROUTE_ADDED")
else:
    print("CHART_ROUTE_EXISTS")

# 3. Add _generate_chart method and _kimi_chart_match helper
if "_generate_chart" not in code:
    chart_method = '''
# ===== 图表生成引擎 =====
_CHART_KEYWORD_MAP = {
    "七日统计": "daily_bar", "7日统计": "daily_bar", "七日": "daily_bar", "7日": "daily_bar",
    "请求趋势": "daily_line", "请求统计": "daily_line", "请求": "daily_line",
    "对话统计": "chat_line", "对话趋势": "chat_line", "AI对话": "chat_line", "聊天": "chat_line",
    "设备操作": "ops_bar", "操作统计": "ops_bar", "操作趋势": "ops_line",
    "安全事件": "security_pie", "安全统计": "security_pie", "安全": "security_pie",
    "在线率": "online_area", "设备在线": "online_area", "在线": "online_area",
    "今日实时": "today_gauge", "今日统计": "today_gauge", "实时": "today_gauge",
    "综合": "overview", "概览": "overview", "总览": "overview",
    "温度趋势": "temp_line", "温度": "temp_line",
    "湿度趋势": "humid_line", "湿度": "humid_line",
}

def _match_chart_type(keyword):
    """关键词匹配图表类型"""
    if not keyword or keyword == "auto":
        return None
    kw = keyword.strip().lower()
    # 精确匹配
    for k, v in _CHART_KEYWORD_MAP.items():
        if k in keyword:
            return v
    return None

def _kimi_chart_match(keyword, available_types):
    """调用Kimi模型匹配关键词到图表类型"""
    kimi_cfg = _AI_CONFIG.get("models", {}).get("kimi", {})
    kimi_key = kimi_cfg.get("key", "")
    if not kimi_key:
        return None
    try:
        prompt = f"""你是一个图表类型匹配器。根据用户关键词，从以下可用图表类型中选最合适的一个：

可用图表类型: {", ".join(available_types)}

- daily_bar: 七日请求/对话/操作柱状图
- daily_line: 七日趋势折线图
- chat_line: 对话量趋势折线图
- ops_bar: 设备操作柱状图
- security_pie: 安全事件饼图
- online_area: 设备在线率面积图
- today_gauge: 今日实时仪表盘
- overview: 综合概览
- temp_line: 温度趋势折线图
- humid_line: 湿度趋势折线图

用户关键词: {keyword}

只输出图表类型ID，不要其他文字。"""
        body = {
            "model": kimi_cfg.get("model", "moonshot-v1-8k"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 20,
        }
        req = Request(
            kimi_cfg.get("url", "https://api.moonshot.cn/v1/chat/completions"),
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {kimi_key}", "Content-Type": "application/json"},
            method="POST",
        )
        _ssl_ctx = ssl.create_default_context()
        with urlopen(req, timeout=10, context=_ssl_ctx) as r:
            resp = json.loads(r.read().decode("utf-8"))
            result = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip().lower()
            if result in available_types:
                return result
    except Exception as e:
        log(f"[CHART-KIMI] Kimi匹配失败: {e}")
    return None


def _generate_chart(chart_type="auto", days=7):
    """生成图表配置数据，前端可直接渲染"""
    available_types = ["daily_bar", "daily_line", "chat_line", "ops_bar", "security_pie", "online_area", "today_gauge", "overview", "temp_line", "humid_line"]

    # 确定图表类型
    resolved = None
    if chart_type != "auto":
        # 先关键词匹配
        resolved = _match_chart_type(chart_type)
        # 再Kimi匹配
        if not resolved:
            resolved = _kimi_chart_match(chart_type, available_types)
    if not resolved:
        resolved = "overview"

    conn = _db()
    try:
        # 获取daily数据
        rows = conn.execute("SELECT * FROM daily_log ORDER BY log_date DESC LIMIT ?", (days,)).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM daily_log LIMIT 0").description]
        daily = [dict(zip(cols, r)) for r in reversed(rows)]  # 按日期正序

        # 获取today数据
        today = _cst_today_str()
        today_row = conn.execute("SELECT * FROM daily_log WHERE log_date=?", (today,)).fetchone()
        today_data = dict(zip(cols, today_row)) if today_row else {"log_date": today}

        # realtime
        with _STATUS_LOCK:
            online_devices = sum(1 for d in DEVICE_DEFS if _DEVICE_STATUS.get(d["id"], {}).get("online"))
            online_sensors = sum(1 for s in SENSOR_DEFS if _SENSOR_STATUS.get(s["id"], {}).get("online"))

        dates = [d["log_date"][5:] for d in daily]  # MM-DD
    finally:
        conn.close()

    charts = []

    # ---- 七日统计柱状图 ----
    if resolved in ("daily_bar", "overview"):
        charts.append({
            "id": "daily_bar",
            "title": "七日请求/对话/操作统计",
            "type": "bar",
            "xAxis": {"type": "category", "data": dates},
            "series": [
                {"name": "请求数", "type": "bar", "data": [d.get("total_requests", 0) for d in daily]},
                {"name": "对话数", "type": "bar", "data": [d.get("total_chat", 0) for d in daily]},
                {"name": "设备操作", "type": "bar", "data": [d.get("total_device_ops", 0) for d in daily]},
            ],
        })

    # ---- 七日趋势折线图 ----
    if resolved in ("daily_line", "overview"):
        charts.append({
            "id": "daily_line",
            "title": "七日趋势折线图",
            "type": "line",
            "xAxis": {"type": "category", "data": dates},
            "series": [
                {"name": "请求数", "type": "line", "smooth": True, "data": [d.get("total_requests", 0) for d in daily]},
                {"name": "对话数", "type": "line", "smooth": True, "data": [d.get("total_chat", 0) for d in daily]},
            ],
        })

    # ---- 对话趋势 ----
    if resolved == "chat_line":
        charts.append({
            "id": "chat_line",
            "title": "七日对话趋势",
            "type": "line",
            "xAxis": {"type": "category", "data": dates},
            "series": [
                {"name": "对话数", "type": "line", "smooth": True, "areaStyle": {}, "data": [d.get("total_chat", 0) for d in daily]},
            ],
        })

    # ---- 设备操作柱状图 ----
    if resolved == "ops_bar":
        charts.append({
            "id": "ops_bar",
            "title": "七日设备操作统计",
            "type": "bar",
            "xAxis": {"type": "category", "data": dates},
            "series": [
                {"name": "设备操作", "type": "bar", "data": [d.get("total_device_ops", 0) for d in daily]},
            ],
        })

    # ---- 安全事件饼图 ----
    if resolved in ("security_pie", "overview"):
        sec_data = []
        for d in daily:
            if d.get("total_security_events", 0) > 0:
                sec_data.append({"name": d["log_date"][5:], "value": d["total_security_events"]})
        if not sec_data:
            sec_data = [{"name": "无事件", "value": 1}]
        charts.append({
            "id": "security_pie",
            "title": "安全事件分布",
            "type": "pie",
            "series": [{"type": "pie", "radius": ["40%", "70%"], "data": sec_data}],
        })

    # ---- 在线率面积图 ----
    if resolved in ("online_area", "overview"):
        charts.append({
            "id": "online_area",
            "title": "设备在线峰值",
            "type": "line",
            "xAxis": {"type": "category", "data": dates},
            "series": [
                {"name": "设备峰值", "type": "line", "smooth": True, "areaStyle": {}, "data": [d.get("devices_online_peak", 0) for d in daily]},
                {"name": "传感器峰值", "type": "line", "smooth": True, "areaStyle": {}, "data": [d.get("sensors_active", 0) for d in daily]},
            ],
        })

    # ---- 今日仪表盘 ----
    if resolved in ("today_gauge", "overview"):
        charts.append({
            "id": "today_gauge",
            "title": "今日实时统计",
            "type": "gauge",
            "data": {
                "date": today,
                "total_requests": today_data.get("total_requests", 0),
                "total_chat": today_data.get("total_chat", 0),
                "total_device_ops": today_data.get("total_device_ops", 0),
                "total_security_events": today_data.get("total_security_events", 0),
                "online_devices": online_devices,
                "total_devices": len(DEVICE_DEFS),
                "online_sensors": online_sensors,
                "total_sensors": len(SENSOR_DEFS),
            },
        })

    # ---- 温度/湿度趋势 ----
    if resolved == "temp_line":
        try:
            conn2 = _db()
            rows2 = conn2.execute("SELECT created_at, value FROM sensor_readings WHERE sensor_id='temp_01' AND created_at >= datetime('now','+8 hours','-1 day') ORDER BY created_at").fetchall()
            conn2.close()
            charts.append({"id": "temp_line", "title": "温度趋势 (24h)", "type": "line",
                "xAxis": {"type": "category", "data": [r[0][11:16] for r in rows2[-50:]]},
                "series": [{"name": "温度", "type": "line", "smooth": True, "data": [r[1] for r in rows2[-50:]]}]})
        except: pass

    if resolved == "humid_line":
        try:
            conn2 = _db()
            rows2 = conn2.execute("SELECT created_at, value FROM sensor_readings WHERE sensor_id='humid_01' AND created_at >= datetime('now','+8 hours','-1 day') ORDER BY created_at").fetchall()
            conn2.close()
            charts.append({"id": "humid_line", "title": "湿度趋势 (24h)", "type": "line",
                "xAxis": {"type": "category", "data": [r[0][11:16] for r in rows2[-50:]]},
                "series": [{"name": "湿度", "type": "line", "smooth": True, "data": [r[1] for r in rows2[-50:]]}]})
        except: pass

    return {
        "chart_type": resolved,
        "keyword": chart_type,
        "kimi_used": chart_type != "auto" and _match_chart_type(chart_type) is None,
        "days": days,
        "charts": charts,
    }

'''
    # Insert before _db() function
    code = code.replace("\ndef _db():\n", chart_method + "\ndef _db():\n", 1)
    print("CHART_METHOD_ADDED")
else:
    print("CHART_METHOD_EXISTS")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(code)

# Verify
checks = {
    "kimi_config": "kimi" in code and "moonshot" in code,
    "chart_route": "/api/log/chart" in code,
    "generate_chart": "_generate_chart" in code,
    "kimi_match": "_kimi_chart_match" in code,
    "keyword_map": "_CHART_KEYWORD_MAP" in code,
}
ok = sum(1 for v in checks.values() if v)
print(f"PATCHED: {ok}/{len(checks)} checks passed")
for k, v in checks.items():
    print(f"  {k}: {'OK' if v else 'FAIL'}")
