#!/usr/bin/env python3
"""Patch gateway_v6.py on A9 device - fix log API issues"""
import re

PATH = "/data/A9/smart_home/gateway_v6.py"

with open(PATH, "r", encoding="utf-8") as f:
    code = f.read()

original = code

# 1. Add timezone helpers after "from datetime import datetime"
if "_cst_now" not in code:
    tz_helpers = '''
from datetime import datetime, timezone, timedelta

# ===== 时区: Asia/Shanghai (UTC+8) =====
_CST = timezone(timedelta(hours=8))

def _cst_now():
    """返回 Asia/Shanghai 时区的当前时间"""
    return datetime.now(_CST)

def _cst_today_str():
    """返回 Asia/Shanghai 时区的今日日期字符串 YYYY-MM-DD"""
    return _cst_now().strftime("%Y-%m-%d")

def _cst_now_str():
    """返回 Asia/Shanghai 时区的当前时间字符串 YYYY-MM-DD HH:MM:SS"""
    return _cst_now().strftime("%Y-%m-%d %H:%M:%S")
'''
    code = code.replace("from datetime import datetime", tz_helpers, 1)

# 2. Fix _daily_log_update - replace entire function
old_daily = '''def _daily_log_update():
    """更新今日daily_log汇总（每次请求时调用，节流5分钟）"""
    try:
        conn = _db()
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute("SELECT id FROM daily_log WHERE log_date=?", (today,)).fetchone()
        total_req = conn.execute("SELECT COUNT(*) FROM remote_access_log WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
        total_chat = conn.execute("SELECT COUNT(*) FROM chat_history WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
        total_ops = conn.execute("SELECT COUNT(*) FROM device_operations WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
        total_sec = conn.execute("SELECT COUNT(*) FROM security_events WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
        with _STATUS_LOCK:
            online_peak = sum(1 for s in _DEVICE_STATUS.values() if s.get("online"))
            sensors_active = sum(1 for s in _SENSOR_STATUS.values() if s.get("online"))
        if row:
            conn.execute("UPDATE daily_log SET total_requests=?, total_chat=?, total_device_ops=?, total_security_events=?, devices_online_peak=?, sensors_active=? WHERE log_date=?",
                         (total_req, total_chat, total_ops, total_sec, online_peak, sensors_active, today))
        else:
            conn.execute("INSERT INTO daily_log(log_date,total_requests,total_chat,total_device_ops,total_security_events,devices_online_peak,sensors_active) VALUES(?,?,?,?,?,?,?)",
                         (today, total_req, total_chat, total_ops, total_sec, online_peak, sensors_active))
        conn.commit(); conn.close()
    except Exception:
        pass'''

new_daily = '''def _daily_log_update():
    """更新今日daily_log汇总（每次请求时调用，节流5分钟）"""
    try:
        conn = _db()
        today = _cst_today_str()
        today_prefix = today + "%"
        row = conn.execute("SELECT id FROM daily_log WHERE log_date=?", (today,)).fetchone()
        total_req = conn.execute("SELECT COUNT(*) FROM remote_access_log WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        total_chat = conn.execute("SELECT COUNT(*) FROM chat_history WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        total_ops = conn.execute("SELECT COUNT(*) FROM device_operations WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        total_sec = conn.execute("SELECT COUNT(*) FROM security_events WHERE created_at LIKE ?", (today_prefix,)).fetchone()[0]
        # 峰值追踪：取历史峰值和当前在线的较大值
        with _STATUS_LOCK:
            current_online = sum(1 for s in _DEVICE_STATUS.values() if s.get("online"))
            current_sensors = sum(1 for s in _SENSOR_STATUS.values() if s.get("online"))
        if row:
            prev = conn.execute("SELECT devices_online_peak, sensors_active FROM daily_log WHERE log_date=?", (today,)).fetchone()
            online_peak = max(current_online, prev[0] if prev and prev[0] else 0)
            sensors_active = max(current_sensors, prev[1] if prev and prev[1] else 0)
        else:
            online_peak = current_online
            sensors_active = current_sensors
        if row:
            conn.execute("UPDATE daily_log SET total_requests=?, total_chat=?, total_device_ops=?, total_security_events=?, devices_online_peak=?, sensors_active=? WHERE log_date=?",
                         (total_req, total_chat, total_ops, total_sec, online_peak, sensors_active, today))
        else:
            conn.execute("INSERT INTO daily_log(log_date,total_requests,total_chat,total_device_ops,total_security_events,devices_online_peak,sensors_active) VALUES(?,?,?,?,?,?,?)",
                         (today, total_req, total_chat, total_ops, total_sec, online_peak, sensors_active))
        conn.commit(); conn.close()
    except Exception:
        pass'''

code = code.replace(old_daily, new_daily, 1)

# 3. Fix /api/log/today - use _cst_today_str()
code = code.replace(
    'today = datetime.now().strftime("%Y-%m-%d")\n                    row = conn.execute("SELECT * FROM daily_log WHERE log_date=?", (today,)).fetchone()',
    'today = _cst_today_str()\n                    row = conn.execute("SELECT * FROM daily_log WHERE log_date=?", (today,)).fetchone()',
    1
)

# 4. Replace all datetime('now') in SQL with datetime('now','+8 hours')
code = code.replace("datetime('now')", "datetime('now','+8 hours')")

# 5. Fix /api/operations - add limit parameter
old_ops_route = '''                if auth:
                    qs = self.path.split("?", 1); did = None; days = 7
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                            if k == "device_id": did = v
                            if k == "days": days = int(v)
                    self._j(200, self._get_operations(did, days))'''

new_ops_route = '''                if auth:
                    qs = self.path.split("?", 1); did = None; days = 7; limit = 200
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                            if k == "device_id": did = v
                            if k == "days": days = int(v)
                            if k == "limit": limit = min(int(v), 1000)
                    self._j(200, self._get_operations(did, days, limit))'''

code = code.replace(old_ops_route, new_ops_route, 1)

# 6. Fix _get_operations function
old_get_ops = '''    def _get_operations(self, device_id=None, days=7):
        conn = _db()
        time_filter = f"datetime('now','-{days} days')"
        if device_id:
            total = conn.execute(f"SELECT COUNT(*) FROM device_operations WHERE device_id=? AND created_at>={time_filter}", (device_id,)).fetchone()[0]
            rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE device_id=? AND created_at>={time_filter} ORDER BY created_at DESC LIMIT 200", (device_id,)).fetchall()
        else:
            total = conn.execute(f"SELECT COUNT(*) FROM device_operations WHERE created_at>={time_filter}").fetchone()[0]
            rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE created_at>={time_filter} ORDER BY created_at DESC LIMIT 200").fetchall()
        conn.close()
        return {"operations": [{"device_id": r[0], "action": r[1], "params": r[2], "result": r[3], "source": r[4], "scene_id": r[5], "timestamp": r[6]} for r in rows], "total": total, "limit": 200}'''

new_get_ops = '''    def _get_operations(self, device_id=None, days=7, limit=200):
        conn = _db()
        time_filter = f"datetime('now','+8 hours','-{days} days')"
        if device_id:
            total = conn.execute(f"SELECT COUNT(*) FROM device_operations WHERE device_id=? AND created_at>={time_filter}", (device_id,)).fetchone()[0]
            rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE device_id=? AND created_at>={time_filter} ORDER BY created_at DESC LIMIT ?", (device_id, limit)).fetchall()
        else:
            total = conn.execute(f"SELECT COUNT(*) FROM device_operations WHERE created_at>={time_filter}").fetchone()[0]
            rows = conn.execute(f"SELECT device_id,action,params_json,result,source,scene_id,created_at FROM device_operations WHERE created_at>={time_filter} ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return {"operations": [{"device_id": r[0], "action": r[1], "params": r[2], "result": r[3], "source": r[4], "scene_id": r[5], "timestamp": r[6]} for r in rows], "total": total, "limit": limit}'''

code = code.replace(old_get_ops, new_get_ops, 1)

# 7. Add /api/chat/history route
old_ai_ctx = '''            elif p == "/api/ai/context":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_context_summary()); self._log_remote_access(auth, p)
            elif p == "/api/ai/devices":
                auth = self._require_auth("read")
                if auth: self._j(200, self._list_device_templates()); self._log_remote_access(auth, p)'''

new_ai_ctx = '''            elif p == "/api/ai/context":
                auth = self._require_auth("read")
                if auth: self._j(200, self._get_context_summary()); self._log_remote_access(auth, p)
            elif p == "/api/ai/devices":
                auth = self._require_auth("read")
                if auth: self._j(200, self._list_device_templates()); self._log_remote_access(auth, p)
            elif p == "/api/chat/history":
                auth = self._require_auth("read")
                if auth:
                    qs = self.path.split("?", 1); limit = 50
                    if len(qs) > 1:
                        for kv in qs[1].split("&"):
                            k, v = kv.split("=", 1) if "=" in kv else (kv, "")
                            if k == "limit": limit = min(int(v), 1000)
                    self._j(200, self._get_chat_history(limit))
                    self._log_remote_access(auth, p)'''

code = code.replace(old_ai_ctx, new_ai_ctx, 1)

# 8. Add _get_chat_history method after _get_operations
chat_history_method = '''
    def _get_chat_history(self, limit=50):
        """查询聊天历史，返回分页结果"""
        conn = _db()
        try:
            total = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
            rows = conn.execute(
                "SELECT id, user_id, role, content, intent_json, emotion, source, created_at "
                "FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            messages = []
            for r in rows:
                msg = {
                    "id": r[0],
                    "user_id": r[1],
                    "role": r[2],
                    "content": r[3],
                    "timestamp": r[7],
                }
                if r[4]: msg["intent"] = r[4]
                if r[5]: msg["emotion"] = r[5]
                if r[6]: msg["source"] = r[6]
                # 标记AI上游错误
                if r[2] == "assistant" and r[3] and "暂时不可用" in str(r[3]):
                    msg["error"] = True
                messages.append(msg)
            return {"messages": messages, "total": total, "limit": limit}
        except Exception as e:
            conn.close()
            return {"messages": [], "total": 0, "limit": limit, "error": str(e)}
'''

# Insert after _get_operations return line
ops_return = '        return {"operations": [{"device_id": r[0], "action": r[1], "params": r[2], "result": r[3], "source": r[4], "scene_id": r[5], "timestamp": r[6]} for r in rows], "total": total, "limit": limit}'
code = code.replace(ops_return, ops_return + chat_history_method, 1)

# Write patched file
with open(PATH, "w", encoding="utf-8") as f:
    f.write(code)

# Verify
changes = 0
if "_cst_now" in code: changes += 1
if "_cst_today_str" in code: changes += 1
if "datetime('now','+8 hours')" in code: changes += 1
if "/api/chat/history" in code: changes += 1
if "_get_chat_history" in code: changes += 1
if "limit = 200" in code: changes += 1
print(f"PATCHED: {changes} changes applied to {PATH}")
print(f"File size: {len(code)} bytes, {code.count(chr(10))} lines")
