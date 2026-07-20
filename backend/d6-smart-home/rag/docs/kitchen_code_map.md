# H3863 厨房中控代码位置说明

这个项目主工程在：

```text
D:\Users\asus\Downloads\bearpi-pico_h3863-master
```

短路径构建目录通常是：

```text
C:\bp
```

## 最重要的 H3863 固件代码

### 1. 灯、烟雾、热敏主逻辑

```text
application/ws63/ws63_liteos_application/kitchen_controller.c
application/ws63/ws63_liteos_application/kitchen_controller.h
```

这里负责：

```text
GP00：LED 灯亮度控制
GP03：烟雾传感器 DO 输入
GP07 / ADC0：热敏模块 AO 输入
```

当前逻辑重点：

```text
GP00 LED 是低电平亮、高电平灭
网络亮度 0   -> 灭
网络亮度 100 -> 全亮

GP03 smoke_level=1 -> 正常
GP03 smoke_level=0 -> 有烟报警

GP07 thermal_mv <= 1400mV -> 过热报警
```

关键函数：

```text
kitchen_controller_start()
kitchen_controller_get_status()
kitchen_controller_set_light(uint8_t brightness)
```

### 2. Wi-Fi / TCP / UDP 协议

```text
application/ws63/ws63_liteos_application/wifi_led_server.c
application/ws63/ws63_liteos_application/wifi_led_server.h
```

这里负责：

```text
连接 Wi-Fi
启动 TCP 8000 服务
接收远端灯亮度控制
返回厨房传感器状态
通过 UDP 8001 广播报警 JSON
```

当前协议：

```text
TCP 端口：8000
UDP 报警广播端口：8001

CMD 4：查询厨房状态
CMD 5：设置 GP00 灯亮度，content[1] = 0-100
```

状态响应字段：

```text
content[0] = 4
content[1] = smoke_level
content[2] = smoke_alarm
content[3] = temp_alarm
content[4] = alarm
content[5] = light
content[6] = brightness
content[7..8] = thermal_mv，小端序
```

### 3. 程序入口

```text
application/ws63/ws63_liteos_application/main.c
```

入口里会调用：

```text
kitchen_controller_start();
wifi_led_server_start_tasks();
```

可用来确认新固件启动的日志：

```text
DBG|kitchen network controller entered
[kitchen] ready light=GP00 active-low software-pwm smoke=GP03 thermal=ADC0/GP07
[kitchen] thermal alarm rule: ADC0/GP07 <= 1400mV
[boot] Kitchen Wi-Fi sensor/light hub on WS63
```

## 电脑端测试/中控脚本

这些文件在最终输出目录：

```text
C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge
```

### 1. 控灯、查状态、联动 Hi3861 蜂鸣器

```text
C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge\kitchen_hub_bridge.py
```

常用命令：

```powershell
cd C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge

python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 query
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 light 100
python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 light 0

python kitchen_hub_bridge.py --kitchen-ip 192.168.1.23 listen --hi3861-ip 192.168.1.62 --clear-beep
```

### 2. 只实时监听 H3863

```text
C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge\kitchen_monitor_3863.py
```

运行：

```powershell
cd C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge
python kitchen_monitor_3863.py --kitchen-ip 192.168.1.23
```

输出示例：

```text
POLL OK thermal=1600mV smoke_level=1 smoke_alarm=0 temp_alarm=0 alarm=0 brightness=0
POLL ALARM thermal=1350mV smoke_level=1 smoke_alarm=0 temp_alarm=1 alarm=1 brightness=0
POLL ALARM thermal=1600mV smoke_level=0 smoke_alarm=1 temp_alarm=0 alarm=1 brightness=0
```

## 烧录文件

最终输出目录：

```text
C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge
```

优先烧录：

```text
kitchen_alarm_bridge_app-only.fwpkg
```

如果直接烧 bin：

```text
kitchen_alarm_bridge_app-sign.bin
地址：0x230000
```

完整包：

```text
kitchen_alarm_bridge_all.fwpkg
```

## 当前硬件接线

```text
LED：
GP00 -> 电阻 -> LED
LED 另一端 -> 3V3 或 GND，实际当前表现为低电平亮

烟雾模块：
DO -> GP03
GND -> H3863 GND
VCC -> 5V 时，DO 到 GP03 建议加分压，避免 5V 直入 GPIO

热敏模块：
AO -> GP07 / ADC0
GND -> H3863 GND
VCC -> 3.3V 或模块要求电源
```

## 给另一个 AI 的重点

如果要复现“灯”的功能，主要看：

```text
application/ws63/ws63_liteos_application/kitchen_controller.c
```

重点函数：

```text
kitchen_apply_light()
kitchen_drive_light_pwm()
kitchen_controller_set_light()
```

如果要复现“网络控制灯”，再看：

```text
application/ws63/ws63_liteos_application/wifi_led_server.c
```

重点命令：

```text
CMD_KITCHEN_LIGHT = 5
handle_protocol_packet()
send_kitchen_status_packet()
```

