# 边缘端设备知识点与中控接入说明

本文档用于给中央控制设备、上位机、语音网关或后续云端服务快速了解当前 Hi3861 边缘端设备的能力、协议和接入方式。

当前边缘端核心固件为：

```text
src/vendor/pzkj/pz_hi3861/demo/60_multi_service_hub
```

当前编译入口为：

```text
src/vendor/pzkj/pz_hi3861/demo/BUILD.gn
features = [
  "60_multi_service_hub:template",
]
```

## 1. 设备定位

当前 Hi3861 板子作为智能家居边缘端控制器，负责直接连接和控制本地硬件模块。

中央控制设备不需要直接操作 GPIO、UART、I2C、PWM，只需要通过 WiFi TCP 协议访问边缘端即可。

边缘端当前承担：

- 连接 WiFi，作为 TCP Server 暴露控制端口。
- 接收中控或 PC 客户端命令。
- 控制门禁舵机、空调红外模块、蜂鸣器。
- 采集温湿度、光敏、NFC 刷卡状态。
- OLED 本地显示状态。
- 缓存被动事件，供语音桥或中控轮询后播报。

## 2. 网络信息

当前固件内 WiFi 配置：

```text
SSID     : TEST-2.4GHz
PASSWORD : <DOOR_PASSWORD>
```

边缘端作为 TCP Server：

```text
IP   : 由路由器分配，例如 192.168.1.62
PORT : 8000
```

所有功能尽量统一在一个端口：

```text
192.168.1.62:8000
```

中控接入时建议先做健康检查：

```powershell
python .\hub_client.py 192.168.1.62 scan
```

## 3. 当前硬件能力

| 模块 | 当前状态 | 边缘端作用 | 中控是否可控 |
|---|---:|---|---:|
| 门禁舵机 | 已实现 | 开门、关门、查询状态 | 是 |
| DHT11 温湿度 | 已实现 | 后台采样、查询、OLED 显示 | 可查询 |
| 红外空调 | 已实现 | 开空调、关空调、查询状态 | 是 |
| 蜂鸣器 | 已实现 | 打开、关闭、报警 | 是 |
| OLED | 已实现 | 显示 IP、温湿度、门禁、空调状态 | 本地显示 |
| PN532 NFC | 已实现 | 刷卡开门、发布刷卡事件 | 被动事件 |
| 光敏模块 | 已接入/预留 | 采集光照，用于后续自动调光 | 后续扩展 |
| 语音模块 | 通过 PC 桥接 | 语音命令转 WiFi 控制，接收播报帧 | 间接支持 |

## 4. 硬件连接知识点

当前关键引脚约定：

| 功能 | 引脚/接口 | 说明 |
|---|---|---|
| 红外空调 UART | GPIO0 / GPIO1 | GPIO0 -> 红外模块 RX，GPIO1 <- 红外模块 TX，GND 共地 |
| 门禁舵机 | GPIO6 | 舵机控制信号 |
| DHT11 | GPIO7 | 温湿度采集 |
| 蜂鸣器 | GPIO12 | 后来从 IO3/IO5 调整到 IO12，避免复位误响 |
| OLED | I2C0 GPIO9/GPIO10 | GPIO9=SCL，GPIO10=SDA |
| PN532 NFC | I2C0 GPIO9/GPIO10 | 与 OLED 共 I2C 总线 |
| PN532 IRQ/RSTO | 可不接 | 当前能识别 UID 时可先不接，避免影响烧录复位 |
| 光敏模块 | ADC | 用于后续光照采集和自动调光策略 |

### 4.1 当前引脚位置与接线表

| 功能 | Hi3861 资源/引脚 | 板子/模块接线位置 | 接线说明 | 注意事项 |
|---|---|---|---|---|
| 红外空调模块 | GPIO0 / GPIO1 UART | IO0 / IO1 | GPIO0 -> 红外模块 RX，GPIO1 <- 红外模块 TX，GND 共地 | 波特率 115200，使用 AFN22 外部码发送 |
| 门禁舵机 | GPIO6 | 舵机信号线 | GPIO6 -> 舵机信号，舵机 VCC/GND 单独供电或共地 | 舵机必须和板子 GND 共地 |
| DHT11 温湿度 | GPIO7 | DHT11 DATA | VCC、GND、DATA(GPIO7) | OLED 显示 0C/0 时优先查 DATA 线和供电 |
| OLED 屏 | I2C0 GPIO9/GPIO10 | SCL / SDA | GPIO9=SCL，GPIO10=SDA，VCC3.3，GND | 与 PN532 共用 I2C 总线 |
| PN532 NFC | I2C0 GPIO9/GPIO10 | SCL / SDA | GPIO9=SCL，GPIO10=SDA，VCC3.3，GND | IRQ/RSTO 当前可不接，避免影响烧录复位 |
| 蜂鸣器 | GPIO12 | IO12 | GPIO12 -> 蜂鸣器控制脚，VCC/GND 正常接 | 已避开 IO3/IO5 复位误响问题 |
| 光敏模块 | ADC5 / GPIO11 | R_ADC / ADC5 | 光敏 AO -> ADC5(GPIO11)，VCC3.3，GND | 用 `LIGHT QUERY` 看 ADC，确认暗时变大还是变小 |
| 新增 LED 灯 | GPIO13 | TRIG | 两线小电流 LED：LED VCC -> 3.3V，LED GND -> TRIG(GPIO13) | 当前代码为低电平点亮；避开 PN532 的 GPIO5/RSTO 和 GPIO2/IRQ |

### 4.2 LED + 光敏控制设计

LED 灯默认自动模式，既支持 WiFi 远程控制，也支持光敏自动开灯。当前代码把外接 `TRIG/GPIO13` 当作低电平吸电流开关使用。

如果你的 LED 只有 `VCC` 和 `GND` 两根线：

```text
小电流 LED 模块：
LED VCC -> 3.3V
LED GND -> TRIG / GPIO13
```

这叫低电平吸电流接法：`LIGHT ON` 时 GPIO13 拉低，电流从 3.3V 经过 LED 流入 GPIO13，灯亮；`LIGHT OFF` 时 GPIO13 拉高，灯灭。

光敏自动模式当前按 `ADC 高=暗、ADC 低=亮` 处理：ADC >= 1500 判定为暗并开灯，ADC <= 1100 判定为亮并关灯，中间区间保持原状态，避免灯频繁闪烁。

不要把两线 LED 直接接成 `VCC -> 3.3V`、`GND -> GND`，否则它会一直亮，软件无法控制。

如果 LED 是灯带、大功率灯、5V 高亮模块或电流明显较大：

```text
GPIO2 -> 继电器/MOS 管控制端
LED VCC -> 外部电源正极
LED GND -> 继电器/MOS 管开关回路 -> 外部电源负极
外部电源 GND -> Hi3861 GND 共地
```

这种情况下 GPIO2 只负责“控制开关”，不能直接给灯供电。

当前策略：

- `LIGHT OFF`：手动关闭灯，并退出自动模式。
- `LIGHT ON`：手动打开灯，并退出自动模式。
- `LIGHT AUTO`：进入自动模式，板子每秒读取一次 ADC5/GPIO11 的光敏值，判断太暗时自动打开 LED。
- `LIGHT TEST`：GPIO2 原始高低电平闪烁测试，用于判断 LED 接法和 IO2 是否正确。
- `LIGHT QUERY`：查询当前灯状态、光敏 ADC 值、是否判定为暗、阈值和方向。

当前默认阈值：

```text
LIGHT_DARK_THRESHOLD   = 1500
LIGHT_BRIGHT_THRESHOLD = 2200
LIGHT_DARK_IS_LOW      = 1
```

含义：先按“ADC 越低越暗”处理；ADC <= 1500 判定为暗并开灯，ADC >= 2200 判定为亮并关灯。这里用了两个阈值做回差，避免临界值附近频繁闪烁。

如果实测发现你的光敏模块是“ADC 越高越暗”，只需要把源码里的 `LIGHT_DARK_IS_LOW` 改成 `0`，再重新编译烧录。

建议校准方法：

```powershell
python .\hub_client.py 192.168.1.62 light query
```

然后分别记录：

- 正常室内光下的 `adc=...`
- 用手遮住光敏时的 `adc=...`
- 用手机手电照光敏时的 `adc=...`

根据这三个值再决定是否调整 `LIGHT_DARK_THRESHOLD` / `LIGHT_BRIGHT_THRESHOLD`。

LED 接线不确定时，先执行：

```powershell
python .\hub_client.py 192.168.1.62 light test
```

这个命令会让灯控 GPIO 在 0/1 之间闪烁 3 次，每个电平保持 0.5 秒。若 `LED VCC -> 3.3V，LED GND -> GPIO`，应在 GPIO=0 时亮；若 `LED VCC -> GPIO，LED GND -> GND`，应在 GPIO=1 时亮。两种接法都不闪，说明实际接到的不是当前灯控 GPIO，或该 LED 模块不能由 GPIO 直接驱动。

### 4.3 LED 常亮排查结论

如果 `LIGHT` 命令返回里已经出现 GPIO 真实电平切换，例如：

```text
LIGHT ON  -> state=ON,gpio=0
LIGHT OFF -> state=OFF,gpio=1
```

说明软件命令、TCP 协议、GPIO2 输出控制都已经生效。此时 LED 仍然常亮，问题不在代码，而在 LED 接线回路或 LED 模块本身。

当前固定采用低电平点亮方案：

```text
LED VCC -> 3.3V
LED GND -> GPIO2
```

该方案参考 `bearpi-pico_h3863-master/application/ws63/ws63_liteos_application/kitchen_controller.c` 的 active-low 灯控思路：初始化关闭时 GPIO 输出高电平，开灯时 GPIO 输出低电平，并关闭内部上下拉，避免 GPIO 下拉导致上电后常亮。

这条回路的含义是：

- `GPIO2=0`：GPIO2 吸电流，LED 应该亮。
- `GPIO2=1`：两端都接近高电平，LED 应该灭。

若 `GPIO2=1` 时 LED 仍然亮，按下面顺序排查：

1. 确认 LED 的 `GND` 没有同时接到板子 `GND`，只能接到 `GPIO2`。
2. 确认 LED 的 `VCC` 只接 `3.3V`，不要再接其它电源或模块供电端。
3. 用万用表量 `GPIO2` 对 `GND` 电压：`LIGHT ON` 应接近 0V，`LIGHT OFF` 应接近 3.3V。
4. 如果电压正确但灯仍常亮，说明这个 LED 模块内部不是普通两线 LED，可能自带驱动/反接保护/并联供电路径，需要换普通小 LED 或用继电器/MOS 管控制。
5. 如果电压不变，说明实际插到的不是 GPIO2，对照开发板丝印重新确认 IO2 位置。

### 4.4 LED 亮度低的原因和解决方案

如果 LED 能跟随 `LIGHT ON/OFF` 变化，但亮度明显偏低，通常不是代码问题，而是 GPIO2 直接带 LED 的电流能力有限。

当前低电平吸电流接法：

```text
LED VCC -> 3.3V
LED GND -> GPIO2
```

这种接法只适合验证“能否控制”，不适合作为真正室内照明。GPIO 只能提供/吸收很小的电流，所以两线 LED 可能会亮，但亮度偏低。

推荐方案：

| 方案 | 适用情况 | 接法要点 |
|---|---|---|
| 普通小 LED 直接接 GPIO2 | 只做演示状态灯 | 保持当前接法即可 |
| 继电器模块 | 控制 5V 灯、灯带、小灯泡 | GPIO2 控制继电器 IN，灯由外部电源供电 |
| MOS 管模块 | 控制 LED 灯带/高亮 LED | GPIO2 控制 MOS 管栅极，MOS 管负责灯的电源通断 |
| 三极管驱动 | 小电流 LED 增亮 | GPIO2 只控制三极管，LED 电流走外部电源 |

如果暂时没有三极管、MOS 管或继电器模块，可以先保留当前方案做功能演示：WiFi 能开关灯、光敏能触发自动开灯即可。后续为了亮度和安全性，建议加一个低电平/高电平触发继电器模块或 MOS 管开关模块。

注意：

- 所有外设必须共地。
- 红外模块已经确认需要使用模块协议封装后的 AFN22 外部码发送方式，而不是直接裸发 A2 原始数据。
- PN532 当前 `NFC_ALLOW_ANY_CARD=1`，即任意识别到的卡都可开门；后续可以改成 UID 白名单。

## 5. TCP 协议总览

边缘端统一监听：

```text
TCP 8000
```

根据首包内容区分协议：

| 功能 | 协议类型 | 客户端发送 |
|---|---|---|
| 门禁 | 32 字节二进制包 | `AA 55 ... 55 AA` |
| 温湿度流 | 文本 | `TEMP\n` |
| 温湿度单次查询 | 文本 | `TEMP QUERY\n` |
| 空调 | 文本 | `AC ON\n` / `AC OFF\n` / `AC QUERY\n` |
| 蜂鸣器 | 文本 | `BEEP ON\n` / `BEEP OFF\n` / `BEEP ALARM\n` / `BEEP QUERY\n` |
| 被动事件 | 文本 | `EVENT QUERY\n` |

## 6. 门禁协议

门禁使用 32 字节二进制协议。

包结构：

```text
0-1   : AA 55
2-5   : CRC32，小端，计算 content 24 字节
6-29  : content，共 24 字节
30-31 : 55 AA
```

content 关键字段：

```text
content[0] = cmd
content[1] = room
content[2] = value
```

当前定义：

```text
cmd=0x00 : 查询门状态
cmd=0x01 : 设置门状态
room=0   : 当前默认门
value=0  : 关门
value=1  : 开门
```

PC 测试命令：

```powershell
python .\hub_client.py 192.168.1.62 door open
python .\hub_client.py 192.168.1.62 door close
python .\hub_client.py 192.168.1.62 door query
```

## 7. 温湿度协议

单次查询：

```text
TEMP QUERY\n
```

返回示例：

```text
OK,type=TEMP,temp=24,humi=51,alarm=NONE,ip=192.168.1.62,port=8000
```

持续流：

```text
TEMP\n
```

返回可能包含：

```text
BOOT,ip=192.168.1.62,port=8000,proto=TEMP,sample_s=2
STATUS,type=DHT11_READY,temp=24,humi=51,alarm=NONE,ip=192.168.1.62
DATA,temp=24,humi=51,alarm=NONE,ip=192.168.1.62
ALARM,temp=31,humi=80,alarm=TEMP_AND_HUMI_HIGH,ip=192.168.1.62
```

PC 测试命令：

```powershell
python .\hub_client.py 192.168.1.62 temp --query
python .\hub_client.py 192.168.1.62 temp --count 10
```

设计建议：

- 边缘端负责采集和上报。
- 中控负责策略判断，例如温度过高是否开空调、湿度过高是否报警。
- 不建议把复杂场景逻辑全部写死在板端，便于后续改规则。

## 8. 空调协议

空调通过 WiFi 命令触发板端 UART 控制红外模块。

文本命令：

```text
AC ON\n
AC OFF\n
AC QUERY\n
```

返回示例：

```text
OK,type=AC,action=ON,state=ON,baud=115200,ip=192.168.1.62,port=8000,error=0,enabled=1
```

PC 测试命令：

```powershell
python .\hub_client.py 192.168.1.62 ac on
python .\hub_client.py 192.168.1.62 ac off
python .\hub_client.py 192.168.1.62 ac query
```

重要经验：

- 红外模块波特率为 `115200`。
- PC 工具直发 A2 原始码可成功，但板端不能简单裸发 A2。
- 当前可用方案是把红外码封装为模块要求的 AFN22 外部码帧，再分包发送。

## 9. 蜂鸣器协议

文本命令：

```text
BEEP ON\n
BEEP OFF\n
BEEP ALARM\n
BEEP QUERY\n
```

返回示例：

```text
OK,type=BEEP,action=ALARM,state=ON,ip=192.168.1.62,port=8000,error=0
```

PC 测试命令：

```powershell
python .\hub_client.py 192.168.1.62 beep on
python .\hub_client.py 192.168.1.62 beep off
python .\hub_client.py 192.168.1.62 beep alarm
python .\hub_client.py 192.168.1.62 beep query
```

注意：

- 蜂鸣器最终建议接 `GPIO12`。
- `BEEP ALARM` 是短促报警模式，结束后状态可能回到 OFF。
- 中控可根据温湿度、NFC、雷达、SOS 等事件决定是否触发蜂鸣器。

## 10. NFC 门禁能力

当前 PN532 工作在 I2C 模式。

当前行为：

- 识别到卡 UID。
- 如果允许，则本地直接打开门禁舵机。
- 发布被动事件，供中控/语音桥轮询播报。

串口日志示例：

```text
[hub-nfc] card UID=E077DE5C
[hub-nfc] allowed UID, door open ret=0 state=1 angle=...
[hub-event] seq=1 code=1 detail=E077DE5C
```

当前固件中：

```text
NFC_ALLOW_ANY_CARD = 1
```

后续改为正式门禁时建议：

- 关闭任意卡开门。
- 使用 UID 白名单。
- NFC 成功刷卡只作为认证事件，中控可决定是否开门。

## 11. 被动事件 EVENT QUERY

这是给中央控制设备和语音播报系统用的统一被动事件接口。

请求：

```text
EVENT QUERY\n
```

返回：

```text
OK,type=EVENT,seq=1,code=1,detail=E077DE5C,ip=192.168.1.62,port=8000
```

字段说明：

| 字段 | 含义 |
|---|---|
| seq | 事件递增序号，中控用它判断是否有新事件 |
| code | 事件类型 |
| detail | 事件详情，例如 UID、报警类型 |
| ip/port | 当前边缘端地址 |

当前事件码：

| code | 事件 |
|---:|---|
| 0 | 无事件/启动 |
| 1 | NFC 允许，已开门 |
| 2 | NFC 拒绝 |
| 3 | 温湿度告警 |
| 4 | 温湿度恢复正常 |
| 5 | 门禁打开 |
| 6 | 门禁关闭 |
| 7 | 空调打开 |
| 8 | 空调关闭 |
| 9 | 蜂鸣器报警 |
| 10 | 蜂鸣器关闭 |

PC 测试命令：

```powershell
python .\hub_client.py 192.168.1.62 event query
```

中控轮询建议：

- 轮询间隔：`0.5s ~ 1s`
- 只在 `seq` 变化时处理事件。
- 不要因为 `code` 相同就忽略，必须以 `seq` 为准。

伪代码：

```python
last_seq = None

while True:
    event = tcp_send("EVENT QUERY\n")
    if last_seq is None:
        last_seq = event.seq
    elif event.seq != last_seq:
        last_seq = event.seq
        handle_event(event.code, event.detail)
    sleep(0.5)
```

## 12. 语音桥接

语音模块当前通过电脑串口接入，电脑运行：

```powershell
python .\voice_bridge.py COM12 192.168.1.62 --raw
```

作用：

- 从语音模块串口接收命令帧。
- 转换成 WiFi TCP 命令发送给边缘端。
- 收到边缘端结果后，向语音模块回发播报帧。
- 后台轮询 `EVENT QUERY`，支持 NFC 等被动播报。

当前支持的二进制语音命令帧：

| 语音模块输入帧 | 动作 | 发给边缘端 | 回复语音模块 |
|---|---|---|---|
| `AA 55 00 04 FB` | 空调打开 | `AC ON` | `AA 55 01 03 FB` |
| `AA 55 00 05 FB` | 空调关闭 | `AC OFF` | `AA 55 01 04 FB` |
| `AA 55 00 06 FB` | 空调状态 | `AC QUERY` | `AA 55 00 06 FB` |
| `AA 55 00 07 FB` | 蜂鸣器报警 | `BEEP ALARM` | `AA 55 01 05 FB` |
| `AA 55 00 08 FB` | 蜂鸣器关闭 | `BEEP OFF` | `AA 55 01 06 FB` |
| `AA 55 00 09 FB` | 查询温湿度 | `TEMP QUERY` | `AA 55 01 07 FB` |
| `AA 55 00 0F FB` | 我回来了 | `door open` | `AA 55 01 01 FB` |
| `AA 55 00 10 FB` | 我要出去 | `door close` | `AA 55 01 02 FB` |

当前预留但尚未接入实物控制的帧：

| 帧 | 计划功能 |
|---|---|
| `AA 55 00 11 FB` | 客厅灯打开 |
| `AA 55 00 12 FB` | 客厅灯关闭 |
| `AA 55 00 13 FB` | 卧室灯打开 |
| `AA 55 00 14 FB` | 卧室灯关闭 |
| `AA 55 00 15 FB` | 厨房灯打开 |
| `AA 55 00 16 FB` | 厨房灯关闭 |
| `AA 55 00 17 FB` | 卫生间风扇打开 |
| `AA 55 00 18 FB` | 卫生间风扇关闭 |
| `AA 55 00 19 FB` | 窗帘打开 |
| `AA 55 00 1A FB` | 窗帘关闭 |
| `AA 55 00 1B FB` | 卫生间灯打开 |
| `AA 55 00 1C FB` | 卫生间灯关闭 |
| `AA 55 00 20 FB` | 雷达开启 |
| `AA 55 00 21 FB` | 雷达关闭 |

被动事件播报映射：

| 边缘端事件 | 语音播报帧 |
|---|---|
| NFC 允许 | `AA 55 01 01 FB` |
| NFC 拒绝 | `AA 55 01 05 FB` |
| 温湿度告警 | `AA 55 01 05 FB` |
| 温湿度恢复 | `AA 55 01 07 FB` |

注意：

- 语音模块是否真正播报，取决于固件/协议表里这些回复帧是否绑定了播报词。
- 如果刷 NFC 后看到 `reply sent` 但没有声音，需要检查语音模块播报词协议表。

## 13. 中控推荐架构

推荐把系统拆成三层：

```text
语音模块 / App / Web / 云端
          |
          v
中央控制设备 / 上位机 / 网关
          |
          v
Hi3861 边缘端设备 TCP 8000
          |
          v
本地硬件：门禁、空调、蜂鸣器、温湿度、NFC、OLED、光敏
```

中控职责：

- 统一管理场景逻辑。
- 轮询 `EVENT QUERY`。
- 根据事件触发语音播报、报警、记录日志。
- 下发控制命令。
- 做策略判断，例如：
  - 温度高于阈值 -> 开空调。
  - NFC 刷卡成功 -> 播报“欢迎回家”。
  - 烟雾/火焰/雷达异常 -> 蜂鸣器报警并通知用户。

边缘端职责：

- 保持本地硬件控制稳定。
- 不承载过多复杂业务策略。
- 即使中控断开，也能保留基本本地能力，例如 NFC 开门。

## 14. 当前状态和已知注意点

当前源码已经支持 `EVENT QUERY`，但必须确认新版固件已经烧录进板子。

验证新版固件是否生效：

```powershell
python .\hub_client.py 192.168.1.62 event query
```

正确返回应类似：

```text
OK,type=EVENT,seq=0,code=0,detail=BOOT,ip=192.168.1.62,port=8000
```

如果返回旧版错误：

```text
ERR,unknown_command,use TEMP text, BEEP text, AC text, or 32-byte door binary packet
```

说明板子仍然运行旧固件，必须重新烧录。

烧录注意：

- DevEco 上传端口当前应为 `COM6`。
- 语音模块通常为 `COM12`。
- 烧录前关闭占用 `COM6` 的串口监视器。
- 如果 HiBurn 等待连接，按一下开发板复位键。

## 15. 给中控设备的最小接入清单

中控只需要实现以下 TCP 能力：

1. 建立 TCP 连接到：

```text
192.168.1.62:8000
```

2. 文本命令以 `\n` 结尾。

3. 二进制门禁命令按 32 字节包发送。

4. 周期性轮询：

```text
EVENT QUERY\n
```

5. 至少支持以下动作：

```text
AC ON
AC OFF
AC QUERY
BEEP ALARM
BEEP OFF
BEEP QUERY
TEMP QUERY
EVENT QUERY
```

6. 对门禁使用 32 字节协议，或复用 `hub_client.py` 中的打包逻辑。

7. 收到事件后按 `seq` 去重，不按 `code` 去重。

## 16. 后续扩展方向

优先级建议：

1. 确认新版固件烧录成功，使 `EVENT QUERY` 生效。
2. 对齐语音模块播报帧和播报词。
3. 将 NFC 从任意卡开门改为 UID 白名单。
4. 将光敏模块数据通过 TCP 查询接口暴露给中控。
5. 增加灯光实际控制模块，再接入客厅灯、卧室灯、卫生间灯。
6. 增加烟雾/火焰/雷达等安全传感器，统一进入事件系统。
7. 中控侧实现场景模式：我回来了、我要出去、夜间模式、报警模式。
