# 可扩展设备接入与多协议安全传输：满分演示手册

## 1. 演示目标

这套演示对应两项验收指标：

| 指标 | 可现场验证的证据 |
| --- | --- |
| 可扩展性高、高效接入控制其他家居设备 | ESP32 LED 无需修改主页面和 AI 业务代码，通过“发现—生成设备模板—能力注册—统一控制”自动进入设备页；新增 MQTT 示例适配器只实现一个接口即可注册 |
| 支持主流传输协议、协议广且数据安全 | 主控同时报告 HTTP、HTTPS、WebSocket、MQTT、CoAP；远程 HTTP 被策略拒绝，HTTPS 使用 TLS 1.3 与安全信封，其余实时/物联网协议使用加密负载和完整性标签 |

评审时不要只展示文档，按第 3 节运行脚本，让系统输出实时协议状态、适配器目录、
自定义设备和真实控制结果。

## 2. 架构原理

```text
前端 / AI / MCP
       │ 统一设备模型和统一控制 API
       ▼
AdapterRegistry（适配器注册、能力白名单）
       │
       ├── ESP32 LED HTTP Adapter ── /api/status、/api/led
       ├── MQTT Switch Adapter    ── topic + encrypted payload
       ├── CoAP Sensor Adapter    ── resource + light envelope
       └── 未来设备适配器         ── 只实现 capabilities/query/invoke
       │
       ▼
ProtocolGateway
       ├── HTTPS 8443：远程管理和加密调用
       ├── WebSocket /ws：实时状态与报警
       ├── MQTT 1883：设备控制和传感器上报
       ├── CoAP 5683：低功耗设备
       └── HTTP 8080：本地主控兼容接口
```

设备接入和传输协议是两层：厂商设备可以只实现 HTTP，但手机、云端和主控之间仍可走
HTTPS/MQTT/WebSocket/CoAP。这样既兼容旧设备，又不会谎称 ESP32 本身支持未实现的协议。

## 3. 现场演示

### 3.1 一条命令完成完整演示

在 D6 上执行：

```sh
/data/A9/python-portable/lib/ld-musl-armhf.so.1 \
  --library-path /data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib \
  /data/A9/python-portable/usr/bin/python3.14 \
  /data/A9/demo_protocol_extensibility.py \
  --base http://127.0.0.1:8080 --scan-device --control-device
```

演示依次输出：

1. 主控健康状态；
2. HTTP、HTTPS、WebSocket、MQTT、CoAP 协议与安全策略；
3. 从 `192.168.1.102:8080/api/state` 获取板卡地址；
4. 注册 `ESP32 灯带`；
5. 通过统一 API 切换为蓝色；
6. 恢复演示前颜色；
7. 输出验收通过。

脚本会删除 endpoint、board IP、令牌和 API Key，不在展示屏泄露内网细节。

### 3.2 App 演示

1. 打开“设备”。
2. 点击“扫描自定义设备”。
3. 选择灯光、风扇、空调、窗帘、开关、插座、传感器或摄像头类型。
4. 输入可选名称和安装位置。
5. 点击“扫描并接入设备”。
6. 返回设备页，出现扫描到的设备并展示其实际能力。
7. 刷新设备页，状态仍与硬件一致，证明不是前端静态 Mock。

8. 在扫描结果卡片中查看协议库搜索图标、HTTP、HTTPS、WebSocket、MQTT、CoAP
   和匹配结果；协议库信息只放在自定义设备页面，不放设置页。

当前这组前端改动已经构建为 signed HAP 并安装到 D6，打开设置页即可演示。

### 3.3 接口演示

```http
GET /api/protocols/catalog
GET /api/protocols/status
POST /api/custom/discover
GET /api/devices
POST /api/devices/custom_led_192168154/toggle
POST /api/devices/custom_led_192168154/control
```

`/api/protocols/catalog` 同时给出协议能力、运行状态、适配器能力以及远程访问策略，且
不返回密钥。

## 4. 新设备如何快速接入

新增设备适配器只需实现：

```python
class NewDeviceAdapter:
    adapter_id = "vendor_device_v1"
    protocol = "mqtt"  # http / https / websocket / mqtt / coap

    def capabilities(self):
        return [
            Capability("query", "查询状态"),
            Capability("toggle", "开关设备", {"isOn": "bool"}),
        ]

    def query(self, device_id):
        return {"success": True, "isOn": False}

    def invoke(self, device_id, action, params):
        # 在这里翻译为厂商 HTTP、MQTT topic、CoAP resource 或串口帧
        return {"success": True}

registry.register(NewDeviceAdapter())
```

接入后系统自动获得：

* 统一设备列表和状态模型；
* 能力白名单；
* 前端开关与 AI/MCP 调用入口；
* 操作日志和上下文记录；
* 协议与安全能力目录。

无需修改首页、助手页、设备控制路由或数据库主结构。

## 5. 协议与安全对应关系

| 协议 | 场景 | 安全处理 |
| --- | --- | --- |
| HTTP | 旧设备、同一受信局域网 | 仅允许内网地址；主控鉴权、动作白名单、审计；远程策略拒绝 HTTP |
| HTTPS | 手机、远程服务、管理接口 | TLS 1.3；SM2 签名；SM4 加密安全信封；SM3 摘要；令牌和 Nonce 防重放 |
| WebSocket | 实时状态、报警、助手事件 | 握手鉴权；SM4 加密帧；SM3 完整性；连接和消息大小限制 |
| MQTT | 设备控制、传感器上报 | 客户端 ACL；主题白名单；SM4 加密负载；SM3 标签；公网使用 8883/TLS |
| CoAP | 低功耗传感器 | 资源和方法白名单；轻量 SM4+SM3；时间戳/Nonce；公网使用安全端口 |

系统加密密钥只存在 D6 的 root-only 运行目录。API、日志、演示脚本和设备列表均不返回
SM2 私钥、SM4 密钥、API Key、门禁密码或完整内网 endpoint。

## 6. 验收测试

```powershell
$env:PYTHONPATH='D:\Harmon_LandscapeControl_OpenHarmony'
python -m unittest `
  tests.test_custom_led_adapter `
  tests.test_protocol_contract -v
```

核心断言：

* 五类协议均存在；
* HTTPS、WebSocket、MQTT、CoAP 均标记加密；
* 远程明文 HTTP 被拒绝；
* 公网 endpoint 与 URL 内嵌凭据被拒绝；
* 未声明动作不能执行；
* 新 MQTT 适配器无需修改业务路由即可注册和调用；
* LED 发现、开关、颜色切换和状态回读均成功。

## 7. 评审答辩要点

“系统不是为一个 LED 写死了一组按钮。我们把设备能力、厂商协议和业务控制分成三层。
新设备只需实现适配器契约，就能自动进入设备列表、AI/MCP 能力和审计体系。主控对外提供
HTTPS、WebSocket、MQTT、CoAP，对只支持 HTTP 的旧设备使用内网隔离适配。远程明文
HTTP 会被策略拒绝，所有可执行动作经过认证和能力白名单，敏感地址与密钥不会进入前端。”
