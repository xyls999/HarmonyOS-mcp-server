# Spec: 时间线事件、自动管理输出与精细图表

## Objective

让助手按真实发生时间展示对话和自动事件：发生在最新用户消息之前的事件必须排在消息之前，不能全部追加到对话末尾。确定性自动管理与 AI 警戒分层，自动管理不依赖评分才执行，但每次执行都要保存原因、设备、动作、结果、时间和图表数据；AI 警戒只生成低频、可评价的建议。

## Tech Stack

- OpenHarmony ArkTS API 12，`oh-package.json5` modelVersion 6.0.1。
- D6 后端 Python 3.14 + SQLite，运行目录 `/data/A9/smart_home`。
- 前端图表组件 `ChatChartPanel`，数据通过 `AssistantApi` 获取。

## Commands

```text
Frontend contract tests: python tests/test_control_center_contract.py
Frontend build/sign:     & .\tools\build-openharmony.ps1
D6 install:              hdc install -r entry\\build\\default\\outputs\\default\\entry-default-signed.hap
Backend health:          GET http://192.168.1.94:8080/health
```

## Project Structure

- `entry/src/main/ets/pages/ControlPanelPage.ets`: 时间线、助手输出、图表和评分。
- `entry/src/main/ets/api/assistantApi.ets`: 事件时间字段和前端接口契约。
- `entry/src/main/ets/components/ChatChartPanel.ets`: 折线、圆环、雷达图绘制。
- `smart_home/proactive_intelligence.py`: 5 分钟主动扫描、确定性过滤和持久化报告。
- `docs/`: 规格、接口与部署文档。

## Behavior Contract

1. 事件按 `createdTs` 与消息 `timestamp` 合并排序；同一时间事件先于用户消息，稳定排序不丢数据。
2. 启动时允许载入启动前发生的事件，但普通 `summary` 不直接填充助手；warning/danger、设备操作和需要主人确认的事件进入时间线。
3. 确定性自动管理可以直接执行安全联动；评分只影响 AI 学习策略，不阻止硬规则执行。
4. 每个进入时间线的事件必须有时间、触发模式、设备、动作、结果和至少一组图表数据；无后端图表时前端从操作记录生成折线、圆环和雷达图。
5. 主动扫描每 300 秒一次，统计窗口为 300 秒；离线、不可用和失败设备不能生成反复开关警戒。

## Code Style

```ts
interface TimelineEntry {
  id: string;
  kind: 'message' | 'event';
  timestamp: number;
  message?: ChatMessage;
  event?: AssistantFeedItem;
}
```

时间字段使用 `createdTs`（秒）或 `timestamp`（毫秒），所有 UI 文本使用中文可读模板，后端原始 JSON 只作为结构化证据保存。

## Testing Strategy

- 契约测试验证时间字段、时间线排序、自动/AI 模式分层、非柱状多图表和 5 分钟窗口。
- ArkTS 编译验证类型和系统图标资源。
- D6 真机验证：启动前事件顺序、自动管理事件、助手消息、评分、开关和播报。
- 后端验证：`/health`、助手 feed、操作结果、离线过滤、SQLite 持久化。

## Boundaries

- Always: 保留原始日志和评分数据；自动管理动作必须有确定性规则；每次行为写入时间、证据、动作和结果。
- Ask first: 删除历史事件、改变门禁密码策略、改变安全联动阈值。
- Never: 让大模型直接绕过安全规则；把离线设备当作正常设备触发动作；用无时间的事件覆盖真实时间线。

## Success Criteria

- 最新对话之前发生的事件在 UI 中位于该对话之前。
- 非 AI 自动管理事件可以执行且不要求评分才能执行，但可被完整查看和追溯。
- 每个可见事件至少显示三种非柱状图表数据。
- 5 分钟周期和离线过滤在后端测试及 D6 日志中可验证。
- 前端契约测试、ArkTS 编译、D6 安装和运行时无闪退全部通过。

## Open Questions

- 当前默认保留全部历史事件；“清空助手对话”只清理 UI 会话，不删除长期日志。若需要删除数据库历史，必须单独确认。
