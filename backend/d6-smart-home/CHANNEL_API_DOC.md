# 网络通道接口文档 · WebSocket 长连接

> 版本: 1.0.0  
> 设备端: HarmonyOS A9 (192.168.1.81)  
> 服务端: yuanzhe.tech  
> 更新日期: 2026-07-08

---

## 1. 概述

A9 设备通过 **WebSocket 长连接** 主动连接 yuanzhe.tech，建立双向实时通道。

- **设备→云端**: 自动上报数据快照、心跳、指令执行结果
- **云端→设备**: 远程下发指令(开关设备/激活场景/查询状态/对话)
- **断线自动重连**: 指数退避 (2s → 4s → 8s → ... → 60s)
- **心跳保活**: 每 30 秒一次

---

## 2. 连接建立

### 设备端连接

```
ws://yuanzhe.tech/ws/smart-home
```

> 注意: 当前设备 HTTPS 443 不通，使用 ws:// (HTTP 80)。  
> 如需 wss://，需确保 yuanzhe.tech 443 端口开放。

### 可选认证

连接时携带 Authorization 头:
```
Authorization: Bearer <WS_TOKEN>
```

### 服务端需要做的

1. 在 `yuanzhe.tech` 上部署 WebSocket 服务端，监听路径 `/ws/smart-home`
2. 接受 WebSocket 升级请求
3. 按 `deviceId` 区分不同设备连接
4. 解析设备发来的 JSON 消息，下发指令

---

## 3. 消息格式

所有消息均为 **JSON 文本帧**，包含 `type` 字段区分类型。

### 3.1 设备→云端 消息

#### 注册 (register)

连接建立后立即发送:

```json
{
  "type": "register",
  "deviceId": "harmony_a9",
  "version": "1.0.0",
  "timestamp": "2026-07-08T10:00:00",
  "capabilities": [
    "get_status", "get_devices", "get_sensors", "get_scenes",
    "toggle_device", "control_device", "activate_scene",
    "get_operations", "get_chat_history", "send_chat", "ping"
  ],
  "info": {
    "host": "192.168.1.81",
    "port": 8080,
    "deviceCount": 16,
    "sensorCount": 9,
    "sceneCount": 5,
    "python": "3.14.5"
  }
}
```

#### 全量快照 (snapshot)

连接后立即发送一次，之后每 5 分钟自动发送，也可按需请求:

```json
{
  "type": "snapshot",
  "deviceId": "harmony_a9",
  "timestamp": "2026-07-08T10:00:00",
  "timestampMs": 1720423200000,
  "data": {
    "devices": [ ... ],
    "sensors": [ ... ],
    "scenes": [ ... ],
    "operations": [ ... ],
    "chatHistory": [ ... ],
    "user": { ... },
    "serverStatus": { ... }
  }
}
```

> `data` 内各字段结构同 PUSH_API_DOC.md 中的定义

#### 心跳 (heartbeat)

每 30 秒发送:

```json
{
  "type": "heartbeat",
  "timestamp": "2026-07-08T10:00:30"
}
```

#### 指令响应 (command result)

云端下发指令后，设备返回执行结果:

```json
{
  "msgId": 123,
  "success": true,
  "data": { ... }
}
```

或失败:

```json
{
  "msgId": 123,
  "success": false,
  "error": "设备不存在"
}
```

#### Pong

```json
{
  "type": "pong",
  "timestamp": "2026-07-08T10:00:30"
}
```

---

### 3.2 云端→设备 指令

所有指令包含 `type: "command"` 和 `msgId` (用于匹配响应)。

#### Ping (测试连通)

```json
{
  "type": "ping",
  "msgId": 1
}
```

响应:
```json
{
  "msgId": 1,
  "success": true,
  "data": { "pong": true, "time": "2026-07-08T10:00:00" }
}
```

#### 请求全量快照

```json
{
  "type": "get_snapshot"
}
```

设备会立即发送一个 `type: "snapshot"` 消息。

#### 获取设备列表

```json
{
  "type": "command",
  "action": "get_devices",
  "msgId": 2
}
```

响应:
```json
{
  "msgId": 2,
  "success": true,
  "data": [
    {"id": "light_01", "name": "客厅主灯", "type": "light", "isOn": true, "primaryValue": 80, ...},
    ...
  ]
}
```

#### 开关设备

```json
{
  "type": "command",
  "action": "toggle_device",
  "msgId": 3,
  "deviceId": "light_01",
  "isOn": false
}
```

响应:
```json
{
  "msgId": 3,
  "success": true,
  "data": {
    "id": "light_01", "name": "客厅主灯", "type": "light",
    "room": "客厅", "primaryValue": 80, "isOn": false
  }
}
```

#### 控制设备参数

```json
{
  "type": "command",
  "action": "control_device",
  "msgId": 4,
  "deviceId": "ac_01",
  "subAction": "set_temp",
  "params": { "value": 26 }
}
```

`subAction` 可选值:
- `set_temp` — 设置温度 (params: `{value: 26}`)
- `set_speed` — 设置风速 (params: `{value: 3}`)
- `set_brightness` — 设置亮度 (params: `{value: 60}`)
- `set_mode` — 设置模式 (params: `{mode: "制冷"}`)

#### 激活场景

```json
{
  "type": "command",
  "action": "activate_scene",
  "msgId": 5,
  "sceneId": "s1"
}
```

响应:
```json
{
  "msgId": 5,
  "success": true,
  "data": { "sceneName": "回家", "affectedCount": 4 }
}
```

场景ID对照:
| sceneId | 名称 | 控制设备数 |
|---------|------|-----------|
| s1 | 回家 | 4 |
| s2 | 离家 | 12 |
| s3 | 睡眠 | 7 |
| s4 | 观影 | 4 |
| s5 | 用餐 | 3 |

#### 获取传感器

```json
{
  "type": "command",
  "action": "get_sensors",
  "msgId": 6
}
```

#### 获取场景

```json
{
  "type": "command",
  "action": "get_scenes",
  "msgId": 7
}
```

#### 获取操作记录

```json
{
  "type": "command",
  "action": "get_operations",
  "msgId": 8,
  "limit": 50
}
```

#### 获取对话历史

```json
{
  "type": "command",
  "action": "get_chat_history",
  "msgId": 9,
  "limit": 50
}
```

#### 发送对话 (AI对话)

```json
{
  "type": "command",
  "action": "send_chat",
  "msgId": 10,
  "content": "打开客厅灯"
}
```

响应:
```json
{
  "msgId": 10,
  "success": true,
  "data": {
    "reply": "已切换到「回家」模式，控制 4 台设备",
    "sceneId": "s1"
  }
}
```

---

## 4. 服务端实现示例 (Node.js)

```javascript
const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 80, path: '/ws/smart-home' });
const devices = new Map(); // deviceId → ws

wss.on('connection', (ws, req) => {
  console.log('新连接:', req.socket.remoteAddress);
  let deviceId = null;

  ws.on('message', (raw) => {
    const msg = JSON.parse(raw);

    switch (msg.type) {
      case 'register':
        deviceId = msg.deviceId;
        devices.set(deviceId, ws);
        console.log(`设备注册: ${deviceId}`, msg.info);
        break;

      case 'snapshot':
        // 存储全量快照到数据库
        db.saveSnapshot(msg.deviceId, msg.data);
        console.log(`快照: ${msg.deviceId}, devices=${msg.data.devices?.length}`);
        break;

      case 'heartbeat':
        // 心跳，忽略或更新 last_seen
        db.updateLastSeen(deviceId);
        break;

      default:
        // 指令响应
        if (msg.msgId) {
          handleResponse(msg);
        }
    }
  });

  ws.on('close', () => {
    if (deviceId) devices.delete(deviceId);
    console.log(`断开: ${deviceId}`);
  });

  ws.on('error', (err) => {
    console.error(`错误: ${deviceId}`, err.message);
  });
});

// ===== 远程控制 API (给前端/其他服务调用) =====

app.post('/api/remote/toggle', (req, res) => {
  const { deviceId: did, isOn } = req.body;
  const ws = devices.get('harmony_a9');
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return res.status(503).json({ error: '设备不在线' });
  }
  const msgId = Date.now();
  ws.send(JSON.stringify({
    type: 'command', action: 'toggle_device',
    msgId, deviceId: did, isOn
  }));
  // 等待设备响应...
  res.json({ ok: true, msgId });
});

app.post('/api/remote/scene', (req, res) => {
  const { sceneId } = req.body;
  const ws = devices.get('harmony_a9');
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return res.status(503).json({ error: '设备不在线' });
  }
  const msgId = Date.now();
  ws.send(JSON.stringify({
    type: 'command', action: 'activate_scene',
    msgId, sceneId
  }));
  res.json({ ok: true, msgId });
});

console.log('WebSocket 服务启动: ws://0.0.0.0:80/ws/smart-home');
```

---

## 5. 连接生命周期

```
设备端                                    yuanzhe.tech
  │                                           │
  │──── WebSocket 握手 ────────────────────→  │
  │←─── 101 Switching Protocols ──────────→  │
  │                                           │
  │──── register ─────────────────────────→  │  (注册设备信息)
  │──── snapshot (全量) ──────────────────→  │  (初始数据)
  │                                           │
  │←──── command (get_devices) ────────────  │  (云端查询)
  │──── response ────────────────────────→  │  (设备响应)
  │                                           │
  │←──── command (toggle_device) ──────────  │  (远程控制)
  │──── response ────────────────────────→  │  (执行结果)
  │                                           │
  │──── heartbeat ───────────────────────────────────────────→  │  (每30s心跳)
  │──── snapshot ────────────────────────→  │  (每5min快照)
  │                                           │
  │←──── ping ────────────────────────────  │  (云端探测)
  │──── pong ────────────────────────────→  │
  │                                           │
  │  ✗ 连接断开                               │
  │──── 2s后重连 ────────────────────────→  │
  │  ✗ 失败                                   │
  │──── 4s后重连 ────────────────────────→  │
  │  ✓ 成功                                   │
  │──── register + snapshot ──────────────→  │
```

---

## 6. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| WS_URL | `ws://yuanzhe.tech/ws/smart-home` | WebSocket 服务端地址 |
| WS_TOKEN | (空) | Bearer Token 认证 |
| HEARTBEAT_INTERVAL | 30 | 心跳间隔(秒) |

---

## 7. 本地调试 API

通道服务在设备本地 8081 端口提供调试接口:

| 路径 | 说明 |
|------|------|
| `GET http://192.168.1.81:8081/channel/status` | 通道连接状态 |
| `GET http://192.168.1.81:8081/channel/test` | 发送测试 ping |
