#!/usr/bin/env python3
"""A9 智慧家居 gateway_v6 全接口集成测试"""
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
        if isinstance(result, dict) and result.get('error') and not result.get('ok'):
            print(f'  FAIL {name}: {str(result.get("error",""))[:60]}')
            failed += 1
        else:
            print(f'  PASS {name}')
            passed += 1
    except Exception as e:
        print(f'  FAIL {name}: {str(e)[:60]}')
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

def post_raw(path, data_bytes, headers=None):
    hdrs = {'Content-Type': 'application/json'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(BASE + path, data=data_bytes, headers=hdrs, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

# === 公开接口 ===
print('--- 公开接口 ---')
test('1. /health', lambda: get('/health'))
test('2. /api/auth/public-key', lambda: get('/api/auth/public-key'))

# === 认证 ===
print('--- 认证接口 ---')
conn = sqlite3.connect('/data/A9/smart_home/keys/api_keys.db')
api_key = conn.execute("SELECT api_key FROM api_keys WHERE key_id='admin_001'").fetchone()[0]
conn.close()

token_data = post('/api/auth/token', {'api_key': api_key})
token = token_data.get('token', '')
auth = {'Authorization': 'Bearer ' + token}
test('3. /api/auth/token', lambda: token_data)
test('4. /api/auth/refresh', lambda: post('/api/auth/refresh', {}, auth))

# === 状态查询 ===
print('--- 状态查询接口 ---')
test('5. /api/devices', lambda: get('/api/devices'))
test('6. /api/sensors', lambda: get('/api/sensors'))
test('7. /api/cameras', lambda: get('/api/cameras'))
test('8. /api/alerts', lambda: get('/api/alerts'))
test('9. /api/user/profile', lambda: get('/api/user/profile'))
test('10. /api/operations', lambda: get('/api/operations'))
test('11. /api/sensors/history', lambda: get('/api/sensors/history'))
test('12. /api/server/status', lambda: get('/api/server/status'))
test('13. /api/check', lambda: get('/api/check'))
test('14. /api/hardware/status', lambda: get('/api/hardware/status'))
test('15. /api/rag/stats', lambda: get('/api/rag/stats'))
test('16. /api/stats', lambda: get('/api/stats'))
test('17. /api/security/events', lambda: get('/api/security/events'))
test('18. /api/security/stats', lambda: get('/api/security/stats'))
test('19. /api/security/auth-status', lambda: get('/api/security/auth-status'))

# === 设备控制 ===
print('--- 设备控制接口 ---')
test('20. toggle light_01', lambda: post('/api/devices/light_01/toggle', {'isOn': True}, auth))
test('21. control curtain', lambda: post('/api/devices/curtain_01/control', {'action': 'set_position', 'params': {'value': 50}}, auth))
test('22. door query', lambda: post('/api/door/control', {'action': 'query'}, auth))
test('23. door-password-verify', lambda: post('/api/security/door-password-verify', {'password': 'wrong'}, auth))
test('24. user profile update', lambda: post('/api/user/profile', {'nickname': 'test_user'}, auth))
test('25. rag search', lambda: post('/api/rag/search', {'query': 'temperature'}, auth))

# === 远程管理 ===
print('--- 远程管理接口 ---')
test('26. /api/remote/keys', lambda: get_auth('/api/remote/keys', auth))
test('27. create api key', lambda: post('/api/remote/keys/create', {'name': 'test_key', 'permissions': 'read'}, auth))
test('28. /api/remote/crypto/status', lambda: get_auth('/api/remote/crypto/status', auth))
test('29. /api/remote/crypto/self-test', lambda: get_auth('/api/remote/crypto/self-test', auth))
test('30. /api/remote/access-log', lambda: get_auth('/api/remote/access-log', auth))

# === 加密通信 ===
print('--- 加密通信接口 ---')
sm4_key = bytes.fromhex(open('/data/A9/smart_home/keys/sm4_transport.key').read().strip())
sm2_kp = SM2KeyPair(private_key=int(open('/data/A9/smart_home/keys/sm2_device.key').read().strip(), 16))
env = SecureEnvelope(sm4_key, sm2_kp)

def secure_call(action, params):
    sealed = env.seal({'action': action, 'params': params})
    code, r = post_raw('/api/secure/call', json.dumps(sealed).encode())
    if code != 200:
        return r
    return env.unseal(r)

test('31. secure device.list', lambda: secure_call('device.list', {}))
test('32. secure sensor.list', lambda: secure_call('sensor.list', {}))
test('33. secure status.all', lambda: secure_call('status.all', {}))
test('34. secure scene.list', lambda: secure_call('scene.list', {}))
test('35. secure security.stats', lambda: secure_call('security.stats', {}))
test('36. secure device.toggle', lambda: secure_call('device.toggle', {'device_id': 'light_02', 'isOn': False}))
test('37. secure status.check', lambda: secure_call('status.check', {}))
test('38. secure security.events', lambda: secure_call('security.events', {}))

# === 安全防护 ===
print('--- 安全防护验证 ---')

# Nonce重放
sealed = env.seal({'action': 'device.list', 'params': {}})
code1, r1 = post_raw('/api/secure/call', json.dumps(sealed).encode())
code2, r2 = post_raw('/api/secure/call', json.dumps(sealed).encode())
if code2 == 400:
    print(f'  PASS 39. nonce replay blocked (HTTP {code2})')
    passed += 1
else:
    print(f'  FAIL 39. nonce replay NOT blocked (HTTP {code2})')
    failed += 1

# 过期信封
old_sealed = env.seal({'action': 'device.list', 'params': {}})
old_sealed['timestamp'] = old_sealed['timestamp'] - 600
code3, r3 = post_raw('/api/secure/call', json.dumps(old_sealed).encode())
if code3 == 400:
    print(f'  PASS 40. expired envelope blocked (HTTP {code3})')
    passed += 1
else:
    print(f'  FAIL 40. expired envelope NOT blocked (HTTP {code3})')
    failed += 1

# 签名篡改
tampered = env.seal({'action': 'device.list', 'params': {}})
tampered['signature'] = '0' * 128
code4, r4 = post_raw('/api/secure/call', json.dumps(tampered).encode())
if code4 == 400:
    print(f'  PASS 41. tampered signature blocked (HTTP {code4})')
    passed += 1
else:
    print(f'  FAIL 41. tampered signature NOT blocked (HTTP {code4})')
    failed += 1

# === 结果 ===
print()
print('=' * 50)
print(f'总计: {passed + failed} 项 | PASS: {passed} | FAIL: {failed}')
print('=' * 50)
