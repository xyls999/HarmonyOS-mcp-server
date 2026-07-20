# AGENTS.md — 智慧家居（HarmonyOS NEXT）项目指南

> 本文件面向 AI Coding Agent。阅读者被假设为完全不了解本项目。
> 项目内源码注释、界面文案、文档均以中文为主，因此本文件使用中文撰写。

---

## 1. 项目概述

- **应用名称**：智慧家居 / Smart Home
- **包名**：`com.smarthome.harmony`
- **版本**：`1.0.0`（`versionCode: 1000000`）
- **平台**：HarmonyOS NEXT（SDK `6.1.1(24)`，兼容 `5.0.0(12)`）
- **形态**：单 Module 手机应用（entry HAP），Stage 模式
- **开发语言**：ArkTS + ArkUI 声明式 UI（`.ets`）
- **当前状态**：前端可独立运行，所有 API 已实现「HTTP 优先 → 失败降级到本地 Mock」策略。后端网关可选配 Python 脚本运行。

### 1.1 主要功能

应用采用底部 Tab + 中央 AI 悬浮入口，共五个主页面：

| Tab | 页面 | 说明 |
| --- | --- | --- |
| 首页 | `HomePage` | 问候头图、场景快捷、设备网格、环境概览、AI 快捷入口 |
| 监控 | `MonitorPage` | 摄像头网格、传感器按分组看板、警报消息流 |
| 历史 | `HistoryPage` | 今日概览、能耗趋势、可展开二维对比图表、近期日志 |
| AI 助手 | `ChatPage` | 大模型对话，支持流式打字效果与语音占位 |
| 我的 | `MinePage` | 用户信息、服务端管理（WiFi / 星闪）、设置项 |

另有三个详情页：`DeviceDetailPage`、`SensorDetailPage`、`CameraDetailPage`，以及一个 `AddDevicePage` 添加设备页。

---

## 2. 技术栈与构建体系

### 2.1 核心技术栈

| 层级 | 技术 |
| --- | --- |
| UI 框架 | ArkTS / ArkUI（声明式） |
| 网络 | `@kit.NetworkKit` 的 `http` 模块 |
| 日志 | `@kit.PerformanceAnalysisKit` 的 `hilog` |
| 路由 | `@kit.ArkUI` 的 `router` |
| 测试框架 | `@ohos/hypium`（单元 +  instrument） |
| Mock 工具 | `@ohos/hamock` |
| 构建系统 | Hvigor（DevEco Studio 内置） |
| 包管理 | OHPM（OpenHarmony Package Manager） |

### 2.2 关键配置文件

| 文件 | 作用 |
| --- | --- |
| `build-profile.json5` | 应用级编译配置：签名、SDK 版本、products、modules |
| `entry/build-profile.json5` | Entry 模块级配置：stageMode、混淆、target（含 ohosTest） |
| `hvigor/hvigor-config.json5` | Hvigor 构建选项（默认全部注释，使用 DevEco Studio 默认行为） |
| `hvigorfile.ts` / `entry/hvigorfile.ts` | Hvigor 任务入口，分别引入 `appTasks` / `hapTasks` |
| `oh-package.json5` | 项目级依赖（当前仅 devDeps：`hypium`、`hamock`） |
| `entry/oh-package.json5` | Entry 模块自身依赖（当前为空） |
| `code-linter.json5` | 代码静态检查规则，作用于 `**/*.ets` |
| `AppScope/app.json5` | 应用级元数据：包名、版本、图标、名称 |
| `entry/src/main/module.json5` | 模块元数据：Ability 声明、页面路由、权限（INTERNET） |

### 2.3 构建与运行方式

> **本项目没有纯 CLI 构建工作流，日常开发使用 DevEco Studio。**

| 操作 | 方式 |
| --- | --- |
| 构建 HAP/App | DevEco Studio → Build → Build Hap(s)/App(s) |
| 预览 | DevEco Studio → Previewer（phone profile） |
| 真机/模拟器运行 | DevEco Studio → Run；需 `build-profile.json5` 中签名配置正确 |
| 代码检查 | 由 `code-linter.json5` 驱动，DevEco Studio 自动执行 |
| 单元测试 | `entry/src/test/`（Hypium 本地单元测试） |
| 仪器测试 | `entry/src/ohosTest/`（Hypium instrument 测试） |

### 2.4 构建注意事项

- `build-profile.json5` 中 `signingConfigs[0].material` 包含作者本地调试签名材料的绝对路径（`C:\Users\xyls\.ohos\config\...`）。跨机器运行时必须重新配置签名，否则构建/真机安装会失败。
- `mkjunction.bat` 用于在 Windows 上创建 SDK 目录的 junction 链接（`sdk\default\24 → sdk\default\openharmony`），解决某些 DevEco Studio 版本的 SDK 路径识别问题。需要管理员权限执行。
- 项目未开启 release 混淆（`obfuscation.enable: false`）。

---

## 3. 代码组织与模块划分

### 3.1 顶层目录

```
.
├── AppScope/               # 应用级资源与 app.json5
├── entry/                  # 唯一 HAP 模块
│   ├── src/main/           # 主源码
│   ├── src/ohosTest/       # instrument 测试
│   ├── src/test/           # 本地单元测试
│   ├── src/mock/           # DevEco mock 配置
│   └── build/              # 构建产物（gitignored）
├── hvigor/                 # Hvigor 配置
├── oh_modules/             # OHPM 依赖安装目录（gitignored）
├── smart_home_gateway.py   # Python 网关 v1（HTTP + DeepSeek）
├── smart_home_gateway_v2.py# Python 网关 v2（门禁 socket、温湿度 TCP、MAC 发现）
├── run_gateway.sh          # 在嵌入式/开发板上启动 v2 网关的脚本
└── mkjunction.bat          # Windows SDK junction 辅助脚本
```

### 3.2 主源码目录（`entry/src/main/ets/`）

```
api/            # 数据层：类型定义 + HTTP 客户端 + 各类 API 封装
  types.ets     # 所有业务数据模型与枚举（Device、Sensor、Camera、Scene、UserProfile 等）
  http.ets      # HTTP 客户端：自动尝试多个网关地址，失败返回 null
  adapter.ets   # 后端 JSON 到前端类型的归一化/图标映射
  deviceApi.ets # 设备 CRUD + 控制（风扇/空调/门禁/灯光）+ BearPi 命令
  sensorApi.ets # 传感器查询 + 实时订阅模拟 + 温湿度历史
  monitorApi.ets# 摄像头 + 警报消息
  chatApi.ets   # 大模型对话，支持超时保护与打字机效果
  sceneApi.ets  # 场景激活
  userApi.ets   # 用户资料 + 服务端状态
components/     # 可复用 UI 组件
  AppCard.ets, AppIcon.ets, DeviceCard.ets, SensorCard.ets, CameraCard.ets,
  SectionHeader.ets, ChatBubble.ets, StatRing.ets, ServerManagerPanel.ets
effects/        # 动效组件
  AnimatedNumber.ets
entryability/   # 应用生命周期
  EntryAbility.ets
entrybackupability/
  EntryBackupAbility.ets
mock/           # 本地 Mock 数据
  mockData.ets
pages/          # 页面
  Index.ets, HomePage.ets, MonitorPage.ets, HistoryPage.ets, ChatPage.ets, MinePage.ets,
  AddDevicePage.ets,
  detail/DeviceDetailPage.ets, detail/SensorDetailPage.ets, detail/CameraDetailPage.ets
theme/          # 设计令牌
  Colors.ets, Spacing.ets, Typography.ets, Effects.ets
```

### 3.3 路由声明

页面路由集中在 `entry/src/main/resources/base/profile/main_pages.json`：

```json
{
  "src": [
    "pages/Index",
    "pages/AddDevicePage",
    "pages/detail/DeviceDetailPage",
    "pages/detail/SensorDetailPage",
    "pages/detail/CameraDetailPage"
  ]
}
```

`Index` 是入口 Ability 加载的主页面，内部通过 `@State currentIndex` 切换 Tab，不使用路由栈切换 Tab。详情页通过 `router.pushUrl` 打开并传递 `params`。

---

## 4. 架构约定

### 4.1 API 层契约

- 所有数据访问必须走 `api/` 下的 API 类，**页面/组件禁止直接导入 `MockData`**。
- 每个 API 方法优先尝试 HTTP 调用后端网关；失败（返回 `null` 或异常）时降级到 `MockData`。
- 当前 `Http` 客户端内置三个候选地址：
  - `http://127.0.0.1:8080`（App 与网关同设备运行）
  - `http://192.168.1.81:8080`
  - `http://192.168.1.62:8080`
- 首次成功后，`Http.activeBase` 会被记住，后续请求优先使用成功过的地址。
- 返回类型保持固定；未来接入真实后端时，只需替换方法体，签名与返回类型不变。

### 4.2 数据模型

- 所有业务类型定义在 `api/types.ets`。
- 图标字段统一使用 HarmonyOS 原生 `SymbolGlyph` 系统图标库（`$r('sys.symbol.xxx')`），渲染时使用 `SymbolGlyph(icon).fontColor([color])`。
- 设备类型：`FAN` / `AC` / `DOOR` / `LIGHT` / `CAMERA`。
- 传感器类型包括：温度、湿度、空气质量、光照、人体存在、门窗、烟雾、水浸、功率、体重、姿态。
- 通信协议字段：`wifi` 或 `starflash`（星闪）。

### 4.3 设计系统

- 所有颜色、间距、字号、圆角必须来自 `theme/` 下的常量类（`AppColors`、`AppSpace`、`AppFont`），禁止硬编码样式值。
- 当前视觉方向为「经典鸿蒙浅色」：白色卡片、浅灰青页面底色、主色 `#1D7F68`。
- 语义色：`SUCCESS` / `WARNING` / `DANGER` / `ONLINE` / `OFFLINE`。

### 4.4 关键组件模式

- `DeviceCard`、`SensorCard`、`CameraCard` 等卡片依赖 `@Prop` 接收数据，内部维护本地状态以提供即时交互反馈，再异步调用 API。
- `DeviceCard` 对风扇、空调、灯光提供 ±1 调节，对门禁显示「已锁定/已开锁」。
- 设备开关会联动发送 BearPi 命令（仅限 `LIGHT` 类型，命令格式 `brightness:{room}:{value}`）。

---

## 5. 后端网关

项目包含两个可选的 Python 网关，用于在真实设备/开发板上对接硬件。

### 5.1 `smart_home_gateway.py`（v1）

- 纯标准库实现（`http.server`、`sqlite3`、`urllib`）。
- 默认监听 `0.0.0.0:8080`。
- 提供 RESTful API：设备、传感器、摄像头、警报、用户资料、服务端状态、大模型对话。
- 设备控制数据写入 `control/data/control.db`。
- 大模型对话调用 DeepSeek API（`deepseek-v4-flash`），密钥从环境变量或 `HarmonyOS-mcp-server/.deepseek_env` 加载。

### 5.2 `smart_home_gateway_v2.py`（v2，主要使用）

- 在 v1 基础上增加：
  - 门禁二进制帧控制（socket 自定义协议）。
  - DHT11 温湿度传感器 TCP 数据监听。
  - BearPi 开发板命令（亮度、人感、雷达参数查询）。
  - MAC → IP 自动发现，设备注册表持久化到 `device_registry.json`。
- 配套启动脚本：`run_gateway.sh`，默认运行于 `/data/A9` 嵌入式环境。
- v2 网关启动后常驻后台，App 通过 HTTP 与其通信。

### 5.3 网关与 App 的集成

- App 端 `Http` 会自动探测网关；未探测到时完全使用本地 Mock。
- 因此：**没有运行网关时，App 仍可正常预览和交互**（所有数据来自 `MockData`）。

---

## 6. 测试策略

### 6.1 测试目录

| 目录 | 类型 | 说明 |
| --- | --- | --- |
| `entry/src/test/` | 本地单元测试 | `LocalUnit.test.ets` + `List.test.ets` |
| `entry/src/ohosTest/` | Instrument 测试 | `Ability.test.ets` + `List.test.ets` |

### 6.2 当前测试状态

- 当前测试文件仅包含 Hypium 框架的占位示例（`assertContain` 等），没有针对业务逻辑的断言。
- `code-linter.json5` 已忽略 `src/test/**/*` 和 `src/ohosTest/**/*`。

### 6.3 建议的测试补充方向

- API 层：验证 `normalizeDevice`、`normalizeSensor` 对缺失字段的降级处理。
- `MockData`：验证场景动作数量、传感器阈值等。
- UI 组件：验证 `DeviceCard.valueLabel` 在不同设备类型下的文案。

---

## 7. 代码风格与开发规范

### 7.1 语言与注释

- 源文件扩展名 `.ets`。
- 注释、文档字符串、界面文案使用中文。
- 代码中涉及的 API 路径、类型名、变量名使用英文。

### 7.2 ArkUI 常用装饰器

- `@Entry`：页面入口。
- `@Component` / `struct`：组件声明。
- `@State`：组件内部状态。
- `@Prop`：父传子只读属性。
- `@Link` / `@Builder`：按需使用。

### 7.3 静态检查规则

`code-linter.json5` 配置：

- 文件范围：`"**/*.ets"`
- 规则集：`plugin:@performance/recommended`、`plugin:@typescript-eslint/recommended`
- 安全规则：启用 `@security/no-unsafe-aes/hash/mac/dh/dsa/ecdsa/rsa/3des` 等，多为 `error` 级别。

### 7.4 开发禁忌

- 禁止页面/组件直接依赖 `MockData`。
- 禁止硬编码颜色、间距、字号（应使用 `theme/` 常量）。
- 禁止在 API 调用中永久阻塞 UI；已实现的超时保护（如 `ChatApi.raceTimeout`）应作为模式参考。

---

## 8. 安全与隐私注意事项

- `build-profile.json5` 包含明文存储的本地调试签名密钥与密码，**不可提交到公共仓库**。生产构建必须替换为正式签名。
- `run_gateway.sh` 中硬编码了 `DEEPSEEK_API_KEY`，属于敏感信息，应避免泄露。
- 当前 HTTP 通信未启用 TLS，且使用明文 JSON。若部署到公网或不可信网络，需升级为 HTTPS 并校验服务端证书。
- `ohos.permission.INTERNET` 已在 `module.json5` 中声明。
- 代码规范强制启用了多条安全 lint 规则，改动密码学相关代码时需特别注意。

---

## 9. 部署与运行流程

### 9.1 纯前端预览（最常见）

1. 用 DevEco Studio 打开项目。
2. 等待 Hvigor 同步完成。
3. 点击 Previewer，选择 phone 设备即可预览。

### 9.2 真机/模拟器运行

1. 确保 `build-profile.json5` 中的签名配置有效（或重新生成调试签名）。
2. DevEco Studio → Run。

### 9.3 启动后端网关（可选）

本地开发：

```bash
python3 smart_home_gateway.py
# 或
python3 smart_home_gateway_v2.py
```

嵌入式环境：

```bash
sh run_gateway.sh
```

网关启动后，App 会自动探测 `127.0.0.1:8080` 或局域网候选地址，优先使用真实数据。

---

## 10. 给 Agent 的快速工作清单

- 修改 UI 前先检查 `theme/` 是否已有对应的设计令牌。
- 新增/修改数据结构时，优先更新 `api/types.ets`，再同步到 `mock/mockData.ets` 和 `api/adapter.ets`。
- 新增页面必须同时更新 `main_pages.json`。
- 新增后端接口时，应在 `http.ets` 中通过 `Http.get` / `Http.post` 调用，并保持「失败降级到 Mock」的策略。
- 修改测试后，确保 `code-linter.json5` 没有新增 lint 错误。
- 不要提交签名材料、API 密钥、网关日志、构建产物。

---

## 11. 参考文件索引

| 目的 | 文件 |
| --- | --- |
| 快速了解项目意图 | `CLAUDE.md` |
| 应用元数据 | `AppScope/app.json5` |
| 模块与权限 | `entry/src/main/module.json5` |
| 页面路由 | `entry/src/main/resources/base/profile/main_pages.json` |
| 业务类型 | `entry/src/main/ets/api/types.ets` |
| Mock 数据 | `entry/src/main/ets/mock/mockData.ets` |
| HTTP 与地址探测 | `entry/src/main/ets/api/http.ets` |
| 网关 v1 | `smart_home_gateway.py` |
| 网关 v2 | `smart_home_gateway_v2.py` |
| 启动脚本 | `run_gateway.sh` |
