# A9 智慧家居 · 远程服务端安全 API 接口文档

> **版本**: 6.0.0  
> **设备**: HarmonyOS A9 (192.168.1.81)  
> **加密**: 国密双层 (SM2 + SM3 + SM4)  
> **日期**: 2026-07-14  
> **网关**: gateway_v6.py  

---

## 1. 架构概览

### 1.1 双层加密架构

```
远程服务器
    │
    │  HTTPS (TLS 1.3 传输层)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  A9 网关 (gateway_v6.py :8080)                  │
│                                                   │
│  ┌─────────────────────────────────────────┐     │
│  │  传输层加密 (SM4-CBC)                    │     │
│  │  · 整个 HTTP Body 用 SM4-CBC 加密       │     │
│  │  · 防窃听、防篡改                       │     │
│  │  · 16字节IV前缀 + PKCS7填充             │     │
│  │  ┌─────────────────────────────────┐   │     │
│  │  │  应用层加密 (SM2签名 + SM3摘要)   │   │     │
│  │  │  · SM2-256 签名验证身份          │   │     │
│  │  │  · SM3 消息摘要防篡改            │   │     │
│  │  │  · 时间戳 + Nonce 防重放         │   │     │
│  │  │  · 业务数据 (JSON)               │   │     │
│  │  └─────────────────────────────────┘   │     │
│  └─────────────────────────────────────────┘     │
│                                                   │
│  ──→ 硬件控制 (hardware_bridge.py)               │
│  ──→ 安全护栏 (safety_shield.py)                 │
│  ──→ AI 对话 (DeepSeek/Astron/讯飞)              │
│  ──→ TTS 语音 (channel.py)                       │
│  ──→ 数据推送 (data_pusher.py → yuanzhe.tech)    │
│  ──→ MCP Server (mcp_server_enhanced.py)         │
└─────────────────────────────────────────────────┘
    │
    │  TCP :8000 (局域网)
    │
    ▼
┌──────────┬──────────┬──────────┬──────────┐
│ 客厅      │ 厨房     │ 卫生间    │ 卧室     │
│ Hi3861   │ H3863   │ H3863    │ H3863   │
│ .62:8000 │ .23:8000│ .63:8000 │ .64:8000│
└──────────┴──────────┴──────────┴──────────┘
```

### 1.2 加密算法说明

| 层级 | 算法 | 标准 | 用途 | 密钥长度 |
|------|------|------|------|----------|
| 传输层 | SM4-CBC | GB/T 32907-2016 | 加密整个通信Body | 128位 (16字节) |
| 应用层 | SM2 | GM/T 0003-2012 | 数字签名/身份认证 | 256位 (32字节私钥) |
| 应用层 | SM3 | GB/T 32950-2016 | 消息摘要/Token签名 | 256位输出 |
| Token | SM3-HMAC | - | Token签发与验证 | 256位密钥 |

---

## 2. 认证系统

### 2.1 认证方式

| 方式 | Header | 适用场景 | 权限 |
|------|--------|----------|------|
| Bearer Token | `Authorization: Bearer <token>` | 日常调用 | 由Token签发时决定 |
| API Key | `X-API-Key: <key>` | 服务端对接 | 由Key配置决定 |
| 本地免认证 | (自动, 192.168.1.x) | 局域网内 | read,write,admin,remote |

### 2.2 权限等级

| 权限 | 说明 | 可访问接口 |
|------|------|-----------|
| `read` | 只读 | GET 状态/传感器/设备列表 |
| `write` | 读写 | + POST 设备控制/场景/AI对话 |
| `admin` | 管理 | + API Key管理/密钥轮换/安全审计 |
| `remote` | 远程 | 加密通信 /api/secure/call |

### 2.3 获取 Token

```
POST /api/auth/token
Content-Type: application/json

{
    "api_key": "sm_xxxxxxxx..."
}

→ 200 OK
{
    "token": "eyJ1aWQiOiJhZG1pbl8wMDEiLCJleHAiOjE3MDAw...",
    "expires_in": 86400,
    "permissions": ["read", "write", "admin", "remote"],
    "key_id": "admin_001"
}
```

Token 有效期: 管理员 24h / 写权限 8h / 只读 1h

### 2.4 刷新 Token

```
POST /api/auth/refresh
Authorization: Bearer <token>

→ 200 OK
{
    "token": "<new_token>",
    "expires_in": 3600
}
```

### 2.5 获取设备公钥

```
GET /api/auth/public-key

→ 200 OK
{
    "device_id": "harmony_a9",
    "sm2_public_key": "04xxyy...",     // 65字节未压缩公钥(hex)
    "sm4_key_fingerprint": "a1b2c3d4e5f6g7h8",  // SM4密钥SM3指纹(前16字符)
    "supported_algorithms": ["SM3", "SM4-CBC", "SM2"],
    "envelope_version": 1
}
```

---

## 3. 加密通信协议 (SecureEnvelope)

### 3.1 信封格式

所有 `/api/secure/call` 请求和响应使用以下信封格式:

```json
{
    "version": 1,
    "timestamp": 1700000000,
    "nonce": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "sm4_iv": "f1e2d3c4b5a69788796051423120...",   // 16字节IV (hex)
    "payload": "e8a7b6c5d4f3e2a1b0c9d8...",         // SM4-CBC密文 (hex)
    "signature": "3a2b1c0d9e8f7a6b5c4d3e2f...",     // SM2签名 r||s (hex, 64字节)
    "signer_pubkey": "04xxyyzz..."                   // 签名者SM2公钥 (hex, 65字节)
}
```

### 3.2 封装流程 (发送)

1. **应用层**: 组装内层数据 `{"timestamp": T, "nonce": N, "data": 业务数据}`
2. **应用层**: SM2 签名 (对内层明文签名, 防抵赖)
3. **传输层**: SM4-CBC 加密内层明文 (防窃听)
4. 组装信封, 附加签名和公钥

### 3.3 解封流程 (接收)

1. 检查时间戳 (±300秒有效期)
2. 检查 Nonce (防重放, 缓存10分钟)
3. **传输层**: SM4-CBC 解密得到内层明文
4. **应用层**: SM2 验签 (确认发送方身份)
5. 验证内层 timestamp/nonce 一致性
6. 返回业务数据

### 3.4 远程调用

```
POST /api/secure/call
Content-Type: application/json

<SecureEnvelope>

→ 200 OK
<SecureEnvelope (响应)>
```

### 3.5 支持的 action 列表

| action | 说明 | 参数 |
|--------|------|------|
| `device.toggle` | 开关设备 | `device_id`, `isOn`, `doorPassword` |
| `device.control` | 控制设备参数 | `device_id`, `action`, `params` |
| `device.list` | 设备列表 | - |
| `device.status` | 单设备状态 | `device_id` |
| `sensor.list` | 传感器列表 | - |
| `sensor.history` | 传感器历史 | - |
| `scene.activate` | 激活场景 | `scene_id` 或 `name` |
| `scene.list` | 场景列表 | - |
| `door.control` | 门禁控制 | `action`, `password` |
| `ac.control` | 空调控制 | `action`, 温度/模式/风速 |
| `status.all` | 全量状态 | - |
| `status.check` | 设备连通检查 | - |
| `chat.send` | AI对话 | `message` 或 `messages` |
| `security.events` | 安全事件 | - |
| `security.stats` | 安全统计 | - |

---

## 4. 完整 API 接口列表

### 4.1 公开接口 (无需认证)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 (含加密状态) |
| GET | `/api/auth/public-key` | 获取设备SM2公钥 |
| POST | `/api/auth/token` | 签发Token |
| POST | `/api/secure/call` | 加密远程调用 |

### 4.2 状态查询接口 (需 `read` 权限)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 设备列表 (含在线/离线状态) |
| GET | `/api/sensors` | 传感器列表 (含实时数据) |
| GET | `/api/cameras` | 摄像头列表 |
| GET | `/api/alerts` | 活跃告警 |
| GET | `/api/user/profile` | 用户信息 |
| GET | `/api/operations?device_id=&days=7` | 操作记录 |
| GET | `/api/sensors/history` | 传感器历史 (最近24h) |
| GET | `/api/server/status` | 服务端状态 (含加密信息) |
| GET | `/api/check` | 设备连通检查 |
| GET | `/api/hardware/status` | 硬件状态 |
| GET | `/api/rag/stats` | RAG知识库统计 |
| GET | `/api/stats` | 10+类统计数据 |
| GET | `/api/security/events` | 安全事件日志 |
| GET | `/api/security/stats` | 安全护栏统计 |
| GET | `/api/security/auth-status` | 鉴权配置状态 |

### 4.3 设备控制接口 (需 `write` 权限)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/devices/{id}/toggle` | 开关设备 |
| POST | `/api/devices/{id}/control` | 控制设备参数 |
| POST | `/api/door/control` | 门禁控制 |
| POST | `/api/security/door-password-verify` | 门禁密码验证 |
| POST | `/api/chat/send` | AI对话 |
| POST | `/api/voice/input` | 语音输入 |
| POST | `/api/user/profile` | 更新用户信息 |
| POST | `/api/rag/search` | RAG搜索 |

### 4.4 远程管理接口 (需 `admin` 权限)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/remote/keys` | 列出所有API Key |
| POST | `/api/remote/keys/create` | 创建API Key |
| POST | `/api/remote/keys/revoke` | 撤销API Key |
| GET | `/api/remote/access-log` | 远程访问日志 |
| GET | `/api/remote/crypto/status` | 加密状态 |
| GET | `/api/remote/crypto/self-test` | 加密模块自检 |
| POST | `/api/remote/crypto/rotate-sm4` | 轮换SM4密钥 |
| POST | `/api/remote/crypto/register-pubkey` | 注册远程服务器公钥 |

---

## 5. 详细接口说明

### 5.1 设备开关

```
POST /api/devices/{device_id}/toggle
Authorization: Bearer <token>
Content-Type: application/json

{
    "isOn": true,                    // true=开, false=关
    "doorPassword": "<DOOR_PASSWORD>" // 门禁操作需密码
}

→ 200 OK
{
    "success": true,
    "data": { ... },
    "error": null
}
```

### 5.2 设备参数控制

```
POST /api/devices/{device_id}/control
Authorization: Bearer <token>

{
    "action": "set_brightness",      // set_brightness / set_speed / set_position / set_temp / set_mode / stop
    "params": {
        "value": 80,                 // 亮度/风速/位置/温度
        "mode": "cool"               // 空调模式: cool/heat/dry/fan
    },
    "doorPassword": "..."           // 门禁操作需密码
}
```

### 5.3 门禁控制

```
POST /api/door/control
Authorization: Bearer <token>

{
    "action": "open",               // open / close / query
    "password": "<DOOR_PASSWORD>"   // open/close 必须提供
}
```

### 5.4 场景激活

通过加密通道:

```json
// /api/secure/call 内层 data
{
    "action": "scene.activate",
    "params": {
        "name": "回家"              // 或 "scene_id": "s1"
    }
}
```

可用场景: 回家(s1) / 离家(s2) / 睡眠(s3) / 观影(s4) / 用餐(s5)

### 5.5 AI 对话

```
POST /api/chat/send
Authorization: Bearer <token>

{
    "message": "客厅温度多少度"
}

→ 200 OK
{
    "reply": "[客厅]\n  温度: 24.5°C\n  湿度: 58%RH",
    "role": "assistant",
    "voiceSequence": [{"text": "...", "audioUrl": "/api/tts/audio/xxx.mp3"}]
}
```

### 5.6 全量统计

```
GET /api/stats
Authorization: Bearer <token>

→ 200 OK
{
    "timestamp": "2026-07-14T12:00:00",
    "version": "v6",
    "device_online_rate": {"total": 10, "online": 8, "offline": 2, "rate": 80.0},
    "area_connectivity": {
        "living_room": {"name": "客厅", "ip": "192.168.1.62", "online": true},
        "kitchen": {"name": "厨房", "ip": "192.168.1.23", "online": true},
        ...
    },
    "living_temperature": {"value": 24.5, "unit": "°C", "online": true},
    "living_humidity": {"value": 58.0, "unit": "%RH", "online": true},
    "kitchen_smoke": {"smoke_alarm": false, "online": true},
    "kitchen_thermal": {"thermal_mv": 1200, "online": true},
    "alarm_linkage": {"last_kitchen_alarm": 0, "udp_listening": true}
}
```

---

## 6. 远程服务器调用示例

### 6.1 Python 调用示例 (推荐)

```python
#!/usr/bin/env python3
"""远程服务器调用 A9 智慧家居示例"""
import json
import requests
from gm_crypto import (
    SecureEnvelope, SM2KeyPair, generate_sm4_key,
    generate_token, sm3_hash
)

# ===== 1. 初始化 =====
A9_HOST = "192.168.1.81"  # 或公网地址
A9_PORT = 8080
BASE_URL = f"http://{A9_HOST}:{A9_PORT}"

# 获取设备公钥
resp = requests.get(f"{BASE_URL}/api/auth/public-key")
pub_info = resp.json()
print(f"设备公钥: {pub_info['sm2_public_key'][:32]}...")

# ===== 2. 认证 =====
# 使用管理员 API Key 获取 Token
API_KEY = "sm_xxxxxxxx..."  # 从 /api/remote/keys 获取
resp = requests.post(f"{BASE_URL}/api/auth/token", json={"api_key": API_KEY})
token_data = resp.json()
TOKEN = token_data["token"]
print(f"Token: {TOKEN[:20]}... (有效期 {token_data['expires_in']}s)")

# ===== 3. 普通调用 (Bearer Token) =====
headers = {"Authorization": f"Bearer {TOKEN}"}

# 查询设备列表
resp = requests.get(f"{BASE_URL}/api/devices", headers=headers)
devices = resp.json()
print(f"设备数量: {len(devices)}")

# 开灯
resp = requests.post(
    f"{BASE_URL}/api/devices/light_01/toggle",
    headers=headers,
    json={"isOn": True}
)
print(f"开灯结果: {resp.json()}")

# ===== 4. 加密调用 (SecureEnvelope) =====
# SM4 密钥: 必须与设备端共享 (通过安全渠道预先交换)
SM4_KEY = bytes.fromhex("...")  # 16字节, 从设备 /data/A9/smart_home/keys/sm4_transport.key 获取

# SM2 密钥对: 远程服务器自己的密钥对
SM2_KEYPAIR = SM2KeyPair()  # 生成或从文件加载

# 注册公钥到设备 (管理员操作)
requests.post(
    f"{BASE_URL}/api/remote/crypto/register-pubkey",
    headers=headers,
    json={"public_key": SM2_KEYPAIR.public_key_hex}
)

# 创建安全信封
envelope = SecureEnvelope(SM4_KEY, SM2_KEYPAIR)

# 加密调用: 开客厅灯
sealed = envelope.seal({
    "action": "device.toggle",
    "params": {"device_id": "light_01", "isOn": True}
})

resp = requests.post(
    f"{BASE_URL}/api/secure/call",
    json=sealed
)

# 解密响应
if resp.status_code == 200:
    result = envelope.unseal(resp.json())
    print(f"加密调用结果: {result}")

# 加密调用: 激活回家场景
sealed = envelope.seal({
    "action": "scene.activate",
    "params": {"name": "回家"}
})
resp = requests.post(f"{BASE_URL}/api/secure/call", json=sealed)
result = envelope.unseal(resp.json())
print(f"场景激活: {result}")

# 加密调用: AI对话
sealed = envelope.seal({
    "action": "chat.send",
    "params": {"message": "把客厅灯调到60%"}
})
resp = requests.post(f"{BASE_URL}/api/secure/call", json=sealed)
result = envelope.unseal(resp.json())
print(f"AI回复: {result}")
```

### 6.2 cURL 调用示例

```bash
# 健康检查
curl http://192.168.1.81:8080/health

# 获取设备公钥
curl http://192.168.1.81:8080/api/auth/public-key

# 获取Token
curl -X POST http://192.168.1.81:8080/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sm_xxxxxxxx..."}'

# 查询设备列表
curl http://192.168.1.81:8080/api/devices \
  -H "Authorization: Bearer <token>"

# 开客厅灯
curl -X POST http://192.168.1.81:8080/api/devices/light_01/toggle \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"isOn": true}'

# 开门 (需密码)
curl -X POST http://192.168.1.81:8080/api/door/control \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "open", "password": "<DOOR_PASSWORD>"}'

# 查询传感器
curl http://192.168.1.81:8080/api/sensors \
  -H "Authorization: Bearer <token>"

# AI对话
curl -X POST http://192.168.1.81:8080/api/chat/send \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "客厅温度多少"}'
```

---

## 7. 密钥管理

### 7.1 密钥文件位置 (A9设备)

| 文件 | 路径 | 说明 |
|------|------|------|
| SM4传输密钥 | `/data/A9/smart_home/keys/sm4_transport.key` | 16字节hex, 设备与远程服务器共享 |
| SM2设备私钥 | `/data/A9/smart_home/keys/sm2_device.key` | 32字节hex, 设备端签名用 |
| SM2远程公钥 | `/data/A9/smart_home/keys/sm2_remote.pub` | 65字节hex, 验证远程服务器签名 |
| Token签名密钥 | `/data/A9/smart_home/keys/token_secret.key` | 32字节hex, Token签发验证 |
| API Key数据库 | `/data/A9/smart_home/keys/api_keys.db` | SQLite, 存储所有API Key |

### 7.2 密钥交换流程

```
远程服务器                          A9 设备
    │                                  │
    │  1. GET /api/auth/public-key     │
    │ ──────────────────────────────→  │
    │  ← {sm2_public_key, sm4_fp}      │
    │                                  │
    │  2. 安全渠道交换 SM4 密钥        │
    │     (如: SSH/VPN/离线传输)       │
    │                                  │
    │  3. POST register-pubkey         │
    │     {public_key: 远程SM2公钥}    │
    │ ──────────────────────────────→  │
    │                                  │
    │  4. POST /api/auth/token         │
    │     {api_key: 管理员Key}         │
    │ ──────────────────────────────→  │
    │  ← {token, permissions}          │
    │                                  │
    │  5. 加密通信就绪                  │
    │     POST /api/secure/call        │
    │ ──────────────────────────────→  │
```

### 7.3 SM4 密钥轮换

```
POST /api/remote/crypto/rotate-sm4
Authorization: Bearer <admin_token>

→ 200 OK
{
    "success": true,
    "old_fingerprint": "a1b2c3d4...",
    "new_fingerprint": "e5f6g7h8...",
    "note": "远程服务器需同步更新SM4密钥"
}
```

⚠️ 轮换后远程服务器必须同步获取新密钥, 否则加密通信将失败。

### 7.4 API Key 管理

```
# 创建新Key
POST /api/remote/keys/create
{
    "name": "手机APP",
    "permissions": "read,write",
    "rate_limit": 100,
    "expires_at": "2026-12-31T23:59:59"
}

# 列出所有Key
GET /api/remote/keys

# 撤销Key
POST /api/remote/keys/revoke
{"key_id": "key_1700000000"}
```

---

## 8. 安全机制汇总

### 8.1 多层安全防护

| 层级 | 机制 | 实现 |
|------|------|------|
| 网络层 | TLS 1.3 | HTTPS (推荐Nginx反代) |
| 传输层 | SM4-CBC 加密 | 整个Body加密, 16字节IV+PKCS7 |
| 应用层 | SM2 数字签名 | 身份认证, 防抵赖 |
| 应用层 | SM3 消息摘要 | 防篡改, Token签名 |
| 协议层 | Nonce 防重放 | 16字节随机, 缓存10分钟 |
| 协议层 | 时间戳有效期 | ±300秒 |
| 认证层 | Bearer Token | SM3签名, 分级有效期 |
| 认证层 | API Key | 分级权限, 频率限制 |
| 业务层 | 安全护栏 | 12+条规则, 正则+频率 |
| 业务层 | 限频保护 | 门禁3s/空调2s/蜂鸣器1s/窗帘3s |
| 业务层 | 门禁密码 | PBKDF2-SHA256, 120000轮 |
| 边缘层 | 边缘鉴权 | nonce+auth_tag, 重放检查 |
| 边缘层 | CRC校验 | 二进制包CRC16 |

### 8.2 安全护栏规则

| 类别 | 严重度 | 规则数 | 示例 |
|------|--------|--------|------|
| shell | Critical | 6 | rm -rf, 反弹Shell, 提权, 数据外泄 |
| prompt | Critical | 1 | Prompt注入 (ignore previous, jailbreak) |
| shell | High | 3 | 系统命令, 网络扫描, 禁用安全控制 |
| sql | High | 1 | DROP DATABASE, TRUNCATE |
| prompt | Medium | 1 | 敏感信息查询 |
| device | High | 动态 | 设备操作频率超限 |

### 8.3 加密自检

```
GET /api/remote/crypto/self-test
Authorization: Bearer <admin_token>

→ 200 OK
{
    "sm3": true,
    "sm4_block": true,
    "sm4_cbc": true,
    "sm2_sign_verify": true,
    "envelope": true,
    "token": true
}
```

---

## 9. 设备ID对照表

| 设备ID | 名称 | 类型 | 房间 | 边缘板 | 操作 |
|--------|------|------|------|--------|------|
| `light_01` | 客厅主灯 | light | 客厅 | Hi3861 .62 | toggle, set_brightness |
| `light_05` | 客厅氛围灯 | light | 客厅 | Hi3861 .62 | toggle, set_brightness |
| `ac_01` | 客厅空调 | ac | 客厅 | Hi3861 .62 | toggle, set_temp, set_mode, set_fan, set_swing |
| `door_01` | 客厅大门 | door | 客厅 | Hi3861 .62 | toggle (需密码) |
| `alarm_01` | 蜂鸣警报 | alarm | 客厅 | Hi3861 .62 | toggle |
| `light_02` | 厨房灯 | light | 厨房 | H3863 .23 | toggle, set_brightness |
| `light_04` | 卫生间灯 | light | 卫生间 | H3863 .63 | toggle, set_brightness |
| `fan_02` | 换气扇 | fan | 卫生间 | H3863 .63 | toggle, set_speed |
| `light_03` | 卧室灯 | light | 卧室 | H3863 .64 | toggle, set_brightness |
| `curtain_01` | 智能窗帘 | curtain | 卧室 | H3863 .64 | toggle, set_position, stop |

### 传感器ID对照表

| 传感器ID | 名称 | 类型 | 房间 | 单位 |
|----------|------|------|------|------|
| `temp_01` | 客厅温度 | temperature | 客厅 | °C |
| `humid_01` | 客厅湿度 | humidity | 客厅 | %RH |
| `smoke_01` | 烟雾检测 | smoke | 厨房 | 正常/报警 |
| `heat_01` | 热敏火灾 | heat | 厨房 | mV |
| `air_01` | 综合报警 | air_quality | 厨房 | 0/1 |

---

## 10. 厨房报警联动

联动规则 (自动运行, 无需远程触发):

1. 中控每1秒查询厨房状态 + 监听 UDP 8001
2. `alarm` 从 0→1 (上升沿): 自动向客厅发送 `BEEP ALARM`
3. `alarm` 从 1→0 (下降沿): 自动发送 `BEEP OFF`
4. 同一持续报警不重复触发蜂鸣器
5. UDP 8001 广播也触发联动

远程服务器可监听 `/api/alerts` 获取实时告警状态。

---

## 11. 错误码

| HTTP状态码 | 错误 | 说明 |
|------------|------|------|
| 200 | - | 成功 |
| 400 | envelope error | 信封解封失败 (签名/解密/过期/重放) |
| 401 | auth required | 需要认证 |
| 403 | permission denied | 权限不足或密码错误 |
| 404 | nf | 接口不存在 |
| 500 | internal error | 内部错误 |

业务层错误 (在200响应体中):

| 字段 | 说明 |
|------|------|
| `success: false` | 操作失败 |
| `error` | 错误描述 |
| `authFailed: true` | 鉴权/限频类失败 (门禁密码/操作限频) |

---

## 12. 部署说明

### 12.1 启动网关

```bash
# 在 A9 设备上
export PATH=/data/A9/bin:/data/A9/python-portable/usr/bin:$PATH
cd /data/A9/smart_home
python3 gateway_v6.py
```

### 12.2 首次运行

首次运行会自动:
1. 初始化数据库 (`smart_home.db`)
2. 生成 SM4 传输密钥
3. 生成 SM2 设备密钥对
4. 生成 Token 签名密钥
5. 创建管理员 API Key (打印到日志)

### 12.3 获取管理员 API Key

首次运行后, 从日志获取管理员 Key:
```bash
cat /data/A9/gateway_v6.log | grep "管理员 API Key"
```

或查询数据库:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('keys/api_keys.db')
row = conn.execute(\"SELECT api_key FROM api_keys WHERE key_id='admin_001'\").fetchone()
print(row[0] if row else 'NOT FOUND')
"
```

### 12.4 Nginx 反代 (推荐, 加 TLS)

```nginx
server {
    listen 443 ssl http2;
    server_name smart-home.example.com;

    ssl_certificate     /etc/ssl/certs/smart-home.pem;
    ssl_certificate_key /etc/ssl/private/smart-home.key;
    ssl_protocols TLSv1.3;

    location / {
        proxy_pass http://192.168.1.81:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 13. 与 v5 的兼容性

- v6 完全兼容 v5 的所有本地接口
- 局域网内 (192.168.1.x) 访问免认证, 行为与 v5 一致
- 新增的认证和加密只在远程访问时生效
- `gateway_v5.py` 可继续运行, v6 是增量升级
