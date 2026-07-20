# 边缘设备协议参考

## 通用 H3863 二进制包

厨房和卫生间使用固定 32 字节 TCP 包：

```text
0-1    AA 55
2-5    CRC32，小端，计算 content 的 24 字节
6-29   content，共 24 字节
30-31  55 AA
```

未使用的 `content` 字节填零。设备回复同样是 32 字节包。

## 厨房 H3863

地址：

```text
TCP 192.168.1.23:8000
UDP 中控监听端口 8001
```

命令：

| content[0] | 功能 | 请求参数 |
|---:|---|---|
| `4` | 查询状态 | 无 |
| `5` | 设置灯亮度 | `content[1]=0-100` |

回复字段：

| 字节 | 字段 |
|---:|---|
| `content[1]` | `smoke_level`，GP03 原始电平 |
| `content[2]` | `smoke_alarm` |
| `content[3]` | `temp_alarm` |
| `content[4]` | 综合 `alarm` |
| `content[5]` | `light_on` |
| `content[6]` | `brightness` |
| `content[7:9]` | `thermal_mv`，小端 uint16 |

报警规则：

```text
GP03 = 0               -> smoke_alarm = 1
thermal_mv <= 1400mV   -> temp_alarm = 1
smoke_alarm OR temp_alarm -> alarm = 1
```

厨房还会向 `255.255.255.255:8001` 广播 JSON 状态。字段与 TCP 状态基本一致。中央控制应监听本机 `0.0.0.0:8001`，并以 `alarm` 状态变化为触发条件。

广播示例：

```json
{"type":"kitchen_alarm","ip":"192.168.1.23","thermal_mv":1630,"smoke_level":1,"smoke_alarm":0,"temp_alarm":0,"alarm":0,"light":0,"brightness":0}
```

## 卫生间 H3863

地址：

```text
TCP 192.168.1.63:8000
```

固定 Wi-Fi MAC：

```text
02:00:73:63:00:01
```

命令：

| content[0] | 功能 | 参数 |
|---:|---|---|
| `6` | 查询状态 | 无 |
| `7` | 设置灯亮度 | `content[1]=0-100` |
| `8` | 控制风扇 | `content[1]=方向`，`content[2]=速度` |

方向：

```text
0 = stop
1 = forward
2 = reverse
```

回复字段：

| 字节 | 字段 |
|---:|---|
| `content[1]` | `light_brightness` |
| `content[2]` | `motor_direction` |
| `content[3]` | `motor_speed` |
| `content[4]` | `motor_running` |

## 卧室 H3863

地址：

```text
TCP 192.168.1.64:8000
```

固定 Wi-Fi MAC：

```text
02:00:73:63:00:02
```

卧室使用 28BYJ-48 + ULN2003 半步驱动：

```text
GP01 -> ULN2003 IN1
GP02 -> ULN2003 IN2
GP04 -> ULN2003 IN3
GP05 -> ULN2003 IN4
GP06 -> 关闭限位，低电平触发
GP07 -> 打开限位，低电平触发
```

命令：

| content[0] | 功能 | 参数 |
|---:|---|---|
| `9` | 查询状态 | 无 |
| `10` | 设置灯亮度 | `content[1]=0-100` |
| `11` | 设置窗帘目标位置 | `content[1]=0-100` |
| `12` | 窗帘动作 | `content[1]=0` 停止，`1` 回零 |

回复字段：

| 字节 | 字段 |
|---:|---|
| `content[1]` | `light_brightness` |
| `content[2]` | `curtain_position` |
| `content[3]` | `curtain_target` |
| `content[4]` | `curtain_moving` |
| `content[5]` | `curtain_homed` |
| `content[6]` | `close_limit` |
| `content[7]` | `open_limit` |
| `content[8]` | `last_error` |

当前固件暂定全行程为 4096 半步、每半步间隔 2ms。`curtain_position` 在没有完成回零时只是软件估算值；安装关闭限位并成功执行 `home` 后才具备可靠的绝对位置基准。

卧室控制板已实机确认能够通过 SSB/FlashBoot 启动、连接 Wi-Fi、设置静态 IP `.64` 并监听 TCP `8000`。步进电机方向、扭矩、真实行程和两个限位输入尚待硬件到货后验证。

## 客厅/全局 Hi3861

地址：

```text
TCP 192.168.1.62:8000
```

除门禁外均为 ASCII 文本命令，以 `\n` 结尾：

```text
TEMP QUERY
EVENT QUERY
AC ON
AC OFF
AC QUERY
BEEP ON
BEEP OFF
BEEP ALARM
BEEP QUERY
LIGHT ON
LIGHT OFF
LIGHT AUTO
LIGHT TEST
LIGHT QUERY
```

返回示例：

```text
OK,type=TEMP,temp=24,humi=51,alarm=NONE,ip=192.168.1.62,port=8000
OK,type=AC,action=ON,state=ON,ip=192.168.1.62,port=8000,error=0
OK,type=BEEP,action=ALARM,state=ON,ip=192.168.1.62,port=8000,error=0
OK,type=EVENT,seq=1,code=1,detail=E077DE5C,ip=192.168.1.62,port=8000
```

门禁使用与 H3863 相同的 32 字节包结构：

```text
content[0] = 0：查询
content[0] = 1：设置
content[1] = 0：当前门
content[2] = 0：关门
content[2] = 1：开门
```

查询时当前固件使用：

```text
cmd=0, room=0, value=1
```

客厅事件码：

| code | 事件 |
|---:|---|
| 0 | 无事件/启动 |
| 1 | NFC 允许并开门 |
| 2 | NFC 拒绝 |
| 3 | 温湿度报警 |
| 4 | 温湿度恢复 |
| 5 | 门打开 |
| 6 | 门关闭 |
| 7 | 空调打开 |
| 8 | 空调关闭 |
| 9 | 蜂鸣器报警 |
| 10 | 蜂鸣器关闭 |

中央控制轮询 `EVENT QUERY` 时必须使用 `seq` 去重。
