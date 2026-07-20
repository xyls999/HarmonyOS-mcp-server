# 智能家居边缘设备到中央控制交接说明

## 1. 交接范围

本文档面向中央控制工程师，覆盖以下四个局域网边缘设备：

| 区域 | 边缘设备 | 地址 | 主要能力 |
|---|---|---|---|
| 客厅/全局 | Hi3861，工程目录名为 `hi3863demo` | `192.168.1.62:8000` | 门禁、温湿度、红外空调、蜂鸣器、客厅灯、NFC/事件 |
| 厨房 | H3863 | `192.168.1.23:8000`，UDP `8001` | GP00 灯、GP03 烟雾数字量、GP07 热敏 ADC |
| 卫生间 | H3863 | `192.168.1.63:8000` | GP00 灯、TB6612/N20 排风扇 |
| 卧室 | H3863 | `192.168.1.64:8000` | GP00 灯、28BYJ-48/ULN2003 窗帘、双限位 |

三个设备均使用 2.4 GHz Wi-Fi。当前实验网络为 `TEST-2.4GHz`。中央控制程序必须与设备处于同一局域网。

## 2. 文件说明

- `central_controller.py`：推荐使用的统一远程控制入口，仅依赖 Python 标准库。
- `devices.json`：设备 IP、端口和灯亮度方向配置。
- `PROTOCOL_REFERENCE.md`：二进制包、文本命令和状态字段说明。
- `01_check_all_devices.bat`：只读检查四台设备，不改变灯、电机或蜂鸣器状态。
- `02_monitor_readonly.bat`：持续监听厨房状态和 UDP 报警，只显示，不联动。
- `03_monitor_alarm_linkage.bat`：厨房报警上升沿触发客厅蜂鸣器，报警恢复后关闭蜂鸣器。
- `reference_clients/`：各边缘设备原始测试客户端，便于协议对照。

运行环境：Windows + Python 3.9 或更高版本，无需安装第三方包。

## 3. 快速开始

在本目录打开 PowerShell：

```powershell
python central_controller.py status
```

该命令只查询，不执行任何开关动作。单台设备超时不会阻止其他设备返回状态。

### 客厅

```powershell
python central_controller.py living temp
python central_controller.py living event
python central_controller.py living light query
python central_controller.py living light on
python central_controller.py living light off
python central_controller.py living light auto
python central_controller.py living door query
python central_controller.py living door open
python central_controller.py living door close
python central_controller.py living ac query
python central_controller.py living ac on
python central_controller.py living ac off
python central_controller.py living beep query
python central_controller.py living beep alarm
python central_controller.py living beep off
```

### 厨房

```powershell
python central_controller.py kitchen status
python central_controller.py kitchen light on
python central_controller.py kitchen light off
python central_controller.py kitchen light 50
```

厨房状态字段：

- `smoke_level=0`：GP03 低电平。
- `smoke_alarm=1`：烟雾报警。
- `temp_alarm=1`：热敏 ADC 电压小于等于 `1400mV`。
- `alarm=1`：烟雾或过热任一报警。
- `thermal_mv`：GP07/ADC0 当前毫伏值。
- `brightness`：边缘端保存的灯亮度，范围 `0-100`。

烟雾模块当前逻辑为低电平报警，即 `GP03=0 -> smoke_alarm=1`。

### 卫生间

```powershell
python central_controller.py bathroom status
python central_controller.py bathroom light on
python central_controller.py bathroom light off
python central_controller.py bathroom light 50
python central_controller.py bathroom fan forward 100
python central_controller.py bathroom fan reverse 60
python central_controller.py bathroom fan stop
```

卫生间状态字段：

- `light_brightness`：灯亮度 `0-100`。
- `motor_direction`：`0=停止，1=正转，2=反转`。
- `motor_speed`：PWM 速度 `0-100`。
- `motor_running`：`0=停止，1=运行`。

TB6612 使用 GP01/PWMA、GP02/AIN1、GP04/AIN2，STBY 固定接 3.3V。电机 VM 使用独立电源，外部电源、TB6612 和 H3863 必须共地。

### 卧室

```powershell
python central_controller.py bedroom status
python central_controller.py bedroom light on
python central_controller.py bedroom light off
python central_controller.py bedroom light 50
python central_controller.py bedroom curtain open
python central_controller.py bedroom curtain close
python central_controller.py bedroom curtain position 50
python central_controller.py bedroom curtain stop
python central_controller.py bedroom curtain home
```

卧室使用 28BYJ-48 + ULN2003：

```text
GP01 -> IN1
GP02 -> IN2
GP04 -> IN3
GP05 -> IN4
GP06 -> 关闭限位开关 -> GND
GP07 -> 打开限位开关 -> GND
```

状态字段：

- `curtain_position`：当前估算位置 `0-100`。
- `curtain_target`：目标位置。
- `curtain_moving`：是否正在步进。
- `curtain_homed`：是否通过限位开关完成过定位。
- `close_limit/open_limit`：对应限位开关状态。
- `last_error=1`：回零超过最大步数但关闭限位仍未触发。

卧室控制板已完成烧录并实测联网，`192.168.1.64:8000` 的 CMD9～CMD12 服务正常监听。28BYJ-48、ULN2003 和限位开关尚未到货，因此目前只确认了启动、网络、协议和空载 GPIO 初始化。电机接入前不要执行 `curtain home`，否则固件会在未触发限位的情况下输出最多 6144 个关闭方向半步。

## 4. 厨房报警联动客厅蜂鸣器

只读监听：

```powershell
python central_controller.py monitor
```

启用自动联动：

```powershell
python central_controller.py monitor --trigger-buzzer --clear-buzzer
```

联动规则：

1. 中控每秒查询一次厨房状态，同时尝试监听 UDP `8001`。
2. `alarm` 从 `0` 变为 `1` 时，向客厅发送 `BEEP ALARM`。
3. 使用 `--clear-buzzer` 时，`alarm` 从 `1` 恢复为 `0` 后发送 `BEEP OFF`。
4. 同一持续报警不会在每次轮询时重复触发蜂鸣器。

生产系统建议由中央控制服务保存报警时间、确认状态和恢复时间，而不是只依赖控制台输出。

厨房 UDP 使用 `255.255.255.255:8001` 局域网广播，不绑定某一台电脑。中央控制程序迁移到另一台电脑后无需修改厨房固件，但新电脑的防火墙必须允许 UDP `8001` 入站，并且交换机/路由器不能隔离无线客户端广播。

## 5. 配置 IP

所有地址集中在 `devices.json`。若设备地址变化，只修改该文件，不需要修改 Python 代码。

当前约定：

```text
客厅    192.168.1.62
厨房    192.168.1.23
卫生间  192.168.1.63
卧室    192.168.1.64
```

建议在路由器 DHCP 设置中为四个地址做 MAC 绑定或地址保留。卫生间固件固定 MAC `02:00:73:63:00:01` 和静态 IP `.63`；卧室固件固定 MAC `02:00:73:63:00:02` 和静态 IP `.64`。

如现场灯亮度方向相反，可在 `devices.json` 中把对应设备的：

```json
"light_command_inverted": false
```

改为：

```json
"light_command_inverted": true
```

统一客户端仍保持 `0=关、100=全亮` 的中央控制语义。

## 6. 连接超时排查

依次检查：

1. 板子是否上电，串口是否已经显示 Wi-Fi 连接成功。
2. 中控电脑和设备是否连接同一个 `192.168.1.x` 局域网。
3. 设备启动日志中的 IP 是否与 `devices.json` 一致。
4. TCP `8000` 是否被系统防火墙阻止。
5. 厨房 UDP 联动需要允许本机接收 UDP `8001`。
6. 使用 `python central_controller.py --timeout 5 status` 增大超时时间。

卧室 `.64` 已实机启动并确认以下状态：

```text
APP|bedroom fixed wifi mac: 02:00:73:63:00:02
APP|[WIFI_LED_STA] static ip ready, ip=192.168.1.64
APP|[bedroom] TCP server listening on 192.168.1.64:8000
APP|[bedroom] protocol CMD9=status CMD10=light CMD11=curtain CMD12=stop/home
```

该旧板上电开头仍可能出现一次 `Flash Init Fail! ret = 0x80001341`，随后如果继续出现 `SSB Flash Init Succ!`、`Flashboot ... Flash Init Succ!` 并进入以上卧室日志，则本次启动最终成功。若只重复报错且没有 SSB/APP 日志，才属于启动失败。

在最初交接包生成时，卫生间 `.63` 查询成功；客厅 `.62` 和厨房 `.23` 查询超时，表示它们当时可能未上电、未联网或不在当前局域网。

## 7. 中央控制实现建议

- TCP 命令采用一次连接、一次请求、一次回复，再关闭连接。
- 设置 `2-5s` 连接和读取超时，并记录设备离线状态。
- 不要无限重试控制命令，避免恢复联网后重复执行开门或报警。
- 客厅 `EVENT QUERY` 使用 `seq` 去重，只在序号变化时处理新事件。
- 厨房报警按状态上升沿/下降沿处理，不要每秒重复报警。
- 所有当前协议均未提供 TLS、认证或权限控制，只应部署在可信局域网。
- 远程跨互联网控制时，应通过受认证的中央网关/VPN 转发，不应直接把设备 TCP `8000` 暴露到公网。

## 8. 原始工程位置

```text
客厅/Hi3861:
D:\Users\asus\Desktop\hi3863demo

厨房客户端与固件交付:
C:\Users\ASUS\Desktop\temp\kitchen_alarm_bridge

卫生间客户端与固件交付:
C:\Users\ASUS\Desktop\temp\bathroom_tb6612_fixed_ip_63

卧室客户端与固件交付:
C:\Users\ASUS\Desktop\temp\bedroom_uln2003_fixed_ip_64

H3863 SDK:
D:\Users\asus\Downloads\bearpi-pico_h3863-master
```

本交接目录用于远程控制和协议接入，不需要重新烧录设备。
