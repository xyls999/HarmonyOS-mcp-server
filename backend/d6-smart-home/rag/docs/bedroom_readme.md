# 卧室 H3863 + 28BYJ-48/ULN2003 固件

## 网络

- Wi-Fi：`TEST-2.4GHz`
- 固定 IP：`192.168.1.64`
- 网关：`192.168.1.1`
- 固定 MAC：`02:00:73:63:00:02`
- TCP 端口：`8000`

## 接线

### LED 灯

```text
H3863 3.3V -> 220~330R 电阻 -> LED 长脚
LED 短脚 -> GP00
```

灯为低电平点亮。

### ULN2003

```text
H3863 GP01 -> ULN2003 IN1
H3863 GP02 -> ULN2003 IN2
H3863 GP04 -> ULN2003 IN3
H3863 GP05 -> ULN2003 IN4

外部 5V 正极 -> ULN2003 VCC/+
外部 5V 负极 -> ULN2003 GND/-
H3863 GND -> 外部 5V 负极

28BYJ-48 五线插头 -> ULN2003 电机接口
```

不要使用 H3863 的 3.3V 给步进电机供电。建议外部 `5V 1A~2A` 电源，并在 ULN2003 电源附近放置 `470uF~1000uF` 电解电容。

### 限位开关

```text
GP06 -> 关闭限位开关 -> GND
GP07 -> 打开限位开关 -> GND
```

固件启用内部上拉：

```text
未触发 = 1
触发   = 0
```

限位开关未到货时 GP06/GP07 保持悬空即可，内部上拉会保持正常状态。

## 控制协议

使用与厨房、卫生间相同的 32 字节 CRC32 协议：

| 命令 | 功能 |
|---:|---|
| `CMD9` | 查询状态 |
| `CMD10` | 设置灯亮度，参数 `0-100` |
| `CMD11` | 设置窗帘目标位置，参数 `0-100` |
| `CMD12` | `0=停止，1=回零` |

状态字段：

```text
content[1] = light_brightness
content[2] = curtain_position
content[3] = curtain_target
content[4] = curtain_moving
content[5] = curtain_homed
content[6] = close_limit
content[7] = open_limit
content[8] = last_error
```

`last_error=1` 表示回零移动超过最大步数但 GP06 仍未触发。

## 当前电机参数

```text
半步序列：8 相半步
步进间隔：2ms
全行程：4096 半步
回零最大：6144 半步
```

这些是到货前的安全初始值。实际安装后必须根据滑轮直径和窗帘行程调整 `BEDROOM_STEPS_FULL_TRAVEL`。

## 电脑控制

```powershell
python bedroom_client.py status
python bedroom_client.py light on
python bedroom_client.py light off
python bedroom_client.py light 50
python bedroom_client.py curtain open
python bedroom_client.py curtain close
python bedroom_client.py curtain position 50
python bedroom_client.py curtain stop
python bedroom_client.py curtain home
```

## 烧录

只使用：

```text
bedroom_uln2003_fixed_ip_64_load_only.fwpkg
```

该包只包含下载加载器和签名应用，不包含 params、flashboot 或 NV。HiBurn 显示 `All images burn successfully` 后停止下载并重新上电。

预期串口：

```text
APP|bedroom fixed wifi mac: 02:00:73:63:00:02
APP|[WIFI_LED_STA] static ip ready, ip=192.168.1.64
[bedroom] TCP server listening on 192.168.1.64:8000
```

## 到货后调试顺序

1. 先不装窗帘，只接 ULN2003 和电机。
2. 执行 `curtain position 5`，确认电机能够小角度旋转。
3. 如果只抖动不旋转，检查 IN1~IN4 接线和 5V 电源。
4. 如果开关方向相反，后续调整软件方向，不要随意重排五线电机插头。
5. 安装限位开关后执行 `curtain home`。
6. 最后测量实际全开所需步数并修改全行程常量。

固件已完成编译，但步进电机、ULN2003 和限位开关尚未到货，因此电机方向、扭矩、行程和限位功能仍需实机验证。
