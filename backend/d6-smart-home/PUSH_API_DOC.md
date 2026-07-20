# 智慧家居数据推送接口文档

> 版本: 1.0.0  
> 推送方: HarmonyOS A9 设备 (192.168.1.81)  
> 接收方: yuanzhe.tech 服务端  
> 更新日期: 2026-07-07

---

## 1. 概述

A9 鸿蒙设备后端每隔 **30 秒** 自动向 `yuanzhe.tech` 推送一次全量/增量数据。数据包含设备状态、传感器读数、场景配置、操作记录、对话历史、告警信息等。

### 推送策略

| 类型 | 频率 | 说明 |
|------|------|------|
| **全量快照** (snapshot) | 每 5 分钟 | 包含所有数据完整状态 |
| **增量事件** (event) | 每 30 秒检测 | 仅包含变化的部分 |
| **失败重试** | 最多 3 次 | 指数退避 (2s → 4s → 8s) |

---

## 2. 接口定义

### 请求

```
POST http://yuanzhe.tech/api/smart-home/data
Content-Type: application/json; charset=utf-8
Authorization: Bearer <PUSH_TOKEN>        (可选)
X-Device-Id: harmony_a9
X-Push-Version: 1.0.0
```

### 响应

```json
{
  "ok": true,
  "received": 1,
  "message": "ok"
}
```

| 状态码 | 含义 |
|--------|------|
| 200 | 成功接收 |
| 400 | 数据格式错误 |
| 401 | 认证失败 (Token无效) |
| 500 | 服务端内部错误 |

---

## 3. 数据结构

### 3.1 通用信封

所有推送数据都包裹在以下信封中：

```json
{
  "type": "snapshot | event",
  "version": "1.0.0",
  "deviceId": "harmony_a9",
  "timestamp": "2026-07-07T14:30:00.123456",
  "timestampMs": 1720339800123,
  // type=snapshot 时:
  "data": { ... },
  // type=event 时:
  "eventType": "device_change | sensor_change",
  "data": { ... }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | `snapshot` 全量快照 / `event` 增量事件 |
| version | string | 协议版本，当前 `1.0.0` |
| deviceId | string | 设备唯一标识，固定 `harmony_a9` |
| timestamp | string | ISO 8601 时间戳 |
| timestampMs | number | Unix 毫秒时间戳 |
| eventType | string | 仅 event 类型: `device_change` / `sensor_change` |
| data | object | 实际数据体 (见下) |

---

### 3.2 全量快照 (type=snapshot)

```json
{
  "type": "snapshot",
  "version": "1.0.0",
  "deviceId": "harmony_a9",
  "timestamp": "2026-07-07T14:30:00.123456",
  "timestampMs": 1720339800123,
  "data": {
    "devices": [ ... ],
    "sensors": [ ... ],
    "scenes": [ ... ],
    "operations": [ ... ],
    "sensorReadings": [ ... ],
    "chatHistory": [ ... ],
    "user": { ... },
    "alerts": [ ... ],
    "cameras": [ ... ],
    "serverStatus": { ... }
  }
}
```

---

### 3.3 设备数据 (devices[])

```json
{
  "id": "light_01",
  "name": "客厅主灯",
  "type": "light",
  "status": "online",
  "room": "客厅",
  "icon": "lightbulb",
  "primaryValue": 80,
  "isOn": true,
  "mode": null,
  "battery": null,
  "protocol": "wifi",
  "updatedAt": "2026-07-07 14:25:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 设备唯一ID，如 `light_01`, `ac_01`, `door_01` |
| name | string | 设备名称 |
| type | string | 设备类型: `light`/`ac`/`fan`/`door`/`curtain`/`alarm`/`camera`/`nfc`/`voice`/`radar`/`exhaust` |
| status | string | 在线状态: `online`/`offline`/`active` |
| room | string | 房间: `客厅`/`厨房`/`卧室`/`卫生间`/`室外`/`全局` |
| icon | string | 图标标识 |
| primaryValue | number | 主要参数值 (亮度%/温度°C/风速档/窗帘开度%) |
| isOn | boolean | 开关状态 |
| mode | string? | 运行模式 (空调: `制冷`/`制热`) |
| battery | number? | 电池电量百分比 |
| protocol | string | 通信协议: `wifi`/`starflash` |
| updatedAt | string | 最后更新时间 |

#### 完整设备列表 (16台)

| id | name | type | room |
|----|------|------|------|
| ac_01 | 客厅空调 | ac | 客厅 |
| fan_01 | 客厅吊扇 | fan | 客厅 |
| door_01 | 客厅大门 | door | 客厅 |
| alarm_01 | 蜂鸣警报 | alarm | 客厅 |
| light_01 | 客厅主灯 | light | 客厅 |
| light_05 | 客厅氛围灯 | light | 客厅 |
| camera_01 | 客厅摄像头 | camera | 客厅 |
| light_02 | 厨房灯 | light | 厨房 |
| exhaust_01 | 抽风机 | fan | 厨房 |
| curtain_01 | 智能窗帘 | curtain | 卧室 |
| light_03 | 卧室灯 | light | 卧室 |
| fan_02 | 换气扇 | fan | 卫生间 |
| light_04 | 卫生间灯 | light | 卫生间 |
| nfc_01 | NFC门禁 | nfc | 室外 |
| voice_01 | 语音中控 | voice | 全局 |
| radar_01 | 毫米波雷达 | radar | 全局 |

---

### 3.4 传感器数据 (sensors[])

```json
{
  "id": "temp_01",
  "name": "客厅温度",
  "type": "temperature",
  "group": "环境监测",
  "room": "客厅",
  "icon": "thermometer",
  "current": {
    "value": 24.5,
    "unit": "°C"
  },
  "thresholdMin": 18,
  "thresholdMax": 28,
  "protocol": "wifi",
  "isAlert": false,
  "updatedAt": "2026-07-07 14:25:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 传感器ID |
| name | string | 传感器名称 |
| type | string | 类型: `temperature`/`humidity`/`illuminance`/`air_quality`/`pir`/`smoke`/`heat`/`door_window`/`power` |
| group | string | 分组: `环境监测`/`安防`/`能耗` |
| room | string | 房间 |
| current.value | number | 当前读数 |
| current.unit | string | 单位: `°C`/`%RH`/`lx`/`AQI`/`有人`/`正常`/`kW` |
| thresholdMin | number? | 下限阈值 |
| thresholdMax | number? | 上限阈值 |
| isAlert | boolean | 是否告警 |

#### 完整传感器列表 (9个)

| id | name | type | group | unit |
|----|------|------|-------|------|
| temp_01 | 客厅温度 | temperature | 环境监测 | °C |
| humid_01 | 客厅湿度 | humidity | 环境监测 | %RH |
| light_s_01 | 客厅光照 | illuminance | 环境监测 | lx |
| air_01 | 空气质量 | air_quality | 环境监测 | AQI |
| pir_01 | 人体感应 | pir | 安防 | 有人 |
| smoke_01 | 烟雾检测 | smoke | 安防 | 正常 |
| heat_01 | 热敏火灾 | heat | 安防 | °C |
| door_s_01 | 门窗感应 | door_window | 安防 | 关闭 |
| power_01 | 总功率 | power | 能耗 | kW |

---

### 3.5 场景数据 (scenes[])

```json
{
  "id": "s1",
  "name": "回家",
  "icon": "house_fill",
  "color": "#22D3EE",
  "isActive": true,
  "description": "回家模式",
  "actions": [
    { "deviceId": "light_01", "isOn": true, "primaryValue": 80 },
    { "deviceId": "ac_01", "isOn": true, "primaryValue": 24 },
    { "deviceId": "curtain_01", "isOn": true, "primaryValue": 100 },
    { "deviceId": "door_01", "isOn": true }
  ],
  "updatedAt": "2026-07-07 14:25:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 场景ID: `s1`~`s5` |
| name | string | 场景名: `回家`/`离家`/`睡眠`/`观影`/`用餐` |
| isActive | boolean | 是否当前激活 |
| actions[].deviceId | string | 关联设备ID |
| actions[].isOn | boolean | 激活后设备开关 |
| actions[].primaryValue | number? | 激活后设备参数值 |

---

### 3.6 操作记录 (operations[])

```json
{
  "deviceId": "light_01",
  "action": "toggle",
  "params": "{\"isOn\":true}",
  "result": "ok",
  "source": "scene",
  "sceneId": "s1",
  "timestamp": "2026-07-07 14:25:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| deviceId | string | 操作的设备ID |
| action | string | 动作: `toggle`/`scene_toggle`/`set_speed`/`set_temp`/`set_brightness`/`set_mode` |
| params | string | JSON参数字符串 |
| result | string | 结果: `ok` |
| source | string | 来源: `api`/`scene`/`chat` |
| sceneId | string? | 触发的场景ID |
| timestamp | string | 操作时间 |

---

### 3.7 传感器历史读数 (sensorReadings[])

```json
{
  "sensorId": "temp_01",
  "value": 24.5,
  "unit": "°C",
  "timestamp": "2026-07-07 14:25:00"
}
```

---

### 3.8 对话历史 (chatHistory[])

```json
{
  "userId": "u001",
  "role": "user",
  "content": "打开客厅灯",
  "sceneId": null,
  "toolsUsed": "",
  "timestamp": "2026-07-07 14:25:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| userId | string | 用户ID |
| role | string | `user` / `assistant` |
| content | string | 消息内容 |
| sceneId | string? | 关联场景ID |
| toolsUsed | string | 使用的工具 |

---

### 3.9 用户信息 (user)

```json
{
  "id": "u001",
  "nickname": "用户",
  "homeName": "我的家",
  "memberCount": 3,
  "avatar": "",
  "deviceCount": 16,
  "updatedAt": "2026-07-07 14:25:00"
}
```

---

### 3.10 告警信息 (alerts[])

```json
{
  "id": "a1",
  "source": "门口摄像头",
  "content": "门口有人停留，检测到异常移动",
  "level": "warning",
  "isRead": false,
  "timestamp": 1720338420000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| level | string | `warning` / `info` / `error` |
| isRead | boolean | 是否已读 |
| timestamp | number | 毫秒时间戳 |

---

### 3.11 摄像头 (cameras[])

```json
{
  "id": "cam_01",
  "name": "客厅摄像头",
  "room": "客厅",
  "status": "online",
  "isRecording": true,
  "resolution": "1080P"
}
```

---

### 3.12 服务端状态 (serverStatus)

```json
{
  "host": "192.168.1.81",
  "port": 8080,
  "isOnline": true,
  "protocol": "wifi",
  "version": "v3",
  "pusherVersion": "1.0.0",
  "uptime": 1720339800,
  "python": "3.14.5"
}
```

---

## 4. 增量事件 (type=event)

### 4.1 设备状态变化

```json
{
  "type": "event",
  "version": "1.0.0",
  "deviceId": "harmony_a9",
  "timestamp": "2026-07-07T14:30:30.123456",
  "timestampMs": 1720339830123,
  "eventType": "device_change",
  "data": {
    "deviceId": "light_01",
    "name": "客厅主灯",
    "type": "light",
    "previous": {
      "isOn": true,
      "primaryValue": 80,
      "mode": null,
      "updatedAt": "2026-07-07 14:25:00"
    },
    "current": {
      "isOn": false,
      "primaryValue": 80,
      "mode": null,
      "updatedAt": "2026-07-07 14:30:30"
    }
  }
}
```

### 4.2 传感器数据变化

```json
{
  "type": "event",
  "version": "1.0.0",
  "deviceId": "harmony_a9",
  "timestamp": "2026-07-07T14:30:30.123456",
  "timestampMs": 1720339830123,
  "eventType": "sensor_change",
  "data": {
    "sensorId": "temp_01",
    "name": "客厅温度",
    "type": "temperature",
    "previous": {
      "value": 24.5,
      "isAlert": false,
      "updatedAt": "2026-07-07 14:25:00"
    },
    "current": {
      "value": 25.1,
      "isAlert": false,
      "updatedAt": "2026-07-07 14:30:30"
    }
  }
}
```

---

## 5. 认证方式

### 方式一: Bearer Token (推荐)

```
Authorization: Bearer <PUSH_TOKEN>
```

设置环境变量:
```bash
export PUSH_TOKEN="your-secret-token-here"
```

### 方式二: 无认证

不设置 `PUSH_TOKEN` 环境变量即可。推送请求不带 Authorization 头。

---

## 6. 接收端实现建议

### 最小实现 (Node.js / Express 示例)

```javascript
app.post('/api/smart-home/data', (req, res) => {
  const { type, deviceId, timestamp, data, eventType } = req.body;
  
  // 1. 校验 deviceId
  if (deviceId !== 'harmony_a9') {
    return res.status(400).json({ ok: false, message: 'unknown device' });
  }
  
  // 2. 按类型处理
  if (type === 'snapshot') {
    // 全量快照 → 覆盖存储
    db.devices.upsert(data.devices);
    db.sensors.upsert(data.sensors);
    db.scenes.upsert(data.scenes);
    // ...
  } else if (type === 'event') {
    // 增量事件 → 更新对应记录
    if (eventType === 'device_change') {
      db.devices.update(data.deviceId, data.current);
    } else if (eventType === 'sensor_change') {
      db.sensors.update(data.sensorId, data.current);
    }
  }
  
  res.json({ ok: true, received: 1, message: 'ok' });
});
```

### 数据库设计建议

```sql
-- 设备状态表 (全量覆盖)
CREATE TABLE devices (
  id          TEXT PRIMARY KEY,
  name        TEXT,
  type        TEXT,
  status      TEXT,
  room        TEXT,
  primary_value INTEGER,
  is_on       BOOLEAN,
  mode        TEXT,
  updated_at  TIMESTAMP
);

-- 传感器读数表 (追加)
CREATE TABLE sensor_readings (
  id          SERIAL PRIMARY KEY,
  sensor_id   TEXT,
  value       REAL,
  unit        TEXT,
  created_at  TIMESTAMP DEFAULT NOW()
);

-- 操作日志表 (追加)
CREATE TABLE operations (
  id          SERIAL PRIMARY KEY,
  device_id   TEXT,
  action      TEXT,
  params      JSONB,
  source      TEXT,
  scene_id    TEXT,
  created_at  TIMESTAMP DEFAULT NOW()
);

-- 设备状态历史表 (增量事件追加)
CREATE TABLE device_state_history (
  id          SERIAL PRIMARY KEY,
  device_id   TEXT,
  previous    JSONB,
  current     JSONB,
  created_at  TIMESTAMP DEFAULT NOW()
);
```

---

## 7. 推送频率与数据量估算

| 数据类型 | 单次大小 | 频率 | 日均量 |
|----------|----------|------|--------|
| 全量快照 | ~15 KB | 每5分钟 | ~4.3 MB |
| 增量事件 | ~0.5 KB | 每30秒(有变化时) | ~0.7 MB |
| **合计** | | | **~5 MB/天** |

---

## 8. 错误处理

### 推送端 (A9设备)

- HTTP 非 2xx → 重试 (最多3次, 退避 2s/4s/8s)
- 超时 (15s) → 视为失败，入队重试
- 连续失败 → 数据保留在本地 SQLite 队列，不丢失
- 队列清理: 已推送数据保留7天，失败数据保留30天

### 接收端 (yuanzhe.tech)

建议实现:
- 请求体大小限制: 建议 ≥ 1MB
- 超时响应: 建议在 10s 内返回
- 幂等性: 同一 `timestampMs` 的数据重复推送不产生副作用
- 健康检查: 可实现 `GET /api/smart-home/health` 返回 `{"ok":true}`

---

## 9. 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| PUSH_URL | `http://yuanzhe.tech/api/smart-home/data` | 推送目标URL |
| PUSH_TOKEN | (空) | Bearer Token 认证 |
| PUSH_INTERVAL | `30` | 推送检测间隔(秒) |
