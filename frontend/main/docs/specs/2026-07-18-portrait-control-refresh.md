# Spec: A9 竖屏科技主控界面升级

## Assumptions

1. 目标设备仍为 D6 `d6290341334135353210f41a68f0bb00`，前端 HAP 安装到该设备，后端继续在 `/data/A9` 运行。
2. “不要横屏”解释为 Ability 固定竖屏，不提供横屏布局。
3. 温湿度只从“设备控制台”移除，仍保留在“数据管理 > 环境”的趋势与当前值中。
4. 烟雾与热敏不作为状态卡或环境矩阵展示，但真实报警仍显示在日志中，并继续由 D6 后端播报和通知。
5. 删除“通知与安全传输”仅指删除设置页展示，不停止 QQ、HTTPS、MQTT、CoAP 或 WebSocket 后端能力。
6. 不增加第三方依赖，继续使用原生 ArkUI 与现有 `TacticalTheme`。

## Objective

把现有横屏双列控制台改为稳定的竖屏家庭主控。启动阶段提供约 4.6 秒、有明确阶段含义的科技加载动画；页面切换保持约 0.5 秒的空间连续性；设备页按功能分类并使用真实按钮；所有内容在竖屏宽度内换行或滚动，不跳出容器。

## Tech Stack

- OpenHarmony API 12
- ArkTS / ArkUI Stage 模型
- Hvigor + DevEco Studio 工具链
- Python `unittest` 源码契约测试
- HDC 设备安装与运行验证

## Commands

- Contract test: `python -m unittest discover -s tests -v`
- Build and sign: `powershell -ExecutionPolicy Bypass -File tools/build-openharmony.ps1`
- Install: `D:\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe -t d6290341334135353210f41a68f0bb00 install -r entry\build\default\outputs\default\entry-default-signed.hap`
- Start: `D:\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe -t d6290341334135353210f41a68f0bb00 shell aa start -a EntryAbility -b com.example.smarthome`

## Project Structure

- `entry/src/main/module.json5`: Ability 方向契约。
- `entry/src/main/ets/pages/ControlPanelPage.ets`: 启动、主题、页面切换、顶部栏和底部导航。
- `entry/src/main/ets/pages/DeviceCenterPage.ets`: 分类设备控制和门禁密码输入。
- `entry/src/main/ets/pages/SettingsPage.ets`: 联动、主动 AI、毫米波和行为评分。
- `entry/src/main/ets/pages/HistoryPage.ets`: 日志、设备和环境数据展示边界。
- `entry/src/main/ets/theme/TacticalTheme.ets`: 统一颜色、间距和动画时长。
- `tests/test_control_center_contract.py`: 可重复执行的 UI 源码契约。

## Code Style

保持现有 ArkUI Builder 风格。颜色和时长使用语义方法或常量，交互目标至少 48 vp，视觉尺寸可以更小：

```ts
@Builder
themeButton() {
  Stack() {
    Column().width(32).height(32).backgroundColor(this.panel())
    SymbolGlyph($r('sys.symbol.sun_max')).fontSize(17).fontColor([this.accent()])
  }
  .width(48)
  .height(48)
  .accessibilityText('切换到白天模式')
}
```

## Visual and Interaction Contract

- Design read: 原生 OpenHarmony 竖屏家庭主控，深色科技感，强调触控清晰度与信息秩序。
- Dials: `DESIGN_VARIANCE 7`, `MOTION_INTENSITY 7`, `VISUAL_DENSITY 6`。
- 保留现有蓝绿品牌强调色，不引入紫色发光和第三套色系。
- 启动总时长目标 4.4-4.8 秒；进度分五阶段，完成后再淡出。
- `loadingCore` 不使用最外层圆形 Ring；中心结构由扫描轨、菱形框、阶段条和中心图标组成。
- 页面切换目标 480-560ms，只动画透明度与位移，不动画内容宽高。
- 顶栏约 58 vp；主题按钮视觉框 32 vp，触控框 48 vp。
- 底栏约 92 vp；单个导航按钮至少 64 vp 高，标签保持单行。
- 设备页使用单列纵向滚动，分类为“门禁与出入口”“温控与空气”“照明与遮阳”“其他设备”。
- 门禁每次操作仍要求手动密码；密码不进入遥测或日志。
- 设备页不请求或展示传感器快照。
- 环境页保留温湿度；烟雾、热敏和厨房报警状态不出现在环境矩阵。
- 设置页不渲染通知模式、协议端口或安全传输说明。

## Testing Strategy

1. 先扩展 Python 契约测试，并确认它针对旧实现失败。
2. 分片修改方向、外壳动效、设备页、设置页和环境矩阵，每片后运行契约测试。
3. 契约通过后执行完整 HAP 构建和签名。
4. 安装到 D6，启动 Ability，读取进程、窗口方向和 hilog。
5. 截图检查竖屏、无横向溢出、底栏可点击、设备按钮完整。

## Boundaries

- Always: 保留真实 DeviceApi 调用、门禁密码要求、后台日志和播报能力；所有修改必须通过契约测试和 ArkTS 构建。
- Ask first: 新增依赖、修改后端协议、改变设备 ID、修改签名身份。
- Never: 把 QQ Token、AI Key、门禁密码写入源码、测试、日志或文档；用 mock 设备替换真实接口；恢复已删除的客厅氛围灯。

## Success Criteria

- `module.json5` 方向为 `portrait`。
- 启动动画持续约 4.6 秒，最外层圆环消失，进度和阶段持续可见。
- 四个页面切换无横向跳格，切换动画在约 0.5 秒内完成。
- 设备页单列分类，按钮高度不低于 44 vp，所有文案不越界。
- 设备页不出现温度、湿度、烟雾或热敏状态条。
- 烟雾和热敏只通过日志/播报链路呈现，不出现在环境矩阵。
- 设置页不存在“通知与安全传输”及其下属协议区域。
- 顶部主题按钮容易点击，底部四个导航按钮更高。
- Python 契约测试、ArkTS 构建、签名、D6 安装和启动均成功。

## Open Questions

无。用户已批准方案 B。
