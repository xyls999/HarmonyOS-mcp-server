# A9 设备端 ↔ yuanzhe.tech 服务端 · 接口对齐文档

> 版本: 2.0.0  
> 设备: HarmonyOS A9 (192.168.1.81)  
> 服务端: yuanzhe.tech  
> 更新日期: 2026-07-08  
> **核心原则: 每个指令必有回应，硬件未接时返回保底消息**

---

## 1. 通信架构

```
A9 设备 (NAT内网)                    yuanzhe.tech (公网)
  │                                       │
  │─── WebSocket 长连接 ──────────────→   │  (设备主动连出，穿透NAT)
  │    ws://yuanzhe.tech/ws/smart-home    │
  │                                       │
  │─── HTTP POST 推送 ────────────────→   │  (定时数据上报)
  │    http://yuanzhe.tech/api/           │
  │        smart-home/data                │
  │                                       │
  │←── WebSocket 下发指令 ────────────    │  (服务端远程控制)
  │    {type:"command", action:...}       │
  │─── WebSocket 返回结果 ────────────→   │
  │    {msgId:N, success:..., data:...}   │
```

---

## 2. WebSocket 通道

### 连接地址

```
ws://yuanzhe.tech/ws/smart-home
```

> ⚠️ 设备 HTTPS 443 不通，必须用 ws:// (HTTP 80)

### 设备注册 (连接后立即发送)

```json
{
  "type": "register",
  "deviceId": "harmony_a9",
  "version": "1.0.0",
  "timestamp": "2026-07-08T10:00:00",
  "capabilities": [
    "ping", "get_status", "get_devices", "get_sensors", "get_scenes",
    "get_user", "get_operations", "get_chat_history", "get_alerts",
    "get_cameras", "get_server_status",
    "toggle_device", "control_device", "add_device", "remove_device",
    "activate_scene", "activate_scene_by_name", "update_user",
    "send_chat", "rag_search"
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

### 心跳 (每30秒)

```json
{"type": "heartbeat", "timestamp": "2026-07-08T10:00:30"}
```

### 快照 (初始+每5分钟)

```json
{
  "type": "snapshot",
  "deviceId": "harmony_a9",
  "timestamp": "2026-07-08T10:00:00",
  "timestampMs": 1720423200000,
  "data": { ... }
}
```

---

## 3. 20个远程指令 · 完整对齐

### 3.1 查询类 (纯软件，始终成功)

#### ping — 连通测试

**请求:**
```json
{"type": "command", "action": "ping", "msgId": 1}
```

**响应:**
```json
{
  "msgId": 1,
  "success": true,
  "data": {"pong": true, "time": "2026-07-08T10:00:00"}
}
```

> ✅ 不依赖数据库，即使DB挂了也能返回成功

---

#### get_status — 全量数据

**请求:**
```json
{"type": "command", "action": "get_status", "msgId": 2}
```

**响应:**
```json
{
  "msgId": 2,
  "success": true,
  "data": {
    "devices": [...],      // 16台设备
    "sensors": [...],      // 9个传感器
    "scenes": [...],       // 5个场景
    "operations": [...],   // 操作记录
    "chatHistory": [...],  // 对话历史
    "user": {...},         // 用户信息
    "serverStatus": {...}  // 服务状态
  }
}
```

---

#### get_devices — 16台设备

**请求:**
```json
{"type": "command", "action": "get_devices", "msgId": 3}
```

**响应:**
```json
{
  "msgId": 3,
  "success": true,
  "data": [
    {"id": "ac_01", "name": "客厅空调", "type": "ac", "status": "active", "room": "客厅", "icon": "air", "primaryValue": 24, "isOn": true, "mode": "制冷", "updatedAt": "..."},
    {"id": "fan_01", "name": "客厅吊扇", "type": "fan", "status": "online", "room": "客厅", "icon": "fan", "primaryValue": 2, "isOn": true, "updatedAt": "..."},
    {"id": "door_01", "name": "客厅大门", "type": "door", "status": "online", "room": "客厅", "icon": "door", "primaryValue": 0, "isOn": true, "updatedAt": "..."},
    {"id": "alarm_01", "name": "蜂鸣警报", "type": "alarm", "status": "online", "room": "客厅", "icon": "alarm", "primaryValue": 0, "isOn": false, "updatedAt": "..."},
    {"id": "light_01", "name": "客厅主灯", "type": "light", "status": "online", "room": "客厅", "icon": "lightbulb", "primaryValue": 80, "isOn": true, "updatedAt": "..."},
    {"id": "light_05", "name": "客厅氛围灯", "type": "light", "status": "online", "room": "客厅", "icon": "lightbulb", "primaryValue": 45, "isOn": false, "updatedAt": "..."},
    {"id": "camera_01", "name": "客厅摄像头", "type": "camera", "status": "online", "room": "客厅", "icon": "camera", "primaryValue": 0, "isOn": true, "updatedAt": "..."},
    {"id": "light_02", "name": "厨房灯", "type": "light", "status": "online", "room": "厨房", "icon": "lightbulb", "primaryValue": 70, "isOn": false, "updatedAt": "..."},
    {"id": "exhaust_01", "name": "抽风机", "type": "fan", "status": "online", "room": "厨房", "icon": "fan", "primaryValue": 1, "isOn": false, "updatedAt": "..."},
    {"id": "curtain_01", "name": "智能窗帘", "type": "curtain", "status": "online", "room": "卧室", "icon": "curtain", "primaryValue": 100, "isOn": true, "updatedAt": "..."},
    {"id": "light_03", "name": "卧室灯", "type": "light", "status": "online", "room": "卧室", "icon": "lightbulb", "primaryValue": 50, "isOn": false, "updatedAt": "..."},
    {"id": "fan_02", "name": "换气扇", "type": "fan", "status": "online", "room": "卫生间", "icon": "fan", "primaryValue": 1, "isOn": false, "updatedAt": "..."},
    {"id": "light_04", "name": "卫生间灯", "type": "light", "status": "online", "room": "卫生间", "icon": "lightbulb", "primaryValue": 60, "isOn": false, "updatedAt": "..."},
    {"id": "nfc_01", "name": "NFC门禁", "type": "nfc", "status": "online", "room": "室外", "icon": "nfc", "primaryValue": 0, "isOn": false, "updatedAt": "..."},
    {"id": "voice_01", "name": "语音中控", "type": "voice", "status": "online", "room": "全局", "icon": "voice", "primaryValue": 0, "isOn": true, "updatedAt": "..."},
    {"id": "radar_01", "name": "毫米波雷达", "type": "radar", "status": "active", "room": "全局", "icon": "radar", "primaryValue": 0, "isOn": true, "updatedAt": "..."}
  ]
}
```

---

#### get_sensors — 9个传感器

**请求:**
```json
{"type": "command", "action": "get_sensors", "msgId": 4}
```

**响应:**
```json
{
  "msgId": 4,
  "success": true,
  "data": [
    {"id": "temp_01", "name": "客厅温度", "type": "temperature", "group": "环境监测", "room": "客厅", "current": {"value": 24.5, "unit": "°C"}, "isAlert": false, "updatedAt": "..."},
    {"id": "humid_01", "name": "客厅湿度", "type": "humidity", "group": "环境监测", "room": "客厅", "current": {"value": 58.0, "unit": "%RH"}, "isAlert": false, "updatedAt": "..."},
    {"id": "light_s_01", "name": "客厅光照", "type": "illuminance", "group": "环境监测", "room": "客厅", "current": {"value": 320.0, "unit": "lx"}, "isAlert": false, "updatedAt": "..."},
    {"id": "air_01", "name": "空气质量", "type": "air_quality", "group": "环境监测", "room": "客厅", "current": {"value": 42.0, "unit": "AQI"}, "isAlert": false, "updatedAt": "..."},
    {"id": "pir_01", "name": "人体感应", "type": "pir", "group": "安防", "room": "客厅", "current": {"value": 1.0, "unit": "有人"}, "isAlert": false, "updatedAt": "..."},
    {"id": "smoke_01", "name": "烟雾检测", "type": "smoke", "group": "安防", "room": "厨房", "current": {"value": 0.0, "unit": "正常"}, "isAlert": false, "updatedAt": "..."},
    {"id": "heat_01", "name": "热敏火灾", "type": "heat", "group": "安防", "room": "厨房", "current": {"value": 36.2, "unit": "°C"}, "isAlert": false, "updatedAt": "..."},
    {"id": "door_s_01", "name": "门窗感应", "type": "door_window", "group": "安防", "room": "室外", "current": {"value": 0.0, "unit": "关闭"}, "isAlert": false, "updatedAt": "..."},
    {"id": "power_01", "name": "总功率", "type": "power", "group": "能耗", "room": "全局", "current": {"value": 1.2, "unit": "kW"}, "isAlert": false, "updatedAt": "..."}
  ]
}
```

---

#### get_scenes — 5个场景

**请求:**
```json
{"type": "command", "action": "get_scenes", "msgId": 5}
```

**响应:**
```json
{
  "msgId": 5,
  "success": true,
  "data": [
    {"id": "s1", "name": "回家", "icon": "house_fill", "color": "#22D3EE", "isActive": true, "description": "回家模式", "actions": [
      {"deviceId": "light_01", "isOn": true, "primaryValue": 80},
      {"deviceId": "ac_01", "isOn": true, "primaryValue": 24},
      {"deviceId": "curtain_01", "isOn": true, "primaryValue": 100},
      {"deviceId": "door_01", "isOn": true}
    ]},
    {"id": "s2", "name": "离家", "icon": "door_sliding", "color": "#F97316", "isActive": false, "description": "离家模式", "actions": [/* 12个设备 */]},
    {"id": "s3", "name": "睡眠", "icon": "bedtime", "color": "#8B5CF6", "isActive": false, "description": "睡眠模式", "actions": [/* 7个设备 */]},
    {"id": "s4", "name": "观影", "icon": "movie", "color": "#EC4899", "isActive": false, "description": "观影模式", "actions": [/* 4个设备 */]},
    {"id": "s5", "name": "用餐", "icon": "restaurant", "color": "#10B981", "isActive": false, "description": "用餐模式", "actions": [/* 3个设备 */]}
  ]
}
```

---

#### get_user — 用户信息

**请求:**
```json
{"type": "command", "action": "get_user", "msgId": 6}
```

**响应:**
```json
{
  "msgId": 6,
  "success": true,
  "data": {"id": "u001", "nickname": "用户", "homeName": "我的家", "memberCount": 3, "avatar": "", "deviceCount": 16}
}
```

---

#### get_operations — 操作记录

**请求:**
```json
{"type": "command", "action": "get_operations", "msgId": 7, "limit": 50}
```

**响应:**
```json
{
  "msgId": 7,
  "success": true,
  "data": [
    {"deviceId": "light_01", "action": "toggle", "params": "{\"isOn\":true}", "result": "ok", "source": "scene", "sceneId": "s1", "timestamp": "..."}
  ]
}
```

---

#### get_chat_history — 对话历史

**请求:**
```json
{"type": "command", "action": "get_chat_history", "msgId": 8, "limit": 50}
```

**响应:**
```json
{
  "msgId": 8,
  "success": true,
  "data": [
    {"userId": "u001", "role": "user", "content": "打开客厅灯", "sceneId": "s1", "timestamp": "..."},
    {"userId": "u001", "role": "assistant", "content": "已切换到「回家」模式", "sceneId": "s1", "timestamp": "..."}
  ]
}
```

---

#### get_alerts — 告警 (模拟数据)

**请求:**
```json
{"type": "command", "action": "get_alerts", "msgId": 9}
```

**响应:**
```json
{
  "msgId": 9,
  "success": true,
  "data": [
    {"id": "a1", "source": "门口摄像头", "content": "门口有人停留，检测到异常移动", "level": "warning", "isRead": false, "timestamp": 1720338420000},
    {"id": "a2", "source": "卧室窗帘", "content": "电量剩余 15%，建议更换电池", "level": "info", "isRead": true, "timestamp": 1720335000000},
    {"id": "a3", "source": "客厅湿度", "content": "当前湿度 72%，建议开启除湿", "level": "info", "isRead": true, "timestamp": 1720327800000}
  ],
  "hardwareOnline": false,
  "message": "告警数据为模拟数据，连通测试成功"
}
```

> ⚠️ `hardwareOnline: false` — 告警数据是硬编码模拟，非真实硬件

---

#### get_cameras — 摄像头 (模拟数据)

**请求:**
```json
{"type": "command", "action": "get_cameras", "msgId": 10}
```

**响应:**
```json
{
  "msgId": 10,
  "success": true,
  "data": [
    {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online", "isRecording": true, "resolution": "1080P"},
    {"id": "cam_02", "name": "门口摄像头", "room": "室外", "status": "online", "isRecording": false, "resolution": "1080P"}
  ],
  "hardwareOnline": false,
  "message": "摄像头数据为模拟数据，连通测试成功"
}
```

> ⚠️ `hardwareOnline: false` — 摄像头数据是硬编码模拟

---

#### get_server_status — 服务状态

**请求:**
```json
{"type": "command", "action": "get_server_status", "msgId": 11}
```

**响应:**
```json
{
  "msgId": 11,
  "success": true,
  "data": {
    "host": "192.168.1.81",
    "port": 8080,
    "isOnline": true,
    "protocol": "wifi",
    "version": "v3",
    "channelVersion": "1.0.0",
    "python": "3.14.5",
    "dbSize": 118784,
    "connectedClients": 1
  }
}
```

> ✅ 不依赖数据库

---

#### rag_search — RAG知识搜索

**请求:**
```json
{"type": "command", "action": "rag_search", "msgId": 12, "query": "空调怎么开", "n_results": 5}
```

**响应:**
```json
{
  "msgId": 12,
  "success": true,
  "data": [
    {"content": "客厅空调可通过语音或场景控制...", "category": "device_control", "score": 0.85}
  ]
}
```

> 45条知识文档，6个分类: scene, device_control, room, bearpi, sensor, faq

---

### 3.2 控制类 (硬件未接入，返回保底)

#### toggle_device — 开关设备

**请求:**
```json
{"type": "command", "action": "toggle_device", "msgId": 13, "deviceId": "light_01", "isOn": false}
```

**响应 (硬件未接入):**
```json
{
  "msgId": 13,
  "success": true,
  "data": {
    "id": "light_01",
    "name": "客厅主灯",
    "type": "light",
    "room": "客厅",
    "primaryValue": 80,
    "isOn": false
  },
  "hardwareOnline": false,
  "message": "客厅主灯开关离线，连通测试成功"
}
```

> ⚠️ `success: true` — 数据库状态已更新，但 `hardwareOnline: false` 表示真实硬件未响应  
> 设备端同时生成 TTS 蜂鸣提示音

---

#### control_device — 设备参数控制

**请求:**
```json
{"type": "command", "action": "control_device", "msgId": 14, "deviceId": "ac_01", "subAction": "set_temp", "params": {"value": 26}}
```

**subAction 可选值:**

| subAction | 说明 | params |
|-----------|------|--------|
| `set_temp` | 设置温度 | `{"value": 26}` |
| `set_speed` | 设置风速 | `{"value": 3}` |
| `set_brightness` | 设置亮度 | `{"value": 60}` |
| `set_mode` | 设置模式 | `{"mode": "制冷"}` |

**响应 (硬件未接入):**
```json
{
  "msgId": 14,
  "success": true,
  "data": {"id": "ac_01", "name": "客厅空调", "type": "ac", "primaryValue": 26, "isOn": true},
  "hardwareOnline": false,
  "message": "客厅空调调温离线，连通测试成功"
}
```

---

#### activate_scene — 激活场景 (按ID)

**请求:**
```json
{"type": "command", "action": "activate_scene", "msgId": 15, "sceneId": "s1"}
```

**场景ID对照:**

| sceneId | 名称 | 控制设备数 |
|---------|------|-----------|
| s1 | 回家 | 4 |
| s2 | 离家 | 12 |
| s3 | 睡眠 | 7 |
| s4 | 观影 | 4 |
| s5 | 用餐 | 3 |

**响应 (硬件未接入):**
```json
{
  "msgId": 15,
  "success": true,
  "data": {
    "sceneName": "回家",
    "affectedCount": 4,
    "affectedDevices": ["客厅主灯", "客厅空调", "智能窗帘", "客厅大门"]
  },
  "hardwareOnline": false,
  "message": "回家场景激活离线，连通测试成功"
}
```

---

#### activate_scene_by_name — 激活场景 (按名称)

**请求:**
```json
{"type": "command", "action": "activate_scene_by_name", "msgId": 16, "name": "回家"}
```

**响应:** 同 `activate_scene`，内部转换为 `sceneId: "s1"` 执行

---

#### add_device — 添加设备

**请求:**
```json
{"type": "command", "action": "add_device", "msgId": 17, "id": "light_06", "name": "阳台灯", "type": "light", "room": "阳台", "icon": "lightbulb"}
```

**响应 (硬件未接入):**
```json
{
  "msgId": 17,
  "success": true,
  "data": {"id": "light_06", "name": "阳台灯", "type": "light", "room": "阳台"},
  "hardwareOnline": false,
  "message": "设备已注册但硬件未接入，连通测试成功"
}
```

---

#### remove_device — 删除设备

**请求:**
```json
{"type": "command", "action": "remove_device", "msgId": 18, "deviceId": "light_06"}
```

**响应 (硬件未接入):**
```json
{
  "msgId": 18,
  "success": true,
  "data": {"removed": "light_06"},
  "hardwareOnline": false,
  "message": "阳台灯移除离线，连通测试成功"
}
```

---

#### update_user — 更新用户信息

**请求:**
```json
{"type": "command", "action": "update_user", "msgId": 19, "nickname": "小明", "homeName": "小明的家", "memberCount": 4}
```

**响应:**
```json
{
  "msgId": 19,
  "success": true,
  "data": {"id": "u001", "nickname": "小明", "homeName": "小明的家", "memberCount": 4}
}
```

> ✅ 纯数据库操作，无硬件依赖

---

#### send_chat — AI对话

**请求:**
```json
{"type": "command", "action": "send_chat", "msgId": 20, "content": "打开客厅灯"}
```

**响应 (场景匹配成功，硬件未接入):**
```json
{
  "msgId": 20,
  "success": true,
  "data": {
    "reply": "已切换到「回家」模式，控制 4 台设备",
    "sceneId": "s1"
  },
  "hardwareOnline": false,
  "message": "AI对话在线，设备控制离线，连通测试成功"
}
```

**对话流程:**
1. 用户消息 → 保存到 chat_history
2. RAG 匹配场景 → 如果命中，激活场景 + 返回场景回复
3. 未命中 → 调用 DeepSeek API → 返回AI回复
4. AI回复 → 保存到 chat_history

---

## 4. 保底机制 · 三层保障

### 4.1 指令级保底 (try/except)

任何指令执行异常时，返回:
```json
{
  "msgId": 123,
  "success": false,
  "offline": true,
  "error": "unable to open database file",
  "message": "设备查询离线，连通测试成功",
  "channelOk": true
}
```

| 字段 | 含义 |
|------|------|
| `offline: true` | 功能离线 (通道本身是通的) |
| `channelOk: true` | WebSocket 通道连通 |
| `message` | 中文提示，含功能名 |

### 4.2 设备级保底 (hardwareOnline)

控制类指令成功执行后，额外返回:
```json
{
  "success": true,
  "data": {...},
  "hardwareOnline": false,
  "message": "客厅主灯开关离线，连通测试成功"
}
```

| 字段 | 含义 |
|------|------|
| `success: true` | 数据库状态已更新 |
| `hardwareOnline: false` | 真实硬件未响应 (当前所有设备都是模拟的) |
| `message` | 带设备名的中文提示 |

**设备名映射表:**

| deviceId | 中文名 |
|----------|--------|
| ac_01 | 客厅空调 |
| fan_01 | 客厅吊扇 |
| door_01 | 客厅大门 |
| alarm_01 | 蜂鸣警报 |
| light_01 | 客厅主灯 |
| light_05 | 客厅氛围灯 |
| camera_01 | 客厅摄像头 |
| light_02 | 厨房灯 |
| exhaust_01 | 抽风机 |
| curtain_01 | 智能窗帘 |
| light_03 | 卧室灯 |
| fan_02 | 换气扇 |
| light_04 | 卫生间灯 |
| nfc_01 | NFC门禁 |
| voice_01 | 语音中控 |
| radar_01 | 毫米波雷达 |

### 4.3 TTS 音频保底

每次离线事件触发时:
1. 生成 660Hz 正弦波 WAV 文件 → `/data/A9/smart_home/tts_cache/offline_*.wav`
2. 日志输出 `[OFFLINE] ⚠ XXX离线，连通测试成功`
3. 日志输出 `[TTS] 🔔 离线提示音: /path/to/file.wav`

### 4.4 保底分类总览

| 指令 | 保底类型 | hardwareOnline | 说明 |
|------|----------|----------------|------|
| ping | 无需保底 | — | 纯软件，始终成功 |
| get_status | 指令级 | — | 数据库查询 |
| get_devices | 指令级 | — | 数据库查询 |
| get_sensors | 指令级 | — | 数据库查询 |
| get_scenes | 指令级 | — | 数据库查询 |
| get_user | 指令级 | — | 数据库查询 |
| get_operations | 指令级 | — | 数据库查询 |
| get_chat_history | 指令级 | — | 数据库查询 |
| get_server_status | 无需保底 | — | 纯软件，始终成功 |
| rag_search | 指令级 | — | 本地RAG |
| update_user | 指令级 | — | 数据库写入 |
| **get_alerts** | **设备级** | **false** | 模拟数据 |
| **get_cameras** | **设备级** | **false** | 模拟数据 |
| **toggle_device** | **设备级** | **false** | DB写入+TTS |
| **control_device** | **设备级** | **false** | DB写入+TTS |
| **activate_scene** | **设备级** | **false** | DB写入+TTS |
| **activate_scene_by_name** | **设备级** | **false** | DB写入+TTS |
| **add_device** | **设备级** | **false** | DB写入+TTS |
| **remove_device** | **设备级** | **false** | DB写入+TTS |
| **send_chat** | **设备级** | **false** | AI在线+设备离线 |

---

## 5. HTTP 推送接口

### 数据推送

```
POST http://yuanzhe.tech/api/smart-home/data
Content-Type: application/json; charset=utf-8
X-Device-Id: harmony_a9
```

推送策略:
- 全量快照: 每5分钟
- 增量事件: 每30秒检测变化
- 失败重试: 最多3次，指数退避

详细数据结构见 `PUSH_API_DOC.md`

---

## 6. 本地 HTTP API (设备端)

| 路径 | 方法 | 说明 |
|------|------|------|
| `http://192.168.1.81:8080/health` | GET | 网关健康检查 |
| `http://192.168.1.81:8080/api/devices` | GET | 设备列表 |
| `http://192.168.1.81:8080/api/sensors` | GET | 传感器列表 |
| `http://192.168.1.81:8080/api/scenes` | GET | 场景列表 |
| `http://192.168.1.81:8080/api/user/profile` | GET | 用户信息 |
| `http://192.168.1.81:8080/api/operations` | GET | 操作记录 |
| `http://192.168.1.81:8080/api/cameras` | GET | 摄像头 |
| `http://192.168.1.81:8080/api/alerts` | GET | 告警 |
| `http://192.168.1.81:8080/api/server/status` | GET | 服务状态 |
| `http://192.168.1.81:8080/api/rag/stats` | GET | RAG统计 |
| `http://192.168.1.81:8080/api/chat/send` | POST | AI对话 |
| `http://192.168.1.81:8080/api/devices/{id}/toggle` | POST | 开关设备 |
| `http://192.168.1.81:8080/api/devices/{id}/control` | POST | 控制设备 |
| `http://192.168.1.81:8080/api/scenes/{id}/activate` | POST | 激活场景 |
| `http://192.168.1.81:8080/api/devices` | POST | 添加设备 |
| `http://192.168.1.81:8080/api/user/profile` | POST | 更新用户 |
| `http://192.168.1.81:8080/api/rag/search` | POST | RAG搜索 |
| `http://192.168.1.81:8080/api/door/control` | POST | 门禁控制 |
| `http://192.168.1.81:8080/api/bearpi/command` | POST | BearPi指令 |
| `http://192.168.1.81:8081/channel/status` | GET | 通道连接状态 |
| `http://192.168.1.81:8081/channel/test` | GET | 通道测试ping |

---

## 7. 数据库 (SQLite)

路径: `/data/A9/control/data/smart_home.db`

| 表 | 记录数 | 说明 |
|----|--------|------|
| devices | 16 | 设备状态 |
| sensors | 9 | 传感器配置 |
| scenes | 5 | 场景定义 |
| scene_actions | 30 | 场景关联设备动作 |
| device_operations | 动态 | 操作日志 |
| sensor_readings | 动态 | 传感器历史读数 |
| users | 1 | 用户信息 |
| chat_history | 动态 | 对话记录 |

---

## 8. 服务端实现要点

### WebSocket 服务端 (Node.js 示例)

```javascript
const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 80, path: '/ws/smart-home' });
const devices = new Map(); // deviceId → ws

wss.on('connection', (ws, req) => {
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
        // 存储快照
        saveSnapshot(msg.deviceId, msg.data);
        break;
      case 'heartbeat':
        // 更新 last_seen
        break;
      default:
        if (msg.msgId) handleResponse(msg);
    }
  });

  ws.on('close', () => {
    if (deviceId) devices.delete(deviceId);
  });
});

// ===== 远程控制: 向设备发送指令 =====
function sendCommand(action, params = {}) {
  const ws = devices.get('harmony_a9');
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return Promise.reject(new Error('设备不在线'));
  }
  const msgId = Date.now();
  const cmd = { type: 'command', action, msgId, ...params };
  ws.send(JSON.stringify(cmd));
  
  return new Promise((resolve) => {
    const handler = (raw) => {
      const msg = JSON.parse(raw);
      if (msg.msgId === msgId) {
        ws.off('message', handler);
        resolve(msg);
      }
    };
    ws.on('message', handler);
    // 30秒超时
    setTimeout(() => { ws.off('message', handler); resolve(null); }, 30000);
  });
}

// 使用示例:
// const result = await sendCommand('toggle_device', { deviceId: 'light_01', isOn: false });
// result.hardwareOnline === false → 硬件未接入，但通道通了
// result.offline === true → 功能完全离线
```

### 关键判断逻辑

```javascript
function handleDeviceResponse(result) {
  if (!result) return { status: 'timeout', message: '设备无响应' };
  
  if (result.offline === true) {
    // 功能完全离线 (数据库异常等)
    return { status: 'offline', channelOk: result.channelOk, message: result.message };
  }
  
  if (result.success && result.hardwareOnline === false) {
    // 数据库写入成功，但硬件未接入
    return { status: 'simulated', data: result.data, message: result.message };
  }
  
  if (result.success) {
    // 完全成功 (未来硬件接入后)
    return { status: 'online', data: result.data };
  }
  
  // 业务错误 (设备不存在等)
  return { status: 'error', error: result.error };
}
```

### Nginx 配置

```nginx
# WebSocket 代理
location /ws/smart-home {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;  # 1小时，匹配心跳
}

# HTTP 推送接收
location /api/smart-home/ {
    proxy_pass http://127.0.0.1:3000/api/smart-home/;
}
```

---

## 9. 连接生命周期

```
设备端                                    yuanzhe.tech
  │                                           │
  │──── WebSocket 握手 ──────────────────→    │
  │──── register ────────────────────────→    │
  │──── snapshot (13KB) ─────────────────→    │
  │                                           │
  │←──── command (toggle_device) ─────────    │
  │──── response {success, hardwareOnline:    │
  │       false, message: "客厅主灯开关       │
  │       离线，连通测试成功"} ────────────→   │
  │                                           │
  │──── heartbeat (每30s) ────────────────→   │
  │──── snapshot (每5min) ────────────────→   │
  │                                           │
  │  ✗ 连接断开                               │
  │──── 2s后重连 → 4s → 8s → ... → 60s ──→   │
  │──── register + snapshot ──────────────→   │
```
