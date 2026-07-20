# kitchen_alarm_bridge

## 这版固件做什么

- H3863 / WS63 作为厨房传感器与灯控节点。
- GP03 接烟雾传感器 DO，低电平表示有烟。
- GP07 / ADC0 接热敏模块 AO，当前热敏模块为越热电压越低，电压 <= 1400mV 表示过热。
- 报警时 H3863 不再自动点亮 LED，只通过 UDP 8001 上报报警 JSON。
- GP00 LED 只接受网络亮度控制，亮度范围 0-100；当前硬件为低电平亮、高电平灭。
- TCP 8000 提供状态查询和灯亮度控制。

## 优先烧录这个文件

HiBurn 优先选择：

```text
kitchen_alarm_bridge_app-only.fwpkg
```

这是单 app 包，只更新 app 分区，包内地址已经是：

```text
0x230000
```

如果你改用 bin 文件，选择：

```text
kitchen_alarm_bridge_app-sign.bin
```

并手动填写烧录地址：

```text
0x230000
```

## 烧录后串口确认

关闭 HiBurn，打开串口工具 COM13 / 115200，按 Reset。看到这些日志表示新固件运行正确：

```text
DBG|kitchen network controller entered
[kitchen] ready light=GP00 active-low software-pwm smoke=GP03 thermal=ADC0/GP07
[boot] kitchen mode: alarm report only, GP00 brightness controlled by network
[boot] Kitchen Wi-Fi sensor/light hub on WS63
[wifi] connected, ip=192.168.1.xxx
[tcp] server listening on 192.168.1.xxx:8000
```

## 本机测试 H3863

假设 H3863 IP 是 192.168.1.23：

```powershell
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 query
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 light 0
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 light 30
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 light 100
```

返回字段含义：

```text
thermal=热敏电压mV
smoke_level=GP03电平，0通常表示有烟
smoke_alarm=1表示烟雾报警
temp_alarm=1表示过热报警，当前阈值为 thermal <= 1400mV
alarm=1表示有任一报警
brightness=GP00 LED亮度 0-100
```

## 报警转发到 Hi3861 蜂鸣器

先确认 Hi3861 蜂鸣器节点能响应：

```powershell
python kitchen_hub_bridge.py beep --hi3861-ip <Hi3861_IP> query
python kitchen_hub_bridge.py beep --hi3861-ip <Hi3861_IP> alarm
python kitchen_hub_bridge.py beep --hi3861-ip <Hi3861_IP> off
```

再启动本机中控监听。H3863 报警时，本机会向 Hi3861 发送 `BEEP ALARM`：

```powershell
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 listen --hi3861-ip <Hi3861_IP> --clear-beep
```

## H3863 网络协议

TCP 8000，32 字节二进制包：

```text
AA 55 + CRC32(content 24字节，小端) + content[24] + 55 AA
```

- 查询状态：content[0] = 4
- 设置灯亮度：content[0] = 5，content[1] = 0-100

状态响应 content：

```text
content[0] = 4
content[1] = smoke_level
content[2] = smoke_alarm
content[3] = temp_alarm
content[4] = alarm
content[5] = light，brightness>0 时为 1
content[6] = brightness
content[7..8] = thermal_mv，小端
```

