# 智能家居中央控制 — 调用接口速查

> 本文档只保留「设备地址」和「可调用的接口」，其他实现细节已删除。

---

## 1. 设备地址信息

所有地址集中在 `devices.json`：

```json
{
  "living_room": { "name": "living-room-hi3861", "ip": "192.168.1.62", "port": 8000 },
  "kitchen":     { "name": "kitchen-h3863",     "ip": "192.168.1.23", "port": 8000, "alarm_udp_port": 8001, "light_command_inverted": false },
  "bathroom":    { "name": "bathroom-h3863",    "ip": "192.168.1.63", "port": 8000, "light_command_inverted": false },
  "bedroom":     { "name": "bedroom-h3863",     "ip": "192.168.1.64", "port": 8000, "light_command_inverted": false },
  "defaults":    { "timeout_seconds": 3.0, "monitor_interval_seconds": 1.0 }
}
```

| 区域 | 设备 | IP | TCP 端口 | UDP 端口 | 备注 |
|---|---|---|---|---|---|
| 客厅/全局 | Hi3861 | `192.168.1.62` | `8000` | - | 门禁、温湿度、红外空调、蜂鸣器、客厅灯、NFC 事件 |
| 厨房 | H3863/WS63 | `192.168.1.23` | `8000` | `8001`（报警广播） | GP00 灯、GP03 烟雾、GP07/ADC0 热敏 |
| 卫生间 | H3863 | `192.168.1.63` | `8000` | - | GP00 灯、TB6612/N20 排风扇 |
| 卧室 | H3863 | `192.168.1.64` | `8000` | - | GP00 灯、28BYJ-48/ULN2003 窗帘、双限位 |

---

## 2. CLI 命令行调用接口

统一入口：

```powershell
python central_controller.py [全局选项] <子命令>
```

全局选项：

| 选项 | 说明 |
|---|---|
| `--config <path>` | 指定配置文件，默认 `./devices.json` |
| `--timeout <秒>` | TCP 连接/读取超时，默认 `3.0` |

---

### 2.1 全局状态

```powershell
# 查询所有设备状态（只读，最安全）
python central_controller.py status
```

### 2.2 客厅（living）

```powershell
python central_controller.py living temp          # 查询温湿度
python central_controller.py living event         # 查询最新 NFC/事件
python central_controller.py living light query   # 查询客厅灯状态
python central_controller.py living light on      # 开客厅灯
python central_controller.py living light off     # 关客厅灯
python central_controller.py living light auto    # 客厅灯自动模式
python central_controller.py living light test    # 客厅灯测试
python central_controller.py living door query    # 查询门状态
python central_controller.py living door open     # 开门
python central_controller.py living door close    # 关门
python central_controller.py living ac query      # 查询空调状态
python central_controller.py living ac on         # 开空调
python central_controller.py living ac off        # 关空调
python central_controller.py living beep query    # 查询蜂鸣器状态
python central_controller.py living beep on       # 打开蜂鸣器
python central_controller.py living beep off      # 关闭蜂鸣器
python central_controller.py living beep alarm    # 蜂鸣器报警音
```

### 2.3 厨房（kitchen）

```powershell
python central_controller.py kitchen status       # 查询厨房状态（烟雾、温度、灯）
python central_controller.py kitchen light on     # 厨房灯全开
python central_controller.py kitchen light off    # 厨房灯关闭
python central_controller.py kitchen light 50     # 厨房灯亮度设为 50%（0-100）
```

### 2.4 卫生间（bathroom）

```powershell
python central_controller.py bathroom status      # 查询卫生间灯和风扇状态
python central_controller.py bathroom light on    # 卫生间灯全开
python central_controller.py bathroom light off   # 卫生间灯关闭
python central_controller.py bathroom light 50    # 卫生间灯亮度设为 50%（0-100）
python central_controller.py bathroom fan stop    # 风扇停止
python central_controller.py bathroom fan forward 100   # 风扇正转，速度 100%
python central_controller.py bathroom fan reverse 60    # 风扇反转，速度 60%
```

### 2.5 卧室（bedroom）

```powershell
python central_controller.py bedroom status       # 查询卧室灯和窗帘状态
python central_controller.py bedroom light on     # 卧室灯全开
python central_controller.py bedroom light off    # 卧室灯关闭
python central_controller.py bedroom light 50     # 卧室灯亮度设为 50%（0-100）
python central_controller.py bedroom curtain open       # 窗帘完全打开（position=100）
python central_controller.py bedroom curtain close      # 窗帘完全关闭（position=0）
python central_controller.py bedroom curtain position 50 # 窗帘开到 50% 位置
python central_controller.py bedroom curtain stop       # 立即停止窗帘电机
python central_controller.py bedroom curtain home       # 窗帘回零（找关闭限位）
```

### 2.6 报警监控（monitor）

```powershell
# 只读监听厨房报警
python central_controller.py monitor

# 报警上升沿触发客厅蜂鸣器，恢复后关闭蜂鸣器
python central_controller.py monitor --trigger-buzzer --clear-buzzer
```

监控可选参数：

| 选项 | 说明 |
|---|---|
| `--interval <秒>` | 轮询间隔，默认 `1.0` |
| `--udp-port <port>` | UDP 监听端口，默认 `8001` |
| `--trigger-buzzer` | 报警时触发客厅蜂鸣器 |
| `--clear-buzzer` | 报警恢复后关闭客厅蜂鸣器（需配合 `--trigger-buzzer`） |

---

## 3. Python 函数调用接口

以下函数均在 `central_controller.py` 中定义，可直接导入调用。

### 3.1 配置与底层通信

```python
config = load_config(path)                          # 加载 devices.json
ip, port = device_endpoint(config, "kitchen")       # 获取设备 IP 和端口
packet = make_packet(command, value1=0, value2=0)   # 构造 32 字节 CRC32 二进制包
content = parse_packet(packet)                      # 解析 32 字节二进制包
content = binary_command(ip, port, cmd, v1, v2, timeout)  # 发二进制包并返回 content
reply = text_command(ip, port, "TEMP QUERY\n", timeout)   # 发 ASCII 文本命令并返回字符串
```

### 3.2 厨房

```python
# 查询厨房状态：烟雾、温度报警、灯亮度等
status = kitchen_status(config, timeout)

# 设置厨房灯亮度，brightness 为 0-100（会自动处理 light_command_inverted）
status = kitchen_set_light(config, brightness, timeout)
```

返回字段示例：

```python
{
  "device": "kitchen",
  "ip": "192.168.1.23",
  "port": 8000,
  "smoke_level": 1,
  "smoke_alarm": 0,
  "temp_alarm": 0,
  "alarm": 0,
  "light_on": 0,
  "brightness": 50,
  "thermal_mv": 1630
}
```

### 3.3 卫生间

```python
# 查询卫生间灯和风扇状态
status = bathroom_status(config, timeout)

# 设置卫生间灯亮度，brightness 为 0-100
status = bathroom_set_light(config, brightness, timeout)

# 控制排风扇：direction 为 "stop"/"forward"/"reverse"，speed 为 0-100
status = bathroom_set_fan(config, direction, speed, timeout)
```

返回字段示例：

```python
{
  "device": "bathroom",
  "ip": "192.168.1.63",
  "port": 8000,
  "light_brightness": 50,
  "motor_direction": 1,
  "motor_speed": 100,
  "motor_running": 1
}
```

### 3.4 卧室

```python
# 查询卧室灯和窗帘状态
status = bedroom_status(config, timeout)

# 设置卧室灯亮度，brightness 为 0-100
status = bedroom_set_light(config, brightness, timeout)

# 设置窗帘目标位置，position 为 0-100
status = bedroom_set_curtain(config, position, timeout)

# 窗帘动作：action 为 "stop" 或 "home"
status = bedroom_curtain_action(config, action, timeout)
```

返回字段示例：

```python
{
  "device": "bedroom",
  "ip": "192.168.1.64",
  "port": 8000,
  "light_brightness": 50,
  "curtain_position": 50,
  "curtain_target": 50,
  "curtain_moving": 0,
  "curtain_homed": 1,
  "close_limit": 1,
  "open_limit": 0,
  "last_error": 0
}
```

### 3.5 客厅

```python
# 门禁控制：action 为 "open"/"close"/"query"
result = living_door(config, action, timeout)

# 文本命令服务：service 为 "temp"/"event"/"ac"/"beep"/"light"，action 为对应动作
result = living_text(config, service, action, timeout)
```

常用组合：

```python
living_text(config, "temp", "query", timeout)     # 查询温湿度
living_text(config, "event", "query", timeout)    # 查询事件
living_text(config, "ac", "on", timeout)          # 开空调
living_text(config, "beep", "alarm", timeout)     # 蜂鸣器报警
living_text(config, "light", "on", timeout)       # 开客厅灯
```

### 3.6 高层辅助函数

```python
# 查询所有设备状态，单台失败不会阻塞其他设备
result = all_status(config, timeout)

# 安全查询包装，返回 {"online": bool, "status": ...} 或 {"online": False, "error": ...}
result = safe_query(name, callback)

# 监控厨房报警，可选联动客厅蜂鸣器
monitor(config, timeout, interval, trigger_buzzer, clear_buzzer, udp_port)
```

---

## 4. 常用批处理快捷方式

| 文件 | 等价命令 | 作用 |
|---|---|---|
| `01_check_all_devices.bat` | `python central_controller.py status` | 只读检查所有设备 |
| `02_monitor_readonly.bat` | `python central_controller.py monitor` | 持续监听厨房报警 |
| `03_monitor_alarm_linkage.bat` | `python central_controller.py monitor --trigger-buzzer --clear-buzzer` | 报警联动客厅蜂鸣器 |
