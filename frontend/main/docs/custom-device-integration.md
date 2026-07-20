# 自定义设备接入方案：ESP32-S3 LED

完整比赛演示步骤、协议安全矩阵和答辩说明见
[`extensibility-and-protocols-demo.md`](./extensibility-and-protocols-demo.md)。

## 结论

项目现在支持“扫描 → 协议匹配 → 用户确认 → 注册 → 查询 → 控制 → 上下文记录”的完整链路。设备按
`LED_API.md` 的 HTTP 契约接入，不需要改 ESP32 下位机代码。发现流程是定向读取
`http://192.168.1.102:8080/api/state`，从返回值获取 `esp_ip`，然后只访问该 IP 的
`/api/status` 和 `/api/led`。这不是全网端口扫描：最多访问一个用户指定的中控和一个
已返回的设备地址，避免把内网信息暴露给第三方或误扫其他设备。

## 接入时序

```text
App 点击“发现 LED”
        │ POST /api/custom/discover
        ▼
网关 CustomLedAdapter
        │ GET 192.168.1.102:8080/api/state
        │ 读取 esp_ip（例如 192.168.1.54）
        │ GET http://192.168.1.54:80/api/status
        ▼
生成待确认设备模板
        │ 暂存扫描结果，不进入设备列表
        ▼ 用户点击“确认接入设备”
创建自定义设备模板
        │ 写入 custom_led_devices.json（仅网关内部使用，前端列表不返回地址）
        │ 同步 Intent/上下文实体
        ▼
设备页出现“ESP32 灯带”，可开关、改颜色、查询状态
```

开发板的 HTTP 状态端口必须真实可达并返回有效状态。本次扫描若遇到设备掉电、
未联网、地址过期或状态接口异常，网关直接返回“设备未联网或状态接口不可达”，
不会生成扫描结果，也不会写入待接入列表或设备注册表。

## 对接 API

### 扫描与手动接入

```http
POST /api/custom/scan
Authorization: Bearer <网关令牌>
Content-Type: application/json

{"deviceType":"light","name":"","room":"玄关"}
```

返回待确认的 `device` 和 `discovery`，不会自动出现在 `/api/devices`。用户确认后调用：

```http
POST /api/custom/register
{"device_id":"custom_led_192168154"}
```

注册后才会进入 `/api/devices`。`discovery.scanned_hosts`
固定为 1，表示定向发现，不代表扫描了整个网段。

### 查询与控制

```http
GET /api/custom/devices

POST /api/devices/custom_led_192168154/control
{"action":"set_color","params":{"color":"blue"}}

POST /api/devices/custom_led_192168154/toggle
{"isOn":true}
```

支持动作：`on`、`off`、`toggle`、`set_color`、`query`。颜色仅允许 `red`、`green`、
`blue`，服务端会再次校验，非法值不会发到设备。

## 可扩展性设计

`CustomLedAdapter` 与网关业务解耦，设备模板只暴露：

* `id/name/type/room`：前端展示和自然语言匹配；
* `capabilities`：动作白名单和参数约束；
* `protocol/transport/endpoint`：实际传输适配器；
* `isOn/primaryValue/mode`：前端统一状态模型。

以后接入 MQTT、WebSocket、CoAP 或 HTTPS 时，只需增加同样接口的适配器，设备页和
AI/上下文层无需改动。主控现有协议网关已经提供 HTTPS、WebSocket、MQTT、CoAP 的
统一路由；LED 适配器当前按厂商文档选择 HTTP，是因为下位机只实现了 HTTP。

## 安全与不泄露原则

1. 发现地址只接受内网 IPv4 的 HTTP(S)，拒绝公网、用户名密码和任意 URL。
2. 不做网段端口扫描，不上传设备状态到外部服务。
3. 注册文件不保存密钥、完整请求体、认证头和响应原文；endpoint 仅作为网关内部路由，
   `/api/devices` 与 `/api/custom/devices` 不返回设备 IP 或 endpoint。
4. 设备控制仍经过主控认证、写权限和日志链路；AI 只能调用白名单动作。
5. 直连失败时返回“设备不可达”，不创建模拟结果，也不伪造成功。

## 验证命令

```powershell
# 先验证中控发现页
curl.exe http://192.168.1.102:8080/api/state

# 按 LED_API.md 验证真实板卡（将 IP 替换为发现结果）
curl.exe http://192.168.1.54/api/status
curl.exe "http://192.168.1.54/api/led?led=1&color=blue"
curl.exe "http://192.168.1.54/api/led?led=0"
```

上述命令不会输出 API 密钥或主控认证信息；生产环境应通过主控 HTTPS/安全信封访问，
不要把 ESP32 的 HTTP 端口直接暴露到公网。
