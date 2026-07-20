# A9 超级上下文/MCP 部署清单

- 日期：2026-07-17
- 目标设备：`d6290341334135353210f41a68f0bb00`
- 设备目录：`/data/A9/smart_home`
- 部署前备份：`/data/A9/backups/super_context_20260717_234533`
- 本地主线测试：64 项通过
- 设备端测试：64 项通过
- 核心文件本地/设备 SHA-256：15/15 一致
- 未执行：真实门禁开关、整机重启（按规格禁止）

| 文件 | SHA-256 |
|---|---|
| `gateway_v6.py` | `1d79ad7396e731d615dabef8b20e9e0c7b800d614dd817190a88a2a6a1c7eaf6` |
| `ai_provider_router.py` | `0bc5139613c387da8c5665f6f3f456ea0ffc5e23e2b1faf1703967a7dcb05134` |
| `bounded_http_server.py` | `ae86fb2890d1a2c2c381d5f7238a4f9f4be45ce0a8cf3302fa76e380d57aa36e` |
| `context_engine.py` | `4c6b340fe5601b4cc77d808e486849ea5de650e41a29ca96337dc3f29cb71cdb` |
| `gateway_context_runtime.py` | `5df7d3db3a8949961b29c25874f31b5c908520eab49a488e8f3f330d7124ab15` |
| `super_mcp.py` | `fafec31067b1e2840d148dd1f0abecf681984b6edb91de0c2cc4e31833c4de2e` |
| `mcp_server_enhanced.py` | `08211850b0e9002fc36a61a25e1e5272167ad7ad6307f16b0ffd9eb427294bb2` |
| `hardware_bridge.py` | `bb07ea3c9eb2775d465e772ce750781dc87183ff236d32f7f8aa9fffe0fbfd3f` |
| `connect/central_controller.py` | `9c94bf4229a49b8049a5c1384b1ed4f9f49bb78032c706e29a770662d2afadbd` |
| `connect/devices.json` | `9d9958dc8156b6ff1795650cc12e56ce1d662c8a3141b565a1ec650db7955cde` |
| `connect/ac_ir_codes.json` | `a7627e95109e74ca0b3f3d16b3606c1949589c00515442300782a053845e221d` |
| `docs/FIELD_HARDWARE_REFERENCE.md` | `b0a63edbf7df03e5209fe5c31d7ec1a33f54da76bc57b09a0b4a71d7bbcc168f` |
| `/data/A9/run_v6.sh` | `9b9e20bb609ea15d4eea486e225c9b14dab0487e7867e19eba987834ea8aa1cc` |
| `/data/A9/run_tunnel.sh` | `96a2988aea946f20bd99fb0c50e172899625fa55b2604b3862a39fbeca8ec766` |
| `deploy/smart_home.cfg` → `/etc/init/smart_home.cfg` | `2645a80f520c51de212295079a257ec2df2d5ac39fba01cac88f355626fb0632` |

## 实机验收摘要

- `/health`：HTTP 200，`ok=true`。
- MCP：GET 405；未认证 POST 401；协议 `2025-11-25`。
- MCP 目录：23 个工具、9 个资源；stdio 与 HTTP 使用同一协议核心。
- 运行实体：16 个设备、9 个传感器、5 个场景。
- 上下文：1,708+ 文档/源码块、88 个实体、81,362+ 事件；后台持续增长。
- 规格补齐接口：`GET /api/ai/context/events`、`GET/POST /api/ai/radar/config` 实机通过；非布尔毫米波参数返回 400，幂等写入未改变 `radar_light`。
- 纯开场问候：自动上下文 0 字符。
- 毫米波实质首问：自动注入约 39K 字符（上限 48K）。
- 毫米波：`radar_presence.enabled=true`；`radar_light.enabled=false`；两者独立。
- 门禁：缺少密码被拒绝；错误测试密码被拒绝；两种测试标记均未出现在数据库、JSON 或日志。
- 动态设备：注册后立即可检索，随后成功注销。
- 非法自定义能力：`executor_type=shell` 返回 MCP `isError=true`。
- 可恢复灯光测试：`light_01` 初始开启，切换到关闭后成功恢复为开启；最终状态等于初始状态。
- HTTP 并发保护：旧进程曾达到 1,882 线程并无法接收请求；现已限制默认 64 个请求线程、连接超时 15 秒，重启后健康/MCP 全部恢复。
- AI 对话：文本路由 `DeepSeek → Astron → 讯飞 → Codex`，实测 DeepSeek 首选成功；多模态路由 `讯飞 → Codex`，实测讯飞返回 500 后 Codex Responses 自动回退成功。两次探测均注入上下文、未执行设备指令。
- 开机启动：`/etc/init/smart_home.cfg` 指向 `/data/A9/run_v6.sh` 和 `/data/A9/run_tunnel.sh`，并在启动前保持脚本权限 `0700`；未通过整机重启验证。

## 凭据处理

旧启动脚本中的运行凭据已迁移至：

- `/data/A9/.a9_backend.env`（权限 600）
- `/data/A9/.a9_tunnel.env`（权限 600）

脚本不再内嵌值。由于凭据曾存在于旧脚本和历史输出，仍建议上线后向各供应方轮换。
