#!/usr/bin/env python3
"""A9 智慧家居 gateway_v6 + AI意图 全接口测试"""
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
        if isinstance(result, dict) and result.get('error') and not result.get('ok') and not result.get('success') and not result.get('intent'):
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

# === 基础接口 ===
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

# === 状态查询 ===
print('--- 状态查询 ---')
test('4. /api/devices', lambda: get_auth('/api/devices', auth))
test('5. /api/sensors', lambda: get_auth('/api/sensors', auth))
test('6. /api/stats', lambda: get_auth('/api/stats', auth))

# === AI 智能意图接口 ===
print('--- AI 智能意图接口 ---')

# 意图解析(不执行)
r7 = post('/api/ai/intent', {'message': '我要睡觉了'})
test('7. intent - 睡觉', lambda: r7)
r8 = post('/api/ai/intent', {'message': '开客厅灯'})
test('8. intent - 开灯', lambda: r8)
r9 = post('/api/ai/intent', {'message': '空调26度'})
test('9. intent - 空调26度', lambda: r9)
r10 = post('/api/ai/intent', {'message': '有点暗'})
test('10. intent - 有点暗', lambda: r10)
r11 = post('/api/ai/intent', {'message': '太热了'})
test('11. intent - 太热了', lambda: r11)
r11b = post('/api/ai/intent', {'message': '我出门了'})
test('11b. intent - 出门', lambda: r11b)

# 意图执行
r12 = post('/api/ai/execute', {'message': '我要睡觉了'})
test('12. execute - 睡觉', lambda: r12)

# 设备能力
test('13. /api/ai/capabilities', lambda: get_auth('/api/ai/capabilities', auth))

# 异常事件
test('14. /api/ai/anomaly', lambda: get_auth('/api/ai/anomaly', auth))

# 推荐
test('15. /api/ai/recommendations', lambda: get_auth('/api/ai/recommendations', auth))

# 习惯统计
test('16. /api/ai/habit/stats', lambda: get_auth('/api/ai/habit/stats', auth))

# === 对话接口(意图引擎集成) ===
print('--- 对话接口(意图引擎) ---')
r17 = post('/api/chat/send', {'message': '我要睡觉了'})
test('17. chat - 睡觉意图', lambda: r17)
print(f'    source={r17.get("source")} reply={r17.get("reply","")[:40]}')

r18 = post('/api/chat/send', {'message': '开客厅灯'})
test('18. chat - 开灯意图', lambda: r18)
print(f'    source={r18.get("source")} reply={r18.get("reply","")[:40]}')

r19 = post('/api/chat/send', {'message': '温度多少'})
test('19. chat - 温度查询', lambda: r19)
print(f'    source={r19.get("source")} reply={r19.get("reply","")[:40]}')

# === 加密通道意图 ===
print('--- 加密通道意图 ---')
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

test('20. secure ai.intent', lambda: secure_call('ai.intent', {'message': '开卧室灯'}))
test('21. secure ai.capabilities', lambda: secure_call('ai.capabilities', {}))
test('22. secure ai.anomaly', lambda: secure_call('ai.anomaly', {}))
test('23. secure ai.recommendations', lambda: secure_call('ai.recommendations', {}))

# === 原有加密通道(回归) ===
print('--- 原有加密通道(回归) ---')
test('24. secure device.list', lambda: secure_call('device.list', {}))
test('25. secure sensor.list', lambda: secure_call('sensor.list', {}))
test('26. secure status.all', lambda: secure_call('status.all', {}))
test('27. secure scene.list', lambda: secure_call('scene.list', {}))

# === 安全防护(回归) ===
print('--- 安全防护(回归) ---')
sealed = env.seal({'action': 'device.list', 'params': {}})
body = json.dumps(sealed).encode()
req = urllib.request.Request(BASE + '/api/secure/call', data=body, headers={'Content-Type': 'application/json'}, method='POST')
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        pass
except:
    pass
# Replay same envelope
req2 = urllib.request.Request(BASE + '/api/secure/call', data=body, headers={'Content-Type': 'application/json'}, method='POST')
try:
    with urllib.request.urlopen(req2, timeout=10) as r:
        code2 = 200
except urllib.error.HTTPError as e:
    code2 = e.code
if code2 == 400:
    print(f'  PASS 28. nonce replay blocked (HTTP {code2})')
    passed += 1
else:
    print(f'  FAIL 28. nonce replay NOT blocked (HTTP {code2})')
    failed += 1

# === 结果 ===
print()
print('=' * 50)
print(f'总计: {passed + failed} 项 | PASS: {passed} | FAIL: {failed}')
print('=' * 50)
