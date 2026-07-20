# A9 超级上下文与 MCP 升级规格

状态：已批准、已实施并通过设备验收  
日期：2026-07-17  
目标设备：`d6290341334135353210f41a68f0bb00`  
设备部署目录：`/data/A9/smart_home/`  
本地实施基线：`C:\Users\xyls\Desktop\A9_backend_upgrade\gateway_v6.py`

## 1. 目标

将 A9 智慧家居后端升级为一个能够持续收集、结构化存储、检索和利用项目全量信息的 AI 控制系统，并提供符合 MCP 规范的资源和工具接口。

系统必须做到：

1. 收集源码、项目文档、设备、传感器、场景、能力、API、协议、安全规则、联动配置、运行状态、操作记录、日志、安全事件、对话历史和新产生的事件。
2. 生成统一的 `project_context.json`，同时将可检索内容、实体和事件持久化到主 SQLite 数据库。
3. 每次非纯开场问候的 AI 对话都自动获得：
   - 核心系统能力与安全边界；
   - 当前实时设备和传感器状态；
   - 与用户问题最相关的文档、源码能力、历史操作、日志和事件；
   - 可调用的 MCP/API 工具目录。
4. 新注册的自定义设备、能力、功能和联动自动进入 JSON、数据库、检索结果和 AI 工具能力，不依赖手工修改 Prompt。
5. 提供 MCP Streamable HTTP 与 stdio 两种入口，允许兼容客户端发现资源、发现工具并调用工具。
6. 保证毫米波功能开关和雷达灯光联动是两个独立状态；部署后毫米波功能保持开启。
7. 开门和关门每次都必须由用户当次手工输入密码；密码不得进入日志、数据库、JSON、Prompt、RAG、对话历史或审计详情。
8. 修复当前设备端 `gateway_v6.py` 的语法错误，完成测试、部署、启动和开机自启动验证。
9. 生成供 HarmonyOS 前端和远端服务端复写调用的完整对齐文档。

## 2. 已确认事实与假设

### 2.1 已确认事实

- 设备运行 HarmonyOS/aarch64 内核，业务 Python 为 3.14.5 armhf musl 便携运行时。
- `smart_home/` 没有 `pyproject.toml`、`requirements.txt` 或 pytest 配置；业务代码主要依赖 Python 标准库。
- 主数据库为 `/data/A9/control/data/smart_home.db`。
- 当前设备端 `gateway_v6.py` 因字符串引号和断行错误无法启动。
- 桌面 `gateway_v6.py` 是可解析修正版，与设备版只有四处逻辑修正。
- 设备端不存在项目级 `CLAUDE.md` 或 `AGENTS.md`。
- 当前数据库包含 16 个逻辑设备、9 个传感器和 5 个场景。
- 设备端存在早期图表、定时任务、记忆、QQ 推送补丁与遗留表，但当前主网关未完整暴露这些文档声称的接口。
- `/etc/init/smart_home.cfg` 已在开机完成后执行 `/data/A9/run_v6.sh` 和 `/data/A9/run_tunnel.sh`。
- 现场硬件与协议权威来源为 `C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717`；其中 `central_controller.py` 为 1841 行，比设备内旧版中控完整。
- 毫米波源是卫生间 H3863 的 Rd-03 V2 UART；当前有效距离为 20-110cm，分区为厨房 20-35cm、卫生间 40-55cm、客厅 60-85cm、卧室 90-110cm，7 个样本至少 5 个稳定命中。
- 现场中控已经在具体硬件动作函数内执行限频；现有 `hardware_bridge.py` 还会在调用前重复限频，二者组合可能错误拦截一次合法动作。

### 2.2 实施假设

1. 桌面参考目录作为可编辑实施基线；验证后部署到设备。
2. 采用 MCP 稳定协议版本 `2025-11-25`，不实现实验性 MCP Tasks。
3. “全部信息进入上下文”解释为：全量采集、全量可检索、关键内容常驻、相关内容自动注入；不是每轮原样拼接全部数据库和日志。
4. 不增加 pip 依赖；检索、MCP、JSON、HTTP 和 SQLite 均使用标准库实现。
5. 不进行真实门禁开关动作测试；只验证缺少/错误密码必定被拒绝及密码脱敏。
6. 毫米波感知功能在部署前后保持启用；自动开灯联动默认保持现有配置，不因本升级自动改变。
7. 本次迁移现有密钥到权限更严格的配置文件，但无法替用户向第三方供应商轮换新密钥；轮换作为部署后人工安全事项。
8. 现场包的 `devices.json`、`central_controller.py`、`ac_ir_codes.json` 和协议文档是硬件行为权威来源；后端旧副本不得覆盖现场新版本。

## 3. 技术栈和官方依据

### 3.1 技术栈

- Python 3.14.5 标准库
- SQLite（`sqlite3`）
- JSON/JSON-RPC 2.0
- `http.server.ThreadingHTTPServer`
- MCP 2025-11-25：Streamable HTTP + stdio
- 现有纯 Python RAG、意图引擎、硬件桥接与国密模块

### 3.2 官方依据

- MCP Streamable HTTP：单一 `/mcp` 端点；POST 接收 JSON-RPC；无服务端 SSE 时 GET 返回 405；验证 `Origin`；使用认证。
  - https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP Tools：通过 `tools/list` 发现，通过 `tools/call` 调用；工具使用 JSON Schema 描述输入。
  - https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- MCP Resources：通过 `resources/list` 发现，通过 `resources/read` 读取。
  - https://modelcontextprotocol.io/specification/2025-11-25/server/resources
- Python 3.14 `sqlite3`：使用参数绑定、显式事务提交和独立连接。
  - https://docs.python.org/3/library/sqlite3.html
- Python 3.14 `json`：限制不可信 JSON 输入大小。
  - https://docs.python.org/3.14/library/json.html

## 4. 方案选择

### 4.1 采用方案

采用“常驻核心上下文 + 结构化匹配 + RAG 检索 + MCP 主动读取”的混合方案。

### 4.2 未采用方案

#### 每轮注入全部原始信息

优点：表面上最完整。  
拒绝原因：日志和数据库会持续增长，原样注入会挤占有效上下文，降低匹配精度并增加上游调用成本。

#### 纯 RAG

优点：上下文较小。  
拒绝原因：安全边界、实时状态和工具能力可能因为召回分数不足而缺失。

## 5. 架构

```text
源码/文档/配置 ─┐
数据库实体/历史 ─┼─> ContextCollector ─> project_context.json
运行日志/新事件 ─┤          │
实时设备/传感器 ─┘          ├─> ai_context_* SQLite 表
                             │
用户消息 ─> ContextMatcher ──┴─> PromptContextBuilder ─> AI
                  │
                  └─> MCP Resources / Tools
```

### 5.1 模块边界

#### `context_engine.py`

负责数据库迁移、采集、清洗、脱敏、分块、索引、匹配、上下文组装和 JSON 快照输出。它不得直接执行硬件动作。

#### `super_mcp.py`

负责 MCP JSON-RPC 生命周期、资源目录、工具目录、参数校验、权限检查和结果封装。工具执行只能调用显式注册的安全处理器。

#### `gateway_v6.py`

负责：

- 初始化上下文引擎；
- 在现有业务写操作后记录上下文事件；
- 在 AI 对话前构建自动上下文；
- 暴露 `/mcp`；
- 将硬件、场景、联动和管理方法注册为 MCP 工具处理器。

#### `mcp_server_enhanced.py`

改为 stdio MCP 包装器，共享 `super_mcp.py` 的协议和工具定义，不再维护另一套重复工具清单。

#### `intent_engine.py`

保留快速匹配、模糊推理、习惯、情感、异常、能耗和短期对话记忆。新增设备/功能变更后触发上下文同步，不把全量检索逻辑复制到该模块。

#### `hardware_bridge.py`

硬件桥接只负责设备 ID 映射、返回结构和错误分类。动作限频统一由现场版 `central_controller.py` 执行，桥接层不得在同一次动作前重复写入限频状态。

## 6. 项目上下文 JSON

输出路径：`/data/A9/smart_home/project_context.json`。

JSON 顶层结构：

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "2026-07-17T22:00:00+08:00",
  "project": {},
  "runtime": {},
  "capabilities": [],
  "devices": [],
  "sensors": [],
  "scenes": [],
  "automations": [],
  "apis": [],
  "mcpTools": [],
  "protocols": [],
  "safety": {},
  "documentation": [],
  "recentActivity": [],
  "collectionStats": {}
}
```

约束：

- JSON 使用原子替换写入，避免读取半文件。
- JSON 不保存任何密码、Token、API Key、私钥、完整 Authorization 头或门禁密码派生材料。
- `recentActivity` 有数量和字符上限；完整历史保存在数据库。
- 文档正文保存在数据库分块；JSON 只保存摘要、来源、哈希和可用主题。

## 7. SQLite 数据模型

所有表位于主数据库 `/data/A9/control/data/smart_home.db`。

### 7.1 `ai_context_documents`

保存文档、源码符号、API 描述和协议说明的可检索分块。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PRIMARY KEY | 稳定内容 ID |
| source_type | TEXT | source/doc/api/protocol/config |
| source_uri | TEXT | 来源路径或逻辑 URI |
| title | TEXT | 标题 |
| content | TEXT | 脱敏后的正文分块 |
| content_hash | TEXT | SHA-256 |
| keywords_json | TEXT | 关键词与别名 |
| metadata_json | TEXT | 行号、模块、优先级等 |
| priority | INTEGER | 0-100 |
| updated_at | TEXT | 东八区时间 |

### 7.2 `ai_context_entities`

保存动态设备、传感器、场景、接口、能力和联动。

| 字段 | 类型 | 说明 |
|---|---|---|
| entity_type | TEXT | device/sensor/scene/api/capability/rule |
| entity_id | TEXT | 实体 ID |
| name | TEXT | 显示名 |
| aliases_json | TEXT | 别名 |
| capabilities_json | TEXT | 能力与参数 Schema |
| state_json | TEXT | 非敏感实时状态 |
| source | TEXT | code/db/custom/runtime |
| enabled | INTEGER | 是否启用 |
| updated_at | TEXT | 更新时间 |

联合主键：`(entity_type, entity_id)`。

### 7.3 `ai_context_events`

保存操作、日志、告警、安全事件、MCP 调用和配置变化。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 事件 ID |
| event_type | TEXT | 事件类型 |
| entity_type | TEXT | 可空 |
| entity_id | TEXT | 可空 |
| summary | TEXT | 脱敏摘要 |
| details_json | TEXT | 脱敏结构化详情 |
| source | TEXT | 来源 |
| severity | TEXT | info/warning/high/critical |
| created_at | TEXT | 创建时间 |

### 7.4 `ai_context_sync_state`

保存文件哈希、日志读取偏移和同步状态，保证增量采集不会重复导入。

### 7.5 `ai_context_snapshots`

保存有限数量的上下文快照摘要，用于启动恢复和问题追踪；保留最近 20 个。

## 8. 数据采集

### 8.1 静态采集

采集范围：

- `gateway_v6.py`、`intent_engine.py`、`hardware_bridge.py`、`central_controller.py`、`protocol_gateway.py`、`gm_crypto.py`、`safety_shield.py`、`channel.py`、`data_pusher.py`、`rag/`、`scenes/`；
- 现场启动脚本包内的 `devices.json`、`central_controller.py`、`voice_remote_bridge.py`、`ac_ir_codes.json`、协议说明、安全说明和现场演示说明；
- 所有项目 Markdown 文档；
- `devices.json` 的非敏感字段；
- 数据库 Schema；
- 启动脚本的命令和变量名，但不采集变量值；
- HTTP API 和 MCP 工具定义。

Python 源码通过 `ast` 提取模块、类、函数、公开方法、路由和文档字符串，不把整个源文件无差别塞进每轮 Prompt。

### 8.2 动态采集

采集范围：

- `devices`、`sensors`、`scenes`、`device_registry`；
- `linkage_config`、`linkage_log`；
- `device_operations`、`sensor_readings`；
- `chat_history`、`conversation_memory`、`memory_store`；
- `security_events`、`remote_access_log`；
- `scheduled_tasks`、`push_history`、`push_config` 的非敏感字段；
- 网关、通道、推送和协议日志；
- 实时硬件状态与服务状态。

### 8.3 采集时机

- 网关启动：全量同步。
- 每 30 秒：设备、传感器、场景、联动和运行状态增量同步。
- 每 5 分钟：文档、源码哈希和日志偏移同步。
- 写穿事件：设备操作、场景执行、联动配置、自定义设备/能力注册、安全事件和 MCP 调用完成后立即记录。
- 管理接口：允许手工触发全量重建和查看同步状态。

## 9. 相关性匹配与上下文注入

### 9.1 匹配步骤

1. 标准化用户文本，保留中英文、数字、设备 ID 和 API 路径。
2. 精确匹配设备 ID、设备名、别名、房间、功能名、接口名和事件类型。
3. 结构化匹配时间范围、日志、历史、状态、配置、故障和控制意图。
4. 对文档与事件执行分词重合、短语命中、实体命中、来源优先级、严重度和时间衰减评分。
5. 合并去重，按预算截取。

### 9.2 每轮上下文结构

```text
系统不可变规则
当前能力与可调用工具
实时设备/传感器/联动状态
匹配到的实体
匹配到的文档/源码能力
最近相关操作和日志
相关对话/记忆
RAG 知识
```

默认预算：

- 核心常驻：最多 12,000 字符；
- 相关文档与实体：最多 24,000 字符，最多 40 个结果；
- 相关事件与历史：最多 12,000 字符，最多 60 个结果；
- 总自动上下文：默认最多 48,000 字符，可由 `AI_CONTEXT_MAX_CHARS` 调整；
- 同一内容通过哈希去重。

### 9.3 开场词判定

仅在以下条件全部满足时跳过大上下文：

- 当前是会话第一条用户消息；
- 文本长度不超过 12 个中文字符或 24 个 ASCII 字符；
- 只匹配“你好、您好、在吗、hello、hi、开始”等问候；
- 不包含设备、房间、动作、功能、故障、日志或查询词。

第一条消息只要包含实质任务，仍执行完整检索。

## 10. 自定义设备和功能

### 10.1 自定义设备

沿用并扩展 `DeviceRegistry`：

- 设备必须有稳定 ID、名称、类型、房间和能力列表；
- 每个能力包含动作名、参数 JSON Schema、是否只读、是否破坏性和执行器；
- 注册成功后同步 `device_registry`、`ai_context_entities` 和 `project_context.json`；
- IntentMatcher 刷新别名和动态意图；
- MCP 的通用 `control_device` 工具立即能够发现该设备及其能力。

### 10.2 自定义能力

允许注册的执行器类型：

- `device_toggle`
- `device_control`
- `scene_activate`
- `safe_internal_api`
- `read_only_query`

禁止：

- 任意 shell；
- 任意 Python 表达式；
- 任意文件路径；
- 任意外部 URL；
- 绕过门禁密码；
- 直接访问密钥数据库。

## 11. 毫米波功能

新增独立配置：

```json
{
  "radar_presence": {
    "enabled": true,
    "source_device": "radar_01",
    "description": "毫米波人体存在感知总开关"
  }
}
```

现有 `radar_light` 继续表示“检测到人体后自动开灯”，不得充当毫米波传感器总开关。

毫米波硬件与稳定匹配参数必须来自现场 `devices.json`：

- `source_device=bathroom`；
- `sensor=Rd-03 V2`；
- 有效距离 20-110cm；
- 厨房 20-35cm、卫生间 40-55cm、客厅 60-85cm、卧室 90-110cm；
- `sample_window=7`、`stable_samples=5`；
- 区间之间的空档是防抖缓冲区，不得自动填平。

部署迁移规则：

- 若 `radar_presence` 不存在，创建并设为 `enabled=true`；
- 不改变现有 `radar_light.enabled`；
- AI 上下文必须同时说明两者状态；
- MCP 提供 `get_radar_config` 和 `set_radar_enabled`；后者需要 admin/write 权限并记录审计。

## 12. 门禁密码

门禁动作包括 `open` 和 `close`，统一规则如下：

1. HTTP、MCP、AI 指令和内部调用最终都必须经过同一个门禁策略函数。
2. 每次动作请求必须携带本次用户手工输入的 `password`。
3. 缺少密码直接拒绝，不允许从环境变量、数据库、对话记忆或上次请求回填。
4. 密码只在当前调用栈内存中短暂存在。
5. 日志和 MCP 审计只记录 `passwordProvided: true/false`，不得记录值、长度、哈希或前缀。
6. AI 模型不得看到密码字段值；在调用上游模型前必须递归脱敏。
7. `tools/list` 将门禁工具标为非只读、可能破坏性，并在描述中明确“必须人工当次输入”。
8. 自动化、定时任务、场景和 AI 大模型输出不得直接执行门禁开关。
9. 语音帧中的门禁开/关、回家和离家动作不得读取预存环境变量自动通过；没有当次人工密码确认时，门禁子动作必须拒绝，其他非门禁子动作不得借机绕过该规则。

## 13. MCP 设计

### 13.1 传输

- HTTP 端点：`POST /mcp`。
- `GET /mcp` 在未实现 SSE 时返回 `405 Method Not Allowed`。
- 支持 `MCP-Protocol-Version: 2025-11-25`；初始化前兼容 `2025-03-26` 请求。
- POST 接受 `application/json`，响应 `application/json`。
- 请求体最大 1 MiB。
- 验证 `Origin`：仅允许明确配置的前端来源；无 Origin 的非浏览器客户端按认证规则处理。
- `/mcp` 不享受现有局域网自动 admin；至少需要 API Key 或 Bearer Token。可为本机 stdio 单独免 HTTP 认证。

### 13.2 MCP 方法

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`

未知方法返回 JSON-RPC `-32601`；参数错误返回 `-32602`；工具业务失败放在 `CallToolResult.isError=true`。

### 13.3 MCP Resources

- `a9://project/manifest`
- `a9://project/capabilities`
- `a9://devices`
- `a9://sensors`
- `a9://scenes`
- `a9://automations`
- `a9://apis`
- `a9://security/policy`
- `a9://context/stats`
- `a9://context/search/{query}`（资源模板）

### 13.4 MCP Tools

只读工具：

- `search_context`
- `get_project_overview`
- `get_context_stats`
- `get_live_status`
- `list_devices`
- `get_device`
- `list_sensors`
- `get_recent_operations`
- `get_recent_logs`
- `get_linkage_config`
- `get_radar_config`
- `list_capabilities`

写工具：

- `toggle_device`
- `control_device`
- `activate_scene`
- `set_linkage_config`
- `set_radar_enabled`
- `register_device`
- `unregister_device`
- `register_capability`
- `rebuild_context`
- `door_control`

`door_control` 不允许通过模型自动构造密码；客户端必须把人工输入作为工具参数提交。

## 14. HTTP 管理接口

新增接口：

- `GET /api/ai/context/manifest`
- `GET /api/ai/context/stats`
- `POST /api/ai/context/search`
- `POST /api/ai/context/rebuild`
- `GET /api/ai/context/events`
- `GET /api/ai/radar/config`
- `POST /api/ai/radar/config`
- `POST /mcp`
- `GET /mcp` → 405

现有 KV、联动、设备、传感器、场景和安全接口继续保留。

## 15. 错误处理和可观测性

- 采集单个来源失败不阻塞网关启动；状态记录到 `ai_context_sync_state`。
- JSON 生成失败保留上一个有效版本。
- 上下文构建失败退化为核心能力 + 实时状态，不影响普通对话。
- MCP 工具调用记录工具名、调用方、结果、耗时和脱敏参数。
- 日志设置轮转/保留策略，避免 `remote_access_log` 和推送队列无限增长。
- 所有返回给客户端的异常使用稳定错误码，不返回完整堆栈或密钥路径内容。

## 16. 安全边界

### 16.1 始终执行

- 参数化 SQL。
- 密码、Token、Key、私钥递归脱敏。
- MCP Origin 校验和认证。
- 工具参数按 JSON Schema 和业务白名单双重校验。
- 门禁密码每次人工输入。
- 写工具记录审计。
- 部署前生成设备端时间戳备份。
- 修改后运行完整测试与真实健康检查。

### 16.2 需要用户另行授权

- 向第三方供应商申请或轮换 API Key。
- 改变毫米波当前启用状态。
- 改变 `radar_light` 自动开灯现有状态。
- 真实执行门禁开门/关门测试。
- 删除历史数据库、日志或旧版本文件。

### 16.3 绝不执行

- 把秘密写入文档、JSON、日志或测试输出。
- 让模型直接执行任意 shell、SQL、URL 或文件操作。
- 把局域网来源自动视为 MCP admin。
- 在没有密码时执行门禁动作。
- 为了测试而清空或替换生产数据库。

## 17. 项目结构

```text
/data/A9/smart_home/
  gateway_v6.py                 主网关，集成上下文和 HTTP MCP
  context_engine.py             采集、索引、匹配、注入
  super_mcp.py                  MCP 协议与工具注册
  mcp_server_enhanced.py        stdio MCP 包装器
  project_context.json          生成的脱敏上下文快照
  tests/
    test_context_engine.py
    test_super_mcp.py
    test_gateway_context.py
    test_security_invariants.py
  docs/
    A9_SUPER_CONTEXT_MCP_ALIGNMENT.md
```

桌面基线目录保持同样的源码和测试文件；最终对齐文档另存到用户桌面。

## 18. 代码风格

- 兼容 Python 3.14 标准库，不引入 pip 包。
- 模块职责单一；避免继续把全部逻辑堆入 `gateway_v6.py`。
- 公共函数使用类型标注和简短 docstring。
- 返回结构使用稳定字典格式。
- 数据库连接按操作创建并关闭；事务显式提交。

示例：

```python
def record_event(
    event_type: str,
    summary: str,
    *,
    details: dict | None = None,
    entity_id: str | None = None,
) -> int:
    """Persist one redacted context event and return its database id."""
    safe_details = redact_sensitive(details or {})
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO ai_context_events(event_type, entity_id, summary, details_json) "
            "VALUES(?, ?, ?, ?)",
            (event_type, entity_id, summary, json.dumps(safe_details, ensure_ascii=False)),
        )
    return int(cursor.lastrowid)
```

## 19. 命令

### 19.1 本地语法检查

```powershell
python -m compileall `
  C:\Users\xyls\Desktop\A9_backend_upgrade\gateway_v6.py `
  C:\Users\xyls\Desktop\A9_backend_upgrade\context_engine.py `
  C:\Users\xyls\Desktop\A9_backend_upgrade\super_mcp.py
```

### 19.2 本地测试

```powershell
python -m unittest discover `
  -s C:\Users\xyls\Desktop\A9_backend_upgrade\tests `
  -p "test_*.py" `
  -v
```

### 19.3 设备启动

```powershell
hdc -t d6290341334135353210f41a68f0bb00 shell "sh /data/A9/run_v6.sh"
```

### 19.4 设备健康检查

```powershell
hdc -t d6290341334135353210f41a68f0bb00 shell `
  "/data/A9/python-portable/lib/ld-musl-armhf.so.1 --library-path /data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib /data/A9/python-portable/usr/bin/python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/health\", timeout=5).read().decode())'"
```

## 20. 测试策略

### 20.1 TDD 顺序

1. 先编写上下文数据库迁移、脱敏和匹配的失败测试。
2. 实现最小 `context_engine.py` 使测试通过。
3. 先编写 MCP initialize/list/read/call 失败测试。
4. 实现最小 `super_mcp.py` 使测试通过。
5. 先编写对话自动注入和开场跳过失败测试。
6. 集成网关并使测试通过。
7. 先编写动态设备、毫米波和门禁安全失败测试。
8. 完成写穿同步和工具处理器。

### 20.2 单元测试

- 数据库建表可重复执行。
- JSON 快照合法、原子、无秘密。
- 文档和事件分块、去重、相关性排序。
- 开场问候跳过；实质首句不跳过。
- 自定义设备和能力自动进入实体、JSON 和检索。
- 密码递归脱敏。
- 门禁缺少密码必定拒绝。
- 毫米波功能和雷达灯光开关互不影响。
- MCP JSON-RPC 错误码、工具 Schema、资源读取和工具结果格式。
- Origin 和认证校验。

### 20.3 集成测试

- 使用临时 SQLite 数据库，不修改生产数据。
- 使用假的硬件桥接器验证控制调用。
- 验证一次设备操作立即进入上下文事件并可检索。
- 验证 AI Prompt 包含核心上下文和相关结果，不包含无关大日志。
- 验证新设备注册后无需重启即可被查询和控制。

### 20.4 设备验收

- 设备端所有修改文件可被 Python AST 解析。
- 网关进程运行，8080 监听，`/health` 返回成功。
- `POST /mcp` 完成 initialize、tools/list、resources/list。
- 上下文 JSON 存在、合法且不含秘密模式。
- 数据库上下文表存在且有文档、实体和事件。
- 普通对话可在日志中证明执行了上下文匹配。
- 开场问候不触发大上下文。
- 毫米波功能为 enabled。
- 门禁缺少密码返回拒绝，且日志无密码。
- 可恢复灯光控制测试后恢复测试前状态。
- 重启一次网关后再次通过健康检查。
- 验证 `/etc/init/smart_home.cfg` 仍指向有效启动脚本；不通过整机重启测试开机启动，以避免未经确认重启设备。

## 21. 部署与回滚

### 21.1 部署

1. 保存设备端 `gateway_v6.py`、`run_v6.sh`、数据库和相关模块的时间戳备份。
2. 推送新增模块和测试。
3. 推送修正后的 `gateway_v6.py`。
4. 迁移数据库，迁移必须可重复执行。
5. 将明文运行时凭据迁移到 root-only 配置文件，启动脚本只加载文件，不打印值。
6. 启动网关并执行设备验收。

### 21.2 回滚

- 停止新网关。
- 恢复时间戳备份源码和启动脚本。
- 新增上下文表保留，不影响旧网关；如确需删除，必须另行获得用户授权。
- 重新启动旧网关并验证旧健康接口。

## 22. 文档交付

最终桌面文档必须包含：

- 真实架构与数据流；
- 全部 HTTP API；
- MCP 连接、初始化、资源、工具和调用示例；
- `project_context.json` Schema；
- SQLite 新表 Schema；
- 前端类型定义与调用示例；
- 服务端调用示例；
- 自定义设备/能力注册流程；
- 毫米波与雷达联动的差异；
- 门禁密码人工输入规则；
- 启动、自启动、健康检查、日志和排错；
- 安全风险、凭据轮换和回滚步骤；
- 设备实测结果与当前已知限制。

## 23. 成功标准

只有以下条件全部满足才可宣称完成：

1. 新增测试先失败、实现后全部通过，并保留红绿证据。
2. 本地完整测试零失败。
3. 设备端网关可启动并持续运行。
4. HTTP 健康、上下文接口和 MCP 核心方法实测成功。
5. 上下文至少包含源码/文档、16 个设备、9 个传感器、5 个场景、API、联动、日志和历史事件。
6. 每次非开场对话自动执行上下文匹配和注入。
7. 新自定义设备/能力可自动进入上下文并通过 MCP 查询。
8. 毫米波功能保持启用且与雷达开灯联动独立。
9. 门禁无密码无法执行，密码不出现在任何持久化内容或日志中。
10. 合法硬件动作只执行一次限频检查，不被桥接层和中控层重复限频。
11. 开机启动配置指向已验证的启动脚本。
12. 桌面完整对齐文档生成并与实际实现一致。

## 24. 明确不在本次范围

- 修改 HarmonyOS 前端页面实现；本次只提供完整对齐文档和类型/调用示例。
- 申请第三方 AI、QQ 或隧道的新凭据。
- 重写所有旧版网关和历史补丁文件。
- 引入向量数据库、外部 embedding 服务或 pip 依赖。
- 实验性 MCP Tasks。
- 真实门禁动作和整机重启测试。

## 25. 开放问题

无。设计中未决项均已采用安全默认值；任何超出本规格的外部凭据轮换、真实门禁动作或整机重启必须另行获得用户授权。
