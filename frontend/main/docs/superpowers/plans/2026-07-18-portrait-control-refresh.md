# A9 Portrait Control Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 A9 前端改造成可在 D6 上稳定运行的竖屏科技主控，并满足动画、分类、传感器展示边界和触控尺寸要求。

**Architecture:** 保持现有四页面外壳和真实 API，不新增依赖。先用源码契约锁定竖屏、动效和内容边界，再逐层调整外壳、设备页、设置页与环境页，最后在 D6 做构建安装验证。

**Tech Stack:** ArkTS, ArkUI, OpenHarmony API 12, Python unittest, Hvigor, HDC

## Global Constraints

- Ability 固定 `portrait`。
- 启动总时长 4.4-4.8 秒，页面切换 480-560ms。
- 不使用加载最外层 Ring，不新增第三方依赖。
- 设备页不请求或展示传感器；环境页只保留温湿度直接展示。
- 设置页删除通知与协议展示，但后端能力不变。
- 真实 DeviceApi、门禁密码和遥测行为必须保留。
- 当前目录不是 Git 仓库，因此以测试检查点替代提交步骤。

---

### Task 1: Lock the approved UI contract with failing tests

**Files:**
- Modify: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: ArkTS source files as UTF-8 text.
- Produces: Contract assertions for portrait, loading timing, device categories, sensor hiding and settings removal.

- [ ] **Step 1: Replace the landscape assertion and add focused contract tests**

```python
def test_shell_is_portrait_with_extended_square_loading_motion(self):
    shell = self.read("pages/ControlPanelPage.ets")
    module = (ROOT / "entry" / "src" / "main" / "module.json5").read_text(encoding="utf-8")
    loading = shell.split("loadingCore", 1)[1].split("themeCore", 1)[0]
    self.assertIn('"orientation": "portrait"', module)
    self.assertNotIn("ProgressType.Ring", loading)
    self.assertIn("this.later(4600", shell)

def test_device_page_is_categorized_and_has_no_sensor_console(self):
    source = self.read("pages/DeviceCenterPage.ets")
    self.assertNotIn("SensorApi", source)
    self.assertNotIn("environmentStrip", source)
    for label in ("门禁与出入口", "温控与空气", "照明与遮阳", "其他设备"):
        self.assertIn(label, source)

def test_settings_hides_transport_section_and_environment_hides_alarm_stats(self):
    settings = self.read("pages/SettingsPage.ets")
    history = self.read("pages/HistoryPage.ets")
    self.assertNotIn("通知与安全传输", settings)
    self.assertNotIn("protocolGrid", settings)
    self.assertIn("visibleEnvironmentStats", history)
    self.assertIn("'smoke'", history)
    self.assertIn("'heat'", history)
```

- [ ] **Step 2: Run RED verification**

Run: `python -m unittest discover -s tests -v`

Expected: failures for landscape orientation, Ring loading, SensorApi/device strip, missing categories, protocol section and missing alarm-stat filter.

### Task 2: Implement the portrait shell and motion rhythm

**Files:**
- Modify: `entry/src/main/module.json5`
- Modify: `entry/src/main/ets/theme/TacticalTheme.ets`
- Modify: `entry/src/main/ets/pages/ControlPanelPage.ets`

**Interfaces:**
- Consumes: Existing `TacticalTheme`, `activePageLabel`, page components.
- Produces: Portrait shell, 4.6-second boot sequence, 520ms page switch, compact top bar and tall bottom nav.

- [ ] **Step 1: Change orientation and motion constants**

```json5
"orientation": "portrait"
```

```ts
static readonly PAGE: number = 360;
static readonly ROUTE: number = 560;
static readonly BOOT_TOTAL: number = 4600;
```

- [ ] **Step 2: Replace boot milestones and remove the loading Ring**

Use milestones `600, 1400, 2500, 3600, 4200, 4420, 4600`. Render diamond frames, vertical/horizontal scan rails, four progress segments and the center icon. Do not add another circular progress component.

- [ ] **Step 3: Tune page switching and touch geometry**

Use switching milestones `90, 220, 380, 520, 560`. Set top bar to about 58 vp, theme visual to 32 vp inside a 48 vp Stack, bottom nav to about 92 vp and nav item to at least 64 vp.

- [ ] **Step 4: Run the focused shell contract**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_shell_is_portrait_with_extended_square_loading_motion -v`

Expected: PASS.

### Task 3: Convert device controls to a categorized portrait flow

**Files:**
- Modify: `entry/src/main/ets/pages/DeviceCenterPage.ets`
- Test: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: `DeviceApi`, `GuardApi`, `Device`, `DeviceType`, `DeviceStatus`.
- Produces: `devicesForCategory(category: number): Device[]` and `deviceCategory(title, subtitle, category)` builders.

- [ ] **Step 1: Remove sensor state and request**

Delete `SensorApi`, `Sensor`, `sensors`, `sensorRequest`, `sensorSnapshot` and `environmentStrip` from the device page.

- [ ] **Step 2: Add deterministic categories**

```ts
private deviceCategoryOf(device: Device): number {
  if (device.type === DeviceType.DOOR || device.id === 'door_01') return 0;
  if (device.type === DeviceType.AC || device.type === DeviceType.FAN ||
      device.id === 'fan_02' || device.id === 'exhaust_01') return 1;
  if (device.type === DeviceType.LIGHT || device.type === DeviceType.CURTAIN ||
      device.id === 'curtain_01') return 2;
  return 3;
}
```

- [ ] **Step 3: Render single-column sections and taller controls**

Replace the two-column fixed-height Grid with category sections and `Column` cards. Set action button minimum height to 44 vp, allow labels to remain on one line, and use vertical sub-rows for AC/door controls on narrow widths.

- [ ] **Step 4: Run device contract tests**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_device_page_is_categorized_and_has_no_sensor_console -v`

Expected: PASS while the existing real-control and door-password test also remains PASS.

### Task 4: Remove transport UI and filter alarm-only telemetry

**Files:**
- Modify: `entry/src/main/ets/pages/SettingsPage.ets`
- Modify: `entry/src/main/ets/pages/HistoryPage.ets`
- Test: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: Guard configuration, pending incidents, backend stats.
- Produces: Settings without protocol rendering and `visibleEnvironmentStats(): BackendStatItem[]`.

- [ ] **Step 1: Remove notification/protocol presentation only**

Remove `ProtocolItem`, `GuardNotificationStatus`, related state, fetches, `protocolGrid()` and all text beneath “通知与安全传输”. Keep guard, radar and feedback APIs unchanged.

- [ ] **Step 2: Add environment stat visibility filter**

```ts
private visibleEnvironmentStats(): BackendStatItem[] {
  const hidden: string[] = ['smoke', 'heat', 'kitchen_smoke', 'kitchen_heat', 'kitchen_temperature'];
  return this.stats.items.slice(2).filter((item: BackendStatItem) => hidden.indexOf(item.key) < 0);
}
```

Render that result in the environment matrix. Do not filter log records.

- [ ] **Step 3: Stack settings panels for portrait**

Replace the root two-column `Row` with a vertical `Column`, retain scroll and add bottom clearance for the taller navigation bar.

- [ ] **Step 4: Run settings/history contract tests**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_settings_hides_transport_section_and_environment_hides_alarm_stats -v`

Expected: PASS.

### Task 5: Full build, device deployment and visual verification

**Files:**
- Verify: `entry/build/default/outputs/default/entry-default-signed.hap`
- Output: device-installed HAP on D6.

**Interfaces:**
- Consumes: Signed HAP and HDC target.
- Produces: Running portrait app on D6.

- [ ] **Step 1: Run the complete frontend suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 2: Build and sign**

Run: `powershell -ExecutionPolicy Bypass -File tools/build-openharmony.ps1`

Expected: `BUILD SUCCESSFUL` and `entry-default-signed.hap` exists.

- [ ] **Step 3: Install and launch on D6**

```powershell
D:\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe -t d6290341334135353210f41a68f0bb00 install -r entry\build\default\outputs\default\entry-default-signed.hap
D:\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe -t d6290341334135353210f41a68f0bb00 shell aa start -a EntryAbility -b com.example.smarthome
```

Expected: install and Ability start both report success.

- [ ] **Step 4: Verify runtime and portrait screenshot**

Capture the active window after boot, inspect portrait geometry, bottom navigation, device categories, settings stack and absence of sensor/control overflow. Check hilog for ArkUI exceptions.

## Self-Review

- Spec coverage: every approved B requirement maps to Tasks 2-5.
- Placeholder scan: no TBD/TODO/implement-later markers.
- Type consistency: categories consume `Device`; environment filter returns `BackendStatItem[]`.
- Dependency order: tests first, shell before pages, full build and device verification last.
