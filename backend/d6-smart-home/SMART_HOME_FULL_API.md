# A9 智慧家居 · 后端完整接口文档

> 版本: 3.1.0
> 设备: HarmonyOS A9 (192.168.1.81)
> 服务端: yuanzhe.tech
> 日期: 2026-07-09
> **所有22个指令均保证有 TTS 蜂鸣音 + message + hardwareOnline:false 保底响应**

---

## 1. 硬件拓扑 → 接口映射

### 1.1 完整硬件清单

```
智能家居
├── 客厅
│   ├── 红外模块 (IR)     → ac_01 客厅空调    [遥控: 开关/温度/模式/风速]
│   ├── 舵机 (Servo)      → door_01 客厅大门  [控制: 开门/关门]
│   ├── 蜂鸣器 (Buzzer)   → alarm_01 蜂鸣警报 [控制: 开启/关闭警报]
│   ├── 温湿度传感器 (DHT11) → temp_01 温度 + humid_01 湿度 [只读]
│   ├── 光敏模块 (LDR)    → light_s_01 光照   [只读, 联动灯光/窗帘]
│   ├── 摄像头 (Camera)   → camera_01 摄像头  [只读: 实时视频流]
│   └── 灯 (LED)          → light_01 主灯 + light_05 氛围灯 [控制: 开关/亮度]
├── 厨房
│   ├── 热敏模块 (Thermal) → heat_01 热敏火灾  [只读, 联动警报]
│   ├── 烟雾传感器 (Smoke) → smoke_01 烟雾检测 [只读, 联动警报]
│   └── 灯 (LED)          → light_02 厨房灯   [控制: 开关/亮度]
├── 卧室
│   ├── 舵机 (Servo)      → curtain_01 智能窗帘 [控制: 开合度0-100%]
│   └── 灯 (LED)          → light_03 卧室灯    [控制: 开关/亮度]
├── 卫生间
│   ├── 舵机 (Servo)      → fan_02 换气扇     [控制: 开关/风速]
│   └── 灯 (LED)          → light_04 卫生间灯  [控制: 开关/亮度]
├── 室外
│   └── NFC模块 (NFC)     → nfc_01 NFC门禁    [控制: 开门/锁门] + door_s_01 门窗感应 [只读]
└── 全局
    ├── 语音模块 (Voice)  → voice_01 语音中控  [输入: 语音指令]
    └── 毫米波雷达 (Radar)→ radar_01 雷达      [只读, 联动: 人到灯亮]
```

### 1.2 硬件 → 设备ID → 接口 完整对照

| 房间 | 硬件模块 | 设备ID | 传感器ID | 操作类型 | BearPi指令码 |
|------|----------|--------|----------|----------|-------------|
| 客厅 | 红外模块 | ac_01 | — | control_device | cmd=2 |
| 客厅 | 舵机(门) | door_01 | — | toggle_device | cmd=3 |
| 客厅 | 蜂鸣器 | alarm_01 | — | toggle_device | cmd=4 |
| 客厅 | DHT11 | — | temp_01, humid_01 | 只读(自动上报) | — |
| 客厅 | 光敏模块 | — | light_s_01 | 只读(自动上报) | — |
| 客厅 | 摄像头 | camera_01 | — | 只读(视频流) | — |
| 客厅 | 主灯 | light_01 | — | toggle + set_brightness | cmd=1 |
| 客厅 | 氛围灯 | light_05 | — | toggle + set_brightness | cmd=1 |
| 厨房 | 热敏 | — | heat_01 | 只读(联动警报) | — |
| 厨房 | 烟雾 | — | smoke_01 | 只读(联动警报) | — |
| 厨房 | 灯 | light_02 | — | toggle + set_brightness | cmd=1 |
| 卧室 | 舵机(窗帘) | curtain_01 | — | control_device | cmd=5 |
| 卧室 | 灯 | light_03 | — | toggle + set_brightness | cmd=1 |
| 卫生间 | 舵机(换气扇) | fan_02 | — | toggle + set_speed | cmd=6 |
| 卫生间 | 灯 | light_04 | — | toggle + set_brightness | cmd=1 |
| 室外 | NFC | nfc_01 | — | toggle_device | cmd=7 |
| 室外 | 门窗感应 | — | door_s_01 | 只读(联动) | — |
| 全局 | 语音 | voice_01 | — | send_chat | — |
| 全局 | 雷达 | radar_01 | — | 只读(联动灯) | — |

> **BearPi 串口协议**: `AA 55 [CRC32 4B] [cmd 1B] [room 1B] [val 1B] [padding 21B] 55 AA`  
> 通过 TCP 发送到开发板 `192.168.1.81:8000`

---

## 2. 通信通道

### 2.1 WebSocket 通道 (双向实时)

```
ws://yuanzhe.tech/ws/smart-home
```

设备主动连出，穿透 NAT。服务端通过此通道下发指令，设备返回结果。

### 2.2 HTTP 推送 (设备→服务端)

```
POST http://yuanzhe.tech/api/smart-home/data
```

定时推送全量快照(5min)和增量事件(30s)。

### 2.3 本地 BearPi 协议 (设备内部)

```
TCP → 192.168.1.81:8000 (开发板)
```

设备后端通过 TCP 发 BearPi 二进制包控制硬件。

### 2.4 传感器 TCP 监听 (设备内部)

```
TCP ← 192.168.1.62:8000 (温湿度DHT11)
```

温湿度传感器主动上报: `DATA,temp=24.5,humid=58.0`

---

## 3. 20个远程指令 · 完整定义

所有指令通过 WebSocket 通道下发:

```json
{"type": "command", "action": "<动作>", "msgId": <数字>, ...参数}
```

设备必回:

```json
{"msgId": <同上>, "success": true/false, "data": {...}, "hardwareOnline": true/false, "message": "..."}
```

---

### 3.1 查询类 (纯软件，始终成功 + TTS保底)

> **所有查询类指令现在也带 `hardwareOnline: false` + `message` + TTS蜂鸣音**
> 格式: `{..., "hardwareOnline": false, "message": "XX查询成功，硬件未接入，连通测试成功"}`

#### `ping` — 连通测试

```json
// 请求
{"type": "command", "action": "ping", "msgId": 1}

// 响应
{"msgId": 1, "success": true, "data": {"pong": true, "time": "2026-07-09T10:00:00"}, "hardwareOnline": false, "message": "连通测试成功，硬件未接入，连通测试成功"}
```

> ✅ 不依赖任何硬件和数据库 · 🔔 TTS蜂鸣

---

#### `get_status` — 全量数据快照

```json
// 请求
{"type": "command", "action": "get_status", "msgId": 2}

// 响应
{
  "msgId": 2, "success": true,
  "data": {
    "devices": [...],       // 16台设备
    "sensors": [...],       // 9个传感器
    "scenes": [...],        // 5个场景
    "operations": [...],    // 操作记录
    "chatHistory": [...],   // 对话历史
    "user": {...},          // 用户
    "serverStatus": {...}   // 服务状态
  },
  "hardwareOnline": false,
  "message": "状态查询成功，硬件未接入，连通测试成功"
}
```

---

#### `get_devices` — 16台设备列表

```json
// 请求
{"type": "command", "action": "get_devices", "msgId": 3}

// 响应
{
  "msgId": 3, "success": true,
  "data": [
    // ===== 客厅 =====
    {"id": "ac_01",       "name": "客厅空调",   "type": "ac",      "status": "active",  "room": "客厅", "icon": "air_fill",       "primaryValue": 24,  "isOn": true, "mode": "制冷"},
    {"id": "fan_01",      "name": "客厅吊扇",   "type": "fan",     "status": "online",  "room": "客厅", "icon": "fan_fill_1",     "primaryValue": 2,   "isOn": true, "battery": 92},
    {"id": "door_01",     "name": "客厅大门",   "type": "door",    "status": "online",  "room": "客厅", "icon": "lock",           "primaryValue": 0,   "isOn": false, "battery": 88},
    {"id": "alarm_01",    "name": "蜂鸣警报",   "type": "alarm",   "status": "online",  "room": "客厅", "icon": "bell_fill",      "primaryValue": 0,   "isOn": false},
    {"id": "light_01",    "name": "客厅主灯",   "type": "light",   "status": "online",  "room": "客厅", "icon": "lightbulb",      "primaryValue": 80,  "isOn": true},
    {"id": "light_05",    "name": "客厅氛围灯", "type": "light",   "status": "online",  "room": "客厅", "icon": "lightbulb",      "primaryValue": 45,  "isOn": false},
    {"id": "camera_01",   "name": "客厅摄像头", "type": "camera",  "status": "online",  "room": "客厅", "icon": "camera_fill",    "primaryValue": 0,   "isOn": true},
    // ===== 厨房 =====
    {"id": "light_02",    "name": "厨房灯",     "type": "light",   "status": "online",  "room": "厨房", "icon": "lightbulb",      "primaryValue": 70,  "isOn": false},
    {"id": "exhaust_01",  "name": "抽风机",     "type": "fan",     "status": "online",  "room": "厨房", "icon": "fan_fill_1",     "primaryValue": 1,   "isOn": false},
    // ===== 卧室 =====
    {"id": "curtain_01",  "name": "智能窗帘",   "type": "curtain", "status": "online",  "room": "卧室", "icon": "lock_open_fill",  "primaryValue": 100, "isOn": true, "battery": 95},
    {"id": "light_03",    "name": "卧室灯",     "type": "light",   "status": "online",  "room": "卧室", "icon": "lightbulb",      "primaryValue": 50,  "isOn": false},
    // ===== 卫生间 =====
    {"id": "fan_02",      "name": "换气扇",     "type": "fan",     "status": "online",  "room": "卫生间", "icon": "fan_fill_1",   "primaryValue": 1,   "isOn": false},
    {"id": "light_04",    "name": "卫生间灯",   "type": "light",   "status": "online",  "room": "卫生间", "icon": "lightbulb",    "primaryValue": 60,  "isOn": false},
    // ===== 室外 =====
    {"id": "nfc_01",      "name": "NFC门禁",    "type": "nfc",     "status": "online",  "room": "室外", "icon": "lock",          "primaryValue": 0,   "isOn": false},
    // ===== 全局 =====
    {"id": "voice_01",    "name": "语音中控",   "type": "voice",   "status": "online",  "room": "全局", "icon": "mic_fill",       "primaryValue": 0,   "isOn": true},
    {"id": "radar_01",    "name": "毫米波雷达", "type": "radar",   "status": "active",  "room": "全局", "icon": "wifi",           "primaryValue": 0,   "isOn": true}
  ]
}
```

---

#### `get_sensors` — 9个传感器列表

```json
// 请求
{"type": "command", "action": "get_sensors", "msgId": 4}

// 响应
{
  "msgId": 4, "success": true,
  "data": [
    // ===== 环境监测 (客厅) =====
    {"id": "temp_01",     "name": "客厅温度",  "type": "temperature", "group": "环境监测", "room": "客厅", "current": {"value": 24.5, "unit": "°C"},  "thresholdMin": 18, "thresholdMax": 28, "isAlert": false},
    {"id": "humid_01",    "name": "客厅湿度",  "type": "humidity",    "group": "环境监测", "room": "客厅", "current": {"value": 58.0, "unit": "%RH"}, "thresholdMin": 40, "thresholdMax": 70, "isAlert": false},
    {"id": "light_s_01",  "name": "客厅光照",  "type": "illuminance", "group": "环境监测", "room": "客厅", "current": {"value": 320,   "unit": "lx"},  "isAlert": false},
    {"id": "air_01",      "name": "空气质量",  "type": "air_quality", "group": "环境监测", "room": "客厅", "current": {"value": 42,    "unit": "AQI"}, "thresholdMax": 100, "isAlert": false},
    // ===== 安防 (客厅) =====
    {"id": "pir_01",      "name": "人体感应",  "type": "pir",         "group": "安防", "room": "客厅", "current": {"value": 1.0, "unit": "有人"},  "isAlert": false},
    // ===== 安防 (厨房) =====
    {"id": "smoke_01",    "name": "烟雾检测",  "type": "smoke",       "group": "安防", "room": "厨房", "current": {"value": 0.0, "unit": "正常"},  "isAlert": false},
    {"id": "heat_01",     "name": "热敏火灾",  "type": "heat",        "group": "安防", "room": "厨房", "current": {"value": 36.2, "unit": "°C"},  "thresholdMax": 60, "isAlert": false},
    // ===== 安防 (室外) =====
    {"id": "door_s_01",   "name": "门窗感应",  "type": "door_window", "group": "安防", "room": "室外", "current": {"value": 0.0, "unit": "关闭"},  "isAlert": false},
    // ===== 能耗 (全局) =====
    {"id": "power_01",    "name": "总功率",    "type": "power",       "group": "能耗", "room": "全局", "current": {"value": 1.2, "unit": "kW"},   "isAlert": false}
  ]
}
```

---

#### `get_scenes` — 5个场景

```json
// 请求
{"type": "command", "action": "get_scenes", "msgId": 5}

// 响应
{
  "msgId": 5, "success": true,
  "data": [
    {"id": "s1", "name": "回家", "icon": "house_fill",  "color": "#22D3EE", "isActive": true,  "description": "回家模式",
      "actions": [
        {"deviceId": "light_01",   "isOn": true, "primaryValue": 80},   // 客厅主灯开 80%
        {"deviceId": "ac_01",      "isOn": true, "primaryValue": 24},   // 空调开 24°C 制冷
        {"deviceId": "curtain_01", "isOn": true, "primaryValue": 100},  // 窗帘全开
        {"deviceId": "door_01",    "isOn": true}                        // 大门开
      ]},
    {"id": "s2", "name": "离家", "icon": "figure_walk", "color": "#F97316", "isActive": false, "description": "离家模式",
      "actions": [/* 12台: 全部灯关+空调关+风扇关+窗帘关+门关+NFC关 */]},
    {"id": "s3", "name": "睡眠", "icon": "moon_fill",   "color": "#818CF8", "isActive": false, "description": "睡眠模式",
      "actions": [/* 7台: 全部灯关+空调26°C+窗帘关 */]},
    {"id": "s4", "name": "观影", "icon": "film",        "color": "#F472B6", "isActive": false, "description": "观影模式",
      "actions": [/* 4台: 主灯20%+氛围灯关+窗帘关+空调24°C */]},
    {"id": "s5", "name": "用餐", "icon": "fork_knife",  "color": "#34D399", "isActive": false, "description": "用餐模式",
      "actions": [/* 3台: 主灯60%+厨房灯80%+抽风机开 */]}
  ]
}
```

---

#### `get_user` — 用户信息

```json
// 请求
{"type": "command", "action": "get_user", "msgId": 6}
// 响应
{"msgId": 6, "success": true, "data": {"id": "u001", "nickname": "用户", "homeName": "我的家", "memberCount": 3, "avatar": "", "deviceCount": 16}}
```

---

#### `get_operations` — 操作记录

```json
// 请求
{"type": "command", "action": "get_operations", "msgId": 7, "limit": 50}
// 响应
{"msgId": 7, "success": true, "data": [
  {"deviceId": "light_01", "action": "toggle", "params": "{\"isOn\":true}", "result": "ok", "source": "scene", "sceneId": "s1", "timestamp": "..."}
]}
```

---

#### `get_chat_history` — 对话历史

```json
// 请求
{"type": "command", "action": "get_chat_history", "msgId": 8, "limit": 50}
// 响应
{"msgId": 8, "success": true, "data": [
  {"userId": "u001", "role": "user",     "content": "打开客厅灯",     "sceneId": "s1", "timestamp": "..."},
  {"userId": "u001", "role": "assistant", "content": "已切换到「回家」模式", "sceneId": "s1", "timestamp": "..."}
]}
```

---

#### `get_alerts` — 告警 (模拟)

```json
// 请求
{"type": "command", "action": "get_alerts", "msgId": 9}
// 响应
{"msgId": 9, "success": true, "data": [
  {"id": "a1", "source": "门口摄像头", "content": "门口有人停留", "level": "warning", "isRead": false, "timestamp": 1720338420000},
  {"id": "a2", "source": "卧室窗帘",   "content": "电量剩余15%",  "level": "info",    "isRead": true,  "timestamp": 1720335000000},
  {"id": "a3", "source": "客厅湿度",   "content": "湿度72%",     "level": "info",    "isRead": true,  "timestamp": 1720327800000}
], "hardwareOnline": false, "message": "告警数据为模拟数据，连通测试成功"}
```

---

#### `get_cameras` — 摄像头 (模拟)

```json
// 请求
{"type": "command", "action": "get_cameras", "msgId": 10}
// 响应
{"msgId": 10, "success": true, "data": [
  {"id": "cam_01", "name": "客厅摄像头", "room": "客厅", "status": "online", "isRecording": true,  "resolution": "1080P"},
  {"id": "cam_02", "name": "门口摄像头", "room": "室外", "status": "online", "isRecording": false, "resolution": "1080P"}
], "hardwareOnline": false, "message": "摄像头数据为模拟数据，连通测试成功"}
```

---

#### `get_server_status` — 服务状态

```json
// 请求
{"type": "command", "action": "get_server_status", "msgId": 11}
// 响应
{"msgId": 11, "success": true, "data": {
  "host": "192.168.1.81", "port": 8080, "isOnline": true, "protocol": "wifi",
  "version": "v3", "channelVersion": "1.0.0", "python": "3.14.5",
  "dbSize": 118784, "connectedClients": 1
}}
```

---

#### `rag_search` — RAG知识搜索

```json
// 请求
{"type": "command", "action": "rag_search", "msgId": 12, "query": "空调怎么开", "n_results": 5}
// 响应
{"msgId": 12, "success": true, "data": [
  {"content": "客厅空调可通过语音或场景控制...", "category": "device_control", "score": 0.85}
]}
```

---

### 3.2 控制类 (硬件未接入时返回保底)

#### `toggle_device` — 开关设备

```json
// 请求
{"type": "command", "action": "toggle_device", "msgId": 13, "deviceId": "light_01", "isOn": false}
```

**所有可用 deviceId:**

| deviceId | 中文名 | 硬件 | 开关效果 |
|----------|--------|------|----------|
| light_01 | 客厅主灯 | LED | 开/关灯 |
| light_05 | 客厅氛围灯 | LED | 开/关灯 |
| light_02 | 厨房灯 | LED | 开/关灯 |
| light_03 | 卧室灯 | LED | 开/关灯 |
| light_04 | 卫生间灯 | LED | 开/关灯 |
| ac_01 | 客厅空调 | 红外IR | 开/关空调 |
| fan_01 | 客厅吊扇 | — | 开/关吊扇 |
| door_01 | 客厅大门 | 舵机 | 开门/关门 |
| alarm_01 | 蜂鸣警报 | 蜂鸣器 | 开启/关闭警报 |
| camera_01 | 客厅摄像头 | — | 开/关摄像头 |
| exhaust_01 | 抽风机 | — | 开/关抽风机 |
| curtain_01 | 智能窗帘 | 舵机 | 全开/全关 |
| fan_02 | 换气扇 | 舵机 | 开/关换气扇 |
| nfc_01 | NFC门禁 | NFC | 开门/锁门 |
| voice_01 | 语音中控 | — | 开启/关闭 |
| radar_01 | 毫米波雷达 | — | 开启/关闭 |

**响应 (硬件未接入):**
```json
{
  "msgId": 13, "success": true,
  "data": {"id": "light_01", "name": "客厅主灯", "type": "light", "room": "客厅", "primaryValue": 80, "isOn": false},
  "hardwareOnline": false,
  "message": "客厅主灯开关离线，连通测试成功"
}
```

---

#### `control_device` — 设备参数控制

```json
// 请求
{"type": "command", "action": "control_device", "msgId": 14, "deviceId": "ac_01", "subAction": "set_temp", "params": {"value": 26}}
```

**subAction 与 deviceId 对应关系:**

| subAction | 适用设备 | 硬件 | params | 说明 |
|-----------|----------|------|--------|------|
| `set_brightness` | light_01, light_05, light_02, light_03, light_04 | LED | `{"value": 0-100}` | 亮度百分比 |
| `set_temp` | ac_01 | 红外IR | `{"value": 16-30}` | 目标温度°C |
| `set_mode` | ac_01 | 红外IR | `{"mode": "制冷"/"制热"/"送风"/"除湿"}` | 空调模式 |
| `set_speed` | fan_01, exhaust_01, fan_02 | — | `{"value": 1-3}` | 风速档位 |
| `set_openness` | curtain_01 | 舵机 | `{"value": 0-100}` | 窗帘开合度% |

**响应 (硬件未接入):**
```json
{
  "msgId": 14, "success": true,
  "data": {"id": "ac_01", "name": "客厅空调", "type": "ac", "primaryValue": 26, "isOn": true},
  "hardwareOnline": false,
  "message": "客厅空调调温离线，连通测试成功"
}
```

---

#### `activate_scene` — 激活场景 (按ID)

```json
// 请求
{"type": "command", "action": "activate_scene", "msgId": 15, "sceneId": "s1"}
```

| sceneId | 名称 | 涉及硬件 | 控制设备数 |
|---------|------|----------|-----------|
| s1 | 回家 | LED+IR+舵机 | 4 (主灯开80%, 空调24°C制冷, 窗帘全开, 大门开) |
| s2 | 离家 | LED+IR+舵机+NFC | 12 (全部关) |
| s3 | 睡眠 | LED+IR+舵机 | 7 (全部灯关, 空调26°C, 窗帘关) |
| s4 | 观影 | LED+IR+舵机 | 4 (主灯20%, 氛围灯关, 窗帘关, 空调24°C) |
| s5 | 用餐 | LED+舵机 | 3 (主灯60%, 厨房灯80%, 抽风机开) |

**响应 (硬件未接入):**
```json
{
  "msgId": 15, "success": true,
  "data": {"sceneName": "回家", "affectedCount": 4, "affectedDevices": ["客厅主灯", "客厅空调", "智能窗帘", "客厅大门"]},
  "hardwareOnline": false,
  "message": "回家场景激活离线，连通测试成功"
}
```

---

#### `activate_scene_by_name` — 按名称激活场景

```json
// 请求
{"type": "command", "action": "activate_scene_by_name", "msgId": 16, "name": "回家"}
// 响应: 同 activate_scene
```

---

#### `add_device` — 添加设备

```json
// 请求
{"type": "command", "action": "add_device", "msgId": 17, "id": "light_06", "name": "阳台灯", "type": "light", "room": "阳台", "icon": "lightbulb"}
// 响应 (硬件未接入)
{"msgId": 17, "success": true, "data": {"id": "light_06", "name": "阳台灯", "type": "light", "room": "阳台"},
 "hardwareOnline": false, "message": "设备已注册但硬件未接入，连通测试成功"}
```

---

#### `remove_device` — 删除设备

```json
// 请求
{"type": "command", "action": "remove_device", "msgId": 18, "deviceId": "light_06"}
// 响应 (硬件未接入)
{"msgId": 18, "success": true, "data": {"removed": "light_06", "removedName": "阳台灯"},
 "hardwareOnline": false, "message": "阳台灯移除离线，连通测试成功"}
```

---

#### `update_user` — 更新用户信息

```json
// 请求
{"type": "command", "action": "update_user", "msgId": 19, "nickname": "小明", "homeName": "小明的家", "memberCount": 4}
// 响应
{"msgId": 19, "success": true, "data": {"id": "u001", "nickname": "小明", "homeName": "小明的家", "memberCount": 4}, "hardwareOnline": false, "message": "用户更新成功，硬件未接入，连通测试成功"}
```

---

#### `send_chat` — AI对话

```json
// 请求
{"type": "command", "action": "send_chat", "msgId": 20, "content": "打开客厅灯"}
// 响应 (场景匹配，硬件未接入)
{
  "msgId": 20, "success": true,
  "data": {"reply": "已切换到「回家」模式，控制 4 台设备", "sceneId": "s1"},
  "hardwareOnline": false,
  "message": "AI对话在线，设备控制离线，连通测试成功"
}
```

**对话流程:** 用户消息 → RAG场景匹配 → 命中则激活场景 → 未命中则DeepSeek API → 保存历史

---

## 4. 复合功能 · 自动联动

以下功能不在 WebSocket 指令里，而是设备端**自动触发**的联动逻辑:

### 4.1 雷达人到灯亮

```
触发: radar_01 检测到人进入区域
条件: 区域内灯当前关闭
动作: 自动开灯 (light_01/light_05 根据区域)
恢复: 人离开后 5 分钟自动关灯
```

**服务端可感知:** 通过 `get_devices` 看到灯的 `isOn` 变化，通过增量推送收到 `device_change` 事件

### 4.2 光敏自动调光

```
触发: light_s_01 光照值变化
条件: 光照 < 100lx 且灯已开
动作: 自动调高灯亮度 (primaryValue 增加)
条件: 光照 > 500lx 且灯已开
动作: 自动降低灯亮度
条件: 光照 < 50lx 且灯未开
动作: 自动开灯
```

### 4.3 烟雾/热敏火灾警报

```
触发: smoke_01 值 > 阈值 或 heat_01 > 60°C
动作:
  1. alarm_01 蜂鸣器自动开启
  2. 生成告警 (get_alerts 可见)
  3. 推送告警事件到服务端
恢复: 传感器值恢复正常后 30 秒关闭警报
```

### 4.4 温湿度联动空调

```
触发: temp_01 > 28°C 且 ac_01 未开
动作: 自动开空调 26°C 制冷
触发: temp_01 < 18°C 且 ac_01 未开
动作: 自动开空调 22°C 制热
```

### 4.5 NFC 开门联动

```
触发: nfc_01 收到刷卡信号
动作:
  1. door_01 大门舵机开门
  2. door_s_01 门窗感应状态更新
  3. 5秒后自动关门
```

**服务端监听方式:** 所有联动变化通过增量推送 (`device_change` / `sensor_change`) 实时送达，服务端无需额外接口

---

## 5. 保底机制 · 三层保障

### 5.1 响应状态判断 (服务端必读)

```javascript
function handleResult(result) {
  if (!result)           return { status: 'timeout',  label: '🔴', msg: '设备无响应' };
  if (result.offline)    return { status: 'offline',  label: '🔴', msg: result.message };
  if (!result.success)   return { status: 'error',    label: '⚠️', msg: result.error };
  if (result.hardwareOnline === false)
                         return { status: 'simulated', label: '🟡', msg: result.message };
  return                  { status: 'online',   label: '🟢', msg: '正常' };
}
```

| status | 含义 | 前端建议 |
|--------|------|----------|
| `online` | 硬件已接入，操作成功 | 🟢 绿色 "在线" |
| `simulated` | DB成功，硬件未接 (hardwareOnline:false) | 🟡 黄色 "模拟" |
| `offline` | 功能完全离线 (offline:true, channelOk:true) | 🔴 红色 "离线" |
| `error` | 业务错误 (设备不存在等) | ⚠️ 灰色 + error |
| `timeout` | WebSocket 无响应 | 🔴 红色 "超时" |

### 5.2 保底分类总览

> **所有22个指令均保证有 TTS 蜂鸣音 + message 字段 + hardwareOnline:false**
> 查询类指令: `XX查询成功，硬件未接入，连通测试成功`
> 控制类指令: `设备名+操作+离线，连通测试成功`
> 异常时: `offline:true + channelOk:true` (通道通但功能离线)

| 指令 | 保底类型 | hardwareOnline | TTS蜂鸣 | message内容 | 硬件依赖 |
|------|----------|----------------|---------|-------------|----------|
| ping | 通道级 | false | ✅ | 连通测试成功，硬件未接入，连通测试成功 | 无 |
| get_status | 通道级 | false | ✅ | 状态查询成功，硬件未接入，连通测试成功 | DB |
| get_devices | 通道级 | false | ✅ | 设备查询成功，硬件未接入，连通测试成功 | DB |
| get_sensors | 通道级 | false | ✅ | 传感器查询成功，硬件未接入，连通测试成功 | DB |
| get_scenes | 通道级 | false | ✅ | 场景查询成功，硬件未接入，连通测试成功 | DB |
| get_user | 通道级 | false | ✅ | 用户查询成功，硬件未接入，连通测试成功 | DB |
| get_operations | 通道级 | false | ✅ | 操作记录查询成功，硬件未接入，连通测试成功 | DB |
| get_chat_history | 通道级 | false | ✅ | 对话历史查询成功，硬件未接入，连通测试成功 | DB |
| get_server_status | 通道级 | false | ✅ | 服务状态查询成功，硬件未接入，连通测试成功 | 无 |
| rag_search | 通道级 | false | ✅ | 知识搜索成功，硬件未接入，连通测试成功 | 本地RAG |
| update_user | 通道级 | false | ✅ | 用户更新成功，硬件未接入，连通测试成功 | DB |
| get_alerts | 设备级 | false | ✅ | 告警数据为模拟数据，连通测试成功 | 模拟数据 |
| get_cameras | 设备级 | false | ✅ | 摄像头数据为模拟数据，连通测试成功 | 模拟数据 |
| toggle_device | 设备级 | false | ✅ | 设备名+开关离线，连通测试成功 | BearPi/IR/舵机 |
| control_device | 设备级 | false | ✅ | 设备名+调温/调光/调速/模式切换离线，连通测试成功 | BearPi/IR/舵机 |
| activate_scene | 设备级 | false | ✅ | 场景名+场景激活离线，连通测试成功 | 多硬件组合 |
| activate_scene_by_name | 设备级 | false | ✅ | 场景名+场景激活离线，连通测试成功 | 多硬件组合 |
| add_device | 设备级 | false | ✅ | 设备已注册但硬件未接入，连通测试成功 | 硬件注册 |
| remove_device | 设备级 | false | ✅ | 设备名+移除离线，连通测试成功 | 硬件移除 |
| send_chat | 设备级 | false | ✅ | AI对话在线，设备控制离线，连通测试成功 | DeepSeek API |

### 5.3 TTS 音频保底

每次硬件离线事件:
1. 生成 660Hz WAV 提示音 → `/data/A9/smart_home/tts_cache/offline_*.wav`
2. 日志 `[OFFLINE] ⚠ XXX离线，连通测试成功`
3. 日志 `[TTS] 🔔 离线提示音: <path>`

---

## 6. HTTP 推送接口

```
POST http://yuanzhe.tech/api/smart-home/data
Content-Type: application/json; charset=utf-8
X-Device-Id: harmony_a9
X-Push-Version: 1.0.0
```

| 推送类型 | 频率 | 大小 |
|----------|------|------|
| 全量快照 (type=snapshot) | 每5分钟 | ~15KB |
| 增量事件 (type=event) | 每30秒(有变化时) | ~0.5KB |

增量事件类型:
- `device_change` — 设备状态变化 (开关/亮度/温度/模式)
- `sensor_change` — 传感器数据变化 (温湿度/光照/烟雾)

---

## 7. 本地 HTTP API (设备端)

| 路径 | 方法 | 说明 |
|------|------|------|
| `http://192.168.1.81:8080/health` | GET | 健康检查 |
| `http://192.168.1.81:8080/api/devices` | GET | 设备列表 |
| `http://192.168.1.81:8080/api/sensors` | GET | 传感器列表 |
| `http://192.168.1.81:8080/api/scenes` | GET | 场景列表 |
| `http://192.168.1.81:8080/api/user/profile` | GET/POST | 用户信息 |
| `http://192.168.1.81:8080/api/operations` | GET | 操作记录 |
| `http://192.168.1.81:8080/api/cameras` | GET | 摄像头 |
| `http://192.168.1.81:8080/api/alerts` | GET | 告警 |
| `http://192.168.1.81:8080/api/server/status` | GET | 服务状态 |
| `http://192.168.1.81:8080/api/rag/stats` | GET | RAG统计 |
| `http://192.168.1.81:8080/api/rag/search` | POST | RAG搜索 |
| `http://192.168.1.81:8080/api/chat/send` | POST | AI对话 |
| `http://192.168.1.81:8080/api/devices/{id}/toggle` | POST | 开关设备 |
| `http://192.168.1.81:8080/api/devices/{id}/control` | POST | 控制设备 |
| `http://192.168.1.81:8080/api/scenes/{id}/activate` | POST | 激活场景 |
| `http://192.168.1.81:8080/api/devices` | POST | 添加设备 |
| `http://192.168.1.81:8080/api/door/control` | POST | 门禁控制 |
| `http://192.168.1.81:8080/api/bearpi/command` | POST | BearPi底层指令 |
| `http://192.168.1.81:8081/channel/status` | GET | 通道状态 |
| `http://192.168.1.81:8081/channel/test` | GET | 通道测试 |

---

## 8. 服务端实现参考

### Node.js WebSocket 服务端

```javascript
const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 80, path: '/ws/smart-home' });
const devices = new Map();

wss.on('connection', (ws) => {
  let deviceId = null;
  ws.on('message', (raw) => {
    const msg = JSON.parse(raw);
    switch (msg.type) {
      case 'register':
        deviceId = msg.deviceId;
        devices.set(deviceId, ws);
        break;
      case 'snapshot':
        saveSnapshot(msg.deviceId, msg.data);
        break;
      case 'heartbeat':
        updateLastSeen(deviceId);
        break;
      default:
        if (msg.msgId) handleResponse(msg);
    }
  });
  ws.on('close', () => { if (deviceId) devices.delete(deviceId); });
});

// 向设备发指令
function sendCommand(action, params = {}) {
  const ws = devices.get('harmony_a9');
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return Promise.reject(new Error('设备不在线'));
  }
  const msgId = Date.now();
  ws.send(JSON.stringify({ type: 'command', action, msgId, ...params }));
  return new Promise((resolve) => {
    const handler = (raw) => {
      const msg = JSON.parse(raw);
      if (msg.msgId === msgId) {
        ws.off('message', handler);
        resolve(msg);
      }
    };
    ws.on('message', handler);
    setTimeout(() => { ws.off('message', handler); resolve(null); }, 30000);
  });
}
```

### Nginx 配置

```nginx
location /ws/smart-home {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}

location /api/smart-home/ {
    proxy_pass http://127.0.0.1:3000/api/smart-home/;
}
```

---

## 9. 连接生命周期

```
A9 设备                                yuanzhe.tech
  │                                       │
  │── WS握手 ─────────────────────────→   │
  │── register ───────────────────────→   │
  │── snapshot (13KB) ────────────────→   │
  │                                       │
  │←── toggle_device ─────────────────    │
  │── {success, hardwareOnline:false,     │
  │    message:"客厅主灯开关离线，         │
  │    连通测试成功"} ─────────────────→   │
  │                                       │
  │── heartbeat (30s) ────────────────→   │
  │── snapshot (5min) ────────────────→   │
  │── device_change (增量) ───────────→   │  ← 联动事件
  │                                       │
  │  ✗ 断线                               │
  │── 2s→4s→8s→...→60s 重连 ─────────→   │
  │── register + snapshot ────────────→   │
```

---

## 10. 测试验证

部署后验证:

1. **WebSocket**: 设备自动连上，发 register + snapshot
2. **ping**: 发 `{"type":"command","action":"ping","msgId":1}` → 收到 pong
3. **get_devices**: 收到 16 台设备
4. **toggle_device**: `deviceId: "light_01"` → 收到 `hardwareOnline: false` + 离线提示
5. **control_device**: `deviceId: "ac_01", subAction: "set_temp"` → 收到空调调温离线提示
6. **activate_scene**: `sceneId: "s1"` → 收到"回家场景激活离线"
7. **send_chat**: `content: "开灯"` → 收到AI回复 + 场景联动
8. **增量推送**: 设备每30s检测变化，自动推送 device_change/sensor_change

---

## 环境信息

| 项目 | 值 |
|------|------|
| 设备 IP | 192.168.1.81 (NAT内网) |
| 设备 ID | harmony_a9 |
| WebSocket | `ws://yuanzhe.tech/ws/smart-home` |
| HTTP 推送 | `http://yuanzhe.tech/api/smart-home/data` |
| 本地网关 | `http://192.168.1.81:8080` |
| 通道调试 | `http://192.168.1.81:8081/channel/status` |
| Python | 3.14.5 (ARM32 musl) |
| **协议限制** | **HTTP 80 / ws:// only** (HTTPS 443 不通) |
