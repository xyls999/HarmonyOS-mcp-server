#!/usr/bin/env python3
"""A9 AI意图引擎v2 全接口测试"""
import urllib.request, json, sys, time, sqlite3
sys.path.insert(0, '/data/A9/smart_home')
from gm_crypto import SecureEnvelope, SM2KeyPair

BASE = 'http://127.0.0.1:8080'
passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        result = fn()
        if isinstance(result, dict) and result.get('error') and not result.get('ok') and not result.get('success') and not result.get('intent') and not result.get('total_watts') is not None:
            print(f'  FAIL {name}: {str(result.get("error",""))[:60]}')
            failed += 1
        else:
            print(f'  PASS {name}')
            passed += 1
    except Exception as e:
        print(f'  FAIL {name}: {str(e)[:80]}')
        failed += 1

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.loads(r.read().decode())

def get_auth(path, headers):
    req = urllib.request.Request(BASE + path, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())

def post(path, data, headers=None):
    hdrs = {'Content-Type': 'application/json'}
    if headers:
        hdrs.update(headers)
    body = json.dumps(data).encode() if data else b'{}'
    req = urllib.request.Request(BASE + path, data=body, headers=hdrs, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

# === 基础 ===
print('--- 基础接口 ---')
test('1. /health', lambda: get('/health'))
test('2. /api/auth/public-key', lambda: get('/api/auth/public-key'))

# === 认证 ===
print('--- 认证 ---')
conn = sqlite3.connect('/data/A9/smart_home/keys/api_keys.db')
api_key = conn.execute("SELECT api_key FROM api_keys WHERE key_id='admin_001'").fetchone()[0]
conn.close()
token_data = post('/api/auth/token', {'api_key': api_key})
token = token_data.get('token', '')
auth = {'Authorization': 'Bearer ' + token}
test('3. /api/auth/token', lambda: token_data)

# === 原有接口回归 ===
print('--- 原有接口回归 ---')
test('4. /api/devices', lambda: get_auth('/api/devices', auth))
test('5. /api/sensors', lambda: get_auth('/api/sensors', auth))
test('6. /api/stats', lambda: get_auth('/api/stats', auth))

# === AI 意图接口(原有) ===
print('--- AI 意图接口(原有) ---')
r7 = post('/api/ai/intent', {'message': '我要睡觉了'})
test('7. intent - 睡觉', lambda: r7)
r8 = post('/api/ai/intent', {'message': '开客厅灯'})
test('8. intent - 开灯', lambda: r8)
r9 = post('/api/ai/intent', {'message': '空调26度'})
test('9. intent - 空调26度', lambda: r9)
r10 = post('/api/ai/intent', {'message': '有点暗'})
test('10. intent - 有点暗', lambda: r10)
test('11. /api/ai/capabilities', lambda: get_auth('/api/ai/capabilities', auth))
test('12. /api/ai/anomaly', lambda: get_auth('/api/ai/anomaly', auth))
test('13. /api/ai/recommendations', lambda: get_auth('/api/ai/recommendations', auth))
test('14. /api/ai/habit/stats', lambda: get_auth('/api/ai/habit/stats', auth))

# === 对话接口 ===
print('--- 对话接口 ---')
r15 = post('/api/chat/send', {'message': '我要睡觉了'})
test('15. chat - 睡觉意图', lambda: r15)
print(f'    source={r15.get("source")} reply={r15.get("reply","")[:40]}')
r16 = post('/api/chat/send', {'message': '开客厅灯'})
test('16. chat - 开灯意图', lambda: r16)
print(f'    source={r16.get("source")} reply={r16.get("reply","")[:40]}')

# === 新增: 节能顾问 ===
print('--- 节能顾问 ---')
test('17. /api/ai/energy', lambda: get_auth('/api/ai/energy', auth))
test('18. /api/ai/energy/waste', lambda: get_auth('/api/ai/energy/waste', auth))
test('19. /api/ai/energy/report', lambda: get_auth('/api/ai/energy/report', auth))

# === 新增: 联动引擎 ===
print('--- 联动引擎 ---')
test('20. /api/ai/linkage/rules', lambda: get_auth('/api/ai/linkage/rules', auth))
test('21. /api/ai/linkage/log', lambda: get_auth('/api/ai/linkage/log', auth))

# === 新增: 情感分析 ===
print('--- 情感分析 ---')
r22 = post('/api/ai/emotion', {'message': '好热啊，烦死了'})
test('22. emotion - 负面', lambda: r22)
print(f'    emotion={r22.get("emotion")} urgency={r22.get("urgency")}')
r23 = post('/api/ai/emotion', {'message': '好舒服啊'})
test('23. emotion - 正面', lambda: r23)
print(f'    emotion={r23.get("emotion")} valence={r23.get("valence")}')
r24 = post('/api/ai/emotion', {'message': '着火了！救命！'})
test('24. emotion - 紧急', lambda: r24)
print(f'    emotion={r24.get("emotion")} urgency={r24.get("urgency")}')

# === 新增: 对话记忆 ===
print('--- 对话记忆 ---')
test('25. /api/ai/context', lambda: get_auth('/api/ai/context', auth))
# 测试指代消解
r26 = post('/api/chat/send', {'message': '开客厅灯'})
test('26. chat - 开灯(建立上下文)', lambda: r26)
r27 = post('/api/chat/send', {'message': '把它关了'})
test('27. chat - 指代消解(把它关了)', lambda: r27)
print(f'    source={r27.get("source")} context_resolved={r27.get("context_resolved")}')
# 清空记忆
test('28. /api/ai/context/clear', lambda: post('/api/ai/context/clear', {}, auth))

# === 新增: 设备注册 ===
print('--- 设备注册 ---')
test('29. /api/ai/devices', lambda: get_auth('/api/ai/devices', auth))
# 注册一个测试设备
r30 = post('/api/ai/device/register', {
    "id": "humidifier_01",
    "name": "智能加湿器",
    "type": "custom",
    "room": "卧室",
    "aliases": ["加湿器", "智能加湿器"],
    "capabilities": [
        {"action": "toggle", "params": {"isOn": "bool"}, "desc": "开关加湿器"},
        {"action": "set_humidity", "params": {"value": "30-80"}, "desc": "设置目标湿度"},
    ],
    "energy_watts": 35,
}, headers=auth)
test('30. register humidifier', lambda: r30)
print(f'    result={r30}')
# 验证注册后能被意图识别
r31 = post('/api/ai/intent', {'message': '开加湿器'})
test('31. intent - 开加湿器(新设备)', lambda: r31)
print(f'    intent={r31.get("intent",{}).get("type")} device={r31.get("intent",{}).get("device_id")}')
# 注销测试设备
r32 = post('/api/ai/device/unregister', {'device_id': 'humidifier_01'}, headers=auth)
test('32. unregister humidifier', lambda: r32)

# === 新增: 节能查询意图 ===
print('--- 节能查询意图 ---')
r33 = post('/api/ai/intent', {'message': '能耗多少'})
test('33. intent - 能耗查询', lambda: r33)
print(f'    type={r33.get("intent",{}).get("type")} query={r33.get("intent",{}).get("query_type")}')

# === 加密通道(回归) ===
print('--- 加密通道(回归) ---')
sm4_key = bytes.fromhex(open('/data/A9/smart_home/keys/sm4_transport.key').read().strip())
sm2_kp_d = int(open('/data/A9/smart_home/keys/sm2_device.key').read().strip(), 16)
sm2_kp = SM2KeyPair(private_key=sm2_kp_d)
env = SecureEnvelope(sm4_key, sm2_kp)

def secure_call(action, params):
    sealed = env.seal({'action': action, 'params': params})
    body = json.dumps(sealed).encode()
    req = urllib.request.Request(BASE + '/api/secure/call', data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read().decode())
    return env.unseal(resp)

test('34. secure ai.intent', lambda: secure_call('ai.intent', {'message': '开卧室灯'}))
test('35. secure ai.capabilities', lambda: secure_call('ai.capabilities', {}))
test('36. secure ai.energy', lambda: secure_call('ai.energy', {}))
test('37. secure ai.linkage', lambda: secure_call('ai.linkage', {}))
test('38. secure device.list', lambda: secure_call('device.list', {}))

# === 结果 ===
print()
print('=' * 50)
print(f'总计: {passed + failed} 项 | PASS: {passed} | FAIL: {failed}')
print('=' * 50)
