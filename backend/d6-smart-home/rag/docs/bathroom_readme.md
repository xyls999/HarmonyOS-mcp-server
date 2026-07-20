# 卫生间 H3863 固定 IP 固件

## 网络配置

- Wi-Fi：`TEST-2.4GHz`
- 固定 IP：`192.168.1.63`
- 子网掩码：`255.255.255.0`
- 网关：`192.168.1.1`
- 固定 Wi-Fi MAC：`02:00:73:63:00:01`
- TCP 控制端口：`8000`

这块板之前无法读取有效的 NV/eFuse MAC，系统每次启动可能生成不同的随机 MAC，因此路由器 DHCP 分配的 IP 会从 `.99` 变为 `.203`。此版本同时固定 MAC 和 IPv4 地址。

建议在路由器 DHCP 设置中排除或保留 `192.168.1.63`，避免以后路由器把同一地址分配给其他设备。

## 唯一推荐烧录文件

只使用：

`bathroom_tb6612_fixed_ip_63_load_only.fwpkg`

这个包只包含：

- `root_loaderboot_sign.bin`：HiBurn 下载加载器
- `ws63-liteos-app-sign.bin`：应用固件，烧录地址 `0x230000`

不要使用 `_all.fwpkg`、recovery、params、flashboot 或 NV 文件。使用 `.fwpkg` 时不需要手动填写地址。

HiBurn 显示 `All images burn successfully` 后立即停止下载并断开连接，然后重新上电。不要让 HiBurn继续循环连接或重复烧录。

## 启动日志

重新上电后，串口应出现类似内容：

```text
APP|bathroom fixed wifi mac: 02:00:73:63:00:01
APP|[WIFI_LED_STA] configure static ip 192.168.1.63
APP|[WIFI_LED_STA] static ip ready, ip=192.168.1.63
APP|[bathroom] wifi connected, ip=192.168.1.63
APP|[bathroom] TCP server listening on 192.168.1.63:8000
```

## 电脑控制

在本目录打开 PowerShell：

```powershell
python bathroom_client.py --ip 192.168.1.63 query
python bathroom_client.py --ip 192.168.1.63 light 100
python bathroom_client.py --ip 192.168.1.63 light 0
python bathroom_client.py --ip 192.168.1.63 motor forward 100
python bathroom_client.py --ip 192.168.1.63 motor reverse 100
python bathroom_client.py --ip 192.168.1.63 motor stop
```

灯为 GP00 低电平有效；客户端参数保持当前协议定义，`light 100` 与 `light 0` 的实际亮灭以接线后的测试结果为准。

## TB6612 接线

- `PWMA` -> GP01
- `AIN1` -> GP02
- `AIN2` -> GP04
- `STBY` -> 3.3V
- `VCC` -> 3.3V
- `VM` -> 电机外部电源正极
- TB6612 `GND`、H3863 `GND`、外部电源负极必须共地
- 电机两根动力线接 `A01/A02`

此版本还修复了电机 `speed=100` 时 PWM 低电平周期为零的问题，避免部分 WS63 PWM 硬件出现短暂停顿。

如果烧录此版本后满速仍然停顿，优先检查电机电源。TB6612 的 `VM` 不要使用 H3863 的 3.3V 输出；建议使用能够承受 N20 启动/堵转电流的独立电源，并在 TB6612 的 `VM-GND` 附近并联 `470uF` 至 `1000uF` 电解电容和 `0.1uF` 陶瓷电容。
