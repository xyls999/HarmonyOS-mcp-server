# Tactical Home Control Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D6 上的明日家居主控升级为稳定、可解释、无误报噪声的明日方舟式竖屏战术控制台。

**Architecture:** 前端继续使用原生 ArkUI 和四栏外壳，新增小型可复用战术开关与动效核心组件。D6 后端源文件纳入同一 Git 仓库，AdaptiveGuard 负责厨房报警生命周期和持久化设置，Gateway 负责设备清单、会话计划与 HTTP 接口，前后端通过现有 REST 接口保持兼容。

**Tech Stack:** ArkTS, ArkUI, OpenHarmony API 12, Python 3.14, sqlite3, unittest, Hvigor, HDC

## Global Constraints

- 固定竖屏，不修改下位机 IP、端口、协议或真实设备 ID。
- 保留明日家居 Logo、现有明暗配色关系、四栏导航和门禁密码要求。
- 不新增第三方前端依赖，不使用背景网格、紫色霓虹、大型圆环或小于 14vp 的可见正文。
- 触控区至少 44vp；动画只改变 transform、rotation、scale 和 opacity。
- 联动关闭时厨房报警完全静默，但原始传感器日志继续持久化。
- `fan_01` 和 `exhaust_01` 永久过滤，真实 `fan_02` 保留，自定义设备接口继续可用。
- 每个行为变更先写失败测试，再实现，再运行完整测试并提交。
- 所有部署命令必须显式指定 D6 `d6290341334135353210f41a68f0bb00`。

---

### Task 1: Version the authoritative D6 backend

**Files:**
- Create: `backend/d6/gateway_v6.py`
- Create: `backend/d6/adaptive_guard.py`
- Create: `backend/d6/proactive_intelligence.py`
- Modify: `tests/test_d6_intelligence_contract.py`

**Interfaces:**
- Consumes: 当前验证通过的 `work/gateway_v6.py`、`work/adaptive_guard_d6.py`、`work/proactive_intelligence.py`。
- Produces: Git 可追踪的 `backend/d6` 后端源文件和相对路径测试入口。

- [ ] **Step 1: Import the current backend without changing behavior**

```powershell
New-Item -ItemType Directory -Force backend\d6
Copy-Item C:\Users\xyls\Documents\Codex\2026-07-17\new-chat\work\gateway_v6.py backend\d6\gateway_v6.py
Copy-Item C:\Users\xyls\Documents\Codex\2026-07-17\new-chat\work\adaptive_guard_d6.py backend\d6\adaptive_guard.py
Copy-Item C:\Users\xyls\Documents\Codex\2026-07-17\new-chat\work\proactive_intelligence.py backend\d6\proactive_intelligence.py
```

- [ ] **Step 2: Point backend contract tests at repository files**

```python
ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend" / "d6"
BACKEND = BACKEND_DIR / "proactive_intelligence.py"
GATEWAY = BACKEND_DIR / "gateway_v6.py"
GUARD = BACKEND_DIR / "adaptive_guard.py"
```

Replace every absolute `work/gateway_v6.py` lookup with `GATEWAY`.

- [ ] **Step 3: Run the unchanged baseline suite**

Run: `python -m unittest discover -s tests -v`

Expected: 54 tests PASS.

- [ ] **Step 4: Commit the backend baseline**

```powershell
git add backend/d6 tests/test_d6_intelligence_contract.py
git commit -m "chore: version authoritative D6 backend sources"
```

---

### Task 2: Make kitchen alarms silent when disabled and debounce noisy sensors

**Files:**
- Create: `tests/test_adaptive_guard_state_machine.py`
- Modify: `backend/d6/adaptive_guard.py`

**Interfaces:**
- Consumes: `AdaptiveGuard.process_snapshot(snapshot: dict) -> list[dict]` and `update_config(updates: dict) -> dict`.
- Produces: one lifecycle per confirmed alarm, persistent `planConfirmation`, and a hard silence gate.

- [ ] **Step 1: Write failing behavioral tests**

```python
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "d6" / "adaptive_guard.py"
SPEC = importlib.util.spec_from_file_location("adaptive_guard_under_test", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeClock:
    def __init__(self, value: float = 1000.0): self.value = value
    def __call__(self) -> float: return self.value
    def advance(self, seconds: float) -> None: self.value += seconds


def kitchen_snapshot(alert: bool) -> dict:
    return {"sensors": [
        {"id": "smoke_01", "type": "smoke", "room": "厨房", "value": int(alert),
         "isAlert": alert, "online": True},
        {"id": "heat_01", "type": "heat", "room": "厨房", "value": 1630,
         "isAlert": False, "online": True},
    ]}


class AdaptiveGuardStateMachineTests(unittest.TestCase):
    def make_guard(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        clock = FakeClock()
        actions, speech, notices, context = [], [], [], []
        guard = MODULE.AdaptiveGuard(
            pathlib.Path(directory.name) / "home.db",
            executor=lambda action: actions.append(action) or {"success": True, "state_changed": True},
            speaker=speech.append,
            notifier=lambda *args, **kwargs: notices.append((args, kwargs)),
            context_recorder=lambda *args, **kwargs: context.append((args, kwargs)),
            clock=clock,
        )
        guard._started_at = clock() - 30
        return guard, clock, actions, speech, notices, context

    def test_disabled_guard_is_completely_silent_for_alarm_and_recovery(self):
        guard, clock, actions, speech, notices, context = self.make_guard()
        guard.update_config({"enabled": False})
        speech.clear()
        for alert in (True, True, True, False, False, False, False, False):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(kitchen_snapshot(alert)), [])
        self.assertEqual(actions, [])
        self.assertEqual(speech, [])
        self.assertEqual(notices, [])
        self.assertEqual(context, [])
        self.assertEqual(guard.list_incidents(limit=10), [])

    def test_alarm_requires_three_samples_and_recovery_requires_five(self):
        guard, clock, actions, speech, notices, context = self.make_guard()
        for _ in range(2):
            clock.advance(1)
            self.assertEqual(guard.process_snapshot(kitchen_snapshot(True)), [])
        clock.advance(1)
        self.assertEqual(len(guard.process_snapshot(kitchen_snapshot(True))), 1)
        self.assertEqual(len(speech), 1)
        for _ in range(4):
            clock.advance(1)
            guard.process_snapshot(kitchen_snapshot(False))
        self.assertEqual(len(actions), 2)
        clock.advance(1)
        guard.process_snapshot(kitchen_snapshot(False))
        self.assertEqual(len(actions), 4)
        self.assertEqual(len(speech), 2)

    def test_plan_confirmation_persists_across_restart(self):
        guard, _, _, _, _, _ = self.make_guard()
        guard.update_config({"planConfirmation": {"enabled": False}})
        restored = MODULE.AdaptiveGuard(guard.db_path)
        self.assertFalse(restored.get_config()["planConfirmation"]["enabled"])
```

- [ ] **Step 2: Run RED verification**

Run: `python -m unittest tests.test_adaptive_guard_state_machine -v`

Expected: failures because `planConfirmation`, silence gating and sample thresholds do not exist.

- [ ] **Step 3: Implement the deterministic state machine**

Add to `DEFAULT_CONFIG`:

```python
"planConfirmation": {"enabled": True},
"startupGraceSeconds": 20,
"kitchenAlarm": {
    "enabled": True, "buzzer": True, "exhaust": True, "clearOnRecovery": True,
    "confirmSamples": 3, "recoverySamples": 5,
},
```

Initialize:

```python
self._started_at = self.clock()
self._kitchen_alarm_streak = 0
self._kitchen_clear_streak = 0
self._kitchen_confirmed = False
```

At the start of `_process_snapshot_locked`:

```python
if not bool(self.config.get("enabled", True)):
    self._active_signatures.clear()
    self._kitchen_alarm_streak = 0
    self._kitchen_clear_streak = 0
    self._kitchen_confirmed = False
    return []
```

Replace immediate kitchen activation with a helper that returns confirmed state:

```python
def _confirmed_kitchen_alarm(self, raw_alert: bool) -> bool:
    if self.clock() - self._started_at < float(self.config.get("startupGraceSeconds", 20)):
        return False
    config = self.config["kitchenAlarm"]
    if raw_alert:
        self._kitchen_alarm_streak += 1
        self._kitchen_clear_streak = 0
        if self._kitchen_alarm_streak >= int(config.get("confirmSamples", 3)):
            self._kitchen_confirmed = True
    else:
        self._kitchen_clear_streak += 1
        self._kitchen_alarm_streak = 0
        if self._kitchen_clear_streak >= int(config.get("recoverySamples", 5)):
            self._kitchen_confirmed = False
    return self._kitchen_confirmed
```

Use the helper once per complete snapshot. Query latest incident regardless of status in `_recent_signature` so a resolved incident still honors cooldown.

- [ ] **Step 4: Run state-machine and full tests**

Run: `python -m unittest tests.test_adaptive_guard_state_machine -v`

Expected: 3 tests PASS.

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the guard fix**

```powershell
git add backend/d6/adaptive_guard.py tests/test_adaptive_guard_state_machine.py
git commit -m "fix: silence and debounce kitchen guard alarms"
```

---

### Task 3: Remove false devices and harden plan execution

**Files:**
- Create: `tests/test_gateway_safety_contract.py`
- Modify: `backend/d6/gateway_v6.py`
- Modify: `entry/src/main/ets/mock/mockData.ets`
- Modify: `entry/src/main/ets/pages/detail/DeviceDetailPage.ets`

**Interfaces:**
- Consumes: `is_explicit_execution_request(text: str) -> bool`, `/api/devices`, pending plan storage and chat request body.
- Produces: truthful device inventory and session-scoped plan confirmation.

- [ ] **Step 1: Write failing safety tests**

```python
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "backend" / "d6" / "gateway_v6.py"


def load_function(name: str):
    tree = ast.parse(GATEWAY.read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {}
    exec(compile(module, str(GATEWAY), "exec"), namespace)
    return namespace[name]


class GatewaySafetyContractTests(unittest.TestCase):
    def test_only_explicit_affirmative_device_commands_execute_directly(self):
        check = load_function("is_explicit_execution_request")
        self.assertTrue(check("打开客厅主灯"))
        self.assertTrue(check("把客厅空调调到26度"))
        self.assertFalse(check("不要打开空调"))
        self.assertFalse(check("先别执行"))
        self.assertFalse(check("我觉得有点暗"))
        self.assertFalse(check("马上让家里舒服一点"))

    def test_removed_mock_devices_are_filtered_but_real_fan_remains(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("REMOVED_LEGACY_DEVICE_IDS", source)
        self.assertIn('"fan_01"', source)
        self.assertIn('"exhaust_01"', source)
        self.assertIn('"fan_02"', source)

    def test_pending_plans_are_scoped_and_expire(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("sessionId", source)
        self.assertIn("expiresAt", source)
        self.assertIn("planNonce", source)
        self.assertNotIn('_PENDING_INTENT_PLANS["u001"]', source)
```

- [ ] **Step 2: Run RED verification**

Run: `python -m unittest tests.test_gateway_safety_contract -v`

Expected: all three tests FAIL against keyword-only execution and global plan storage.

- [ ] **Step 3: Implement affirmative command validation**

Use explicit negative and vague guards before accepting a command:

```python
_NEGATED_EXECUTION = re.compile(r"(不要|别|先别|暂不|取消|不需要|不要执行|别执行)")
_EXPLICIT_DEVICE = re.compile(r"(客厅主灯|厨房灯|卧室灯|卫生间灯|空调|窗帘|换气扇|门禁|大门)")
_EXPLICIT_ACTION = re.compile(r"(打开|开启|关闭|关掉|调到|设为|升高|降低|开门|关门)")

def is_explicit_execution_request(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized or _NEGATED_EXECUTION.search(normalized):
        return False
    return bool(_EXPLICIT_DEVICE.search(normalized) and _EXPLICIT_ACTION.search(normalized))
```

- [ ] **Step 4: Filter stale mock devices without blocking custom injection**

```python
REMOVED_LEGACY_DEVICE_IDS = {"fan_01", "exhaust_01"}

def _visible_devices(devices):
    return [item for item in devices if str(item.get("id", "")) not in REMOVED_LEGACY_DEVICE_IDS]
```

Apply this only to final API/context output after real and custom devices merge. Remove `fan_01` and `exhaust_01` from active frontend mock data and use `light_01` as the detail-page fallback ID.

- [ ] **Step 5: Scope pending plans**

Use `(userId, sessionId)` as the key, store `expiresAt = time.time() + 300`, generate `planNonce = secrets.token_urlsafe(12)`, and confirm only when the request carries the same scope and nonce. Save only the commands rendered in the plan.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_gateway_safety_contract -v`

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

```powershell
git add backend/d6/gateway_v6.py entry/src/main/ets/mock/mockData.ets entry/src/main/ets/pages/detail/DeviceDetailPage.ets tests/test_gateway_safety_contract.py
git commit -m "fix: harden plans and remove stale mock devices"
```

---

### Task 4: Make every settings switch visibly and persistently reactive

**Files:**
- Create: `entry/src/main/ets/components/TacticalToggle.ets`
- Modify: `entry/src/main/ets/pages/SettingsPage.ets`
- Modify: `entry/src/main/ets/api/guardApi.ets`
- Modify: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: `@Link enabled`, `GuardApi.updateConfig(...)`, `GuardApi.getStatus()`.
- Produces: five independently reactive controls with optimistic update and failure rollback.

- [ ] **Step 1: Replace the old source-token test with a failing reactive-component contract**

```python
def test_settings_switches_use_linked_reactive_components(self):
    settings = self.read("pages/SettingsPage.ets")
    toggle = self.read("components/TacticalToggle.ets")
    self.assertIn("@Link enabled: boolean", toggle)
    self.assertIn("onToggle?: (enabled: boolean) => void", toggle)
    for state in ("$linkageEnabled", "$activeAiEnabled", "$feedbackAutomationEnabled",
                  "$planConfirmationEnabled", "$radarEnabled"):
        self.assertIn(state, settings)
    self.assertNotIn("settingEnabled(key", settings)
    self.assertNotIn("fontSize(11)", settings)
    self.assertNotIn("fontSize(9)", settings)
```

- [ ] **Step 2: Run RED verification**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_settings_switches_use_linked_reactive_components -v`

Expected: FAIL because `TacticalToggle` does not exist.

- [ ] **Step 3: Add the linked toggle**

```ts
@Component
export struct TacticalToggle {
  @Link enabled: boolean;
  @Prop disabled: boolean = false;
  @Prop isDark: boolean = true;
  onToggle?: (enabled: boolean) => void;

  build() {
    Stack({ alignContent: Alignment.Center }) {
      Column().width(52).height(24)
        .backgroundColor(this.enabled ? TacticalTheme.accent(this.isDark) : TacticalTheme.panel(this.isDark))
        .border({ width: 1, color: this.enabled ? TacticalTheme.accent(this.isDark) : TacticalTheme.border(this.isDark) })
      Column().width(18).height(18)
        .backgroundColor(this.enabled ? TacticalTheme.inverse(this.isDark) : TacticalTheme.textMuted(this.isDark))
        .translate({ x: this.enabled ? 14 : -14 })
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    }
    .width(60).height(44)
    .opacity(this.disabled ? 0.45 : 1)
    .onClick(() => {
      if (this.disabled) return;
      const next = !this.enabled;
      this.enabled = next;
      if (this.onToggle) this.onToggle(next);
    })
  }
}
```

- [ ] **Step 4: Bind rows directly and protect refreshes**

Replace key-based builder state lookup with explicit `TacticalToggle({ enabled: $linkageEnabled, ... })` instances. Track `savingKey`; `loadData()` must not assign switch states while a key is saving. On request failure, roll back only the submitted state.

- [ ] **Step 5: Run focused tests, build and commit**

Run: `python -m unittest tests.test_control_center_contract -v`

Run: `powershell -ExecutionPolicy Bypass -File tools/build-openharmony.ps1`

Expected: tests PASS and `BUILD SUCCESSFUL`.

```powershell
git add entry/src/main/ets/components/TacticalToggle.ets entry/src/main/ets/pages/SettingsPage.ets entry/src/main/ets/api/guardApi.ets tests/test_control_center_contract.py
git commit -m "fix: make D6 settings switches truly reactive"
```

---

### Task 5: Replace the frozen progress bar with an interruptible tactical transition

**Files:**
- Create: `entry/src/main/ets/components/TacticalMotionCore.ets`
- Modify: `entry/src/main/ets/pages/ControlPanelPage.ets`
- Modify: `entry/src/main/ets/theme/TacticalTheme.ets`
- Modify: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: reactive `@Prop progress`, `outerAngle`, `innerAngle`, `isDark`, `title`.
- Produces: visible 0-100 motion rail, transition reset, and theme phrases with one TTS call.

- [ ] **Step 1: Write the failing motion contract**

```python
def test_transition_progress_is_component_reactive_and_theme_has_phrases(self):
    shell = self.read("pages/ControlPanelPage.ets")
    core = self.read("components/TacticalMotionCore.ets")
    self.assertIn("@Prop progress: number", core)
    self.assertIn("motionRail", core)
    self.assertNotIn("Progress({ value: progress", core)
    self.assertIn("resetTransition", shell)
    self.assertIn("天光接管，居所进入明昼模式", shell)
    self.assertIn("夜幕落下，系统转入低光守护", shell)
    self.assertIn("ChatApi.speak(themePhrase)", shell)
```

- [ ] **Step 2: Run RED verification**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_transition_progress_is_component_reactive_and_theme_has_phrases -v`

Expected: FAIL because the component and reset function do not exist.

- [ ] **Step 3: Implement the transform-only progress rail**

`TacticalMotionCore.motionRail()` renders a fixed 184vp hairline, a full-length fill scaled from left with `scale({ x: progress / 100, centerX: 0 })`, and a 10vp square translated between -87vp and +87vp. The component receives progress through `@Prop`, so ArkUI observes parent state changes.

- [ ] **Step 4: Derive all transition phases from one duration**

```ts
private transitionAt(ratio: number): number {
  const duration = this.transitionKind === 1 ? TacticalMotion.THEME_ROUTE : TacticalMotion.ROUTE;
  return Math.round(duration * ratio);
}

private resetTransition(): void {
  this.transitionGeneration++;
  this.clearTimers();
  this.transitionVisible = false;
  this.transitionClosing = false;
  this.pageSwitching = false;
  this.themeSwitching = false;
  this.transitionProgress = 0;
}
```

Use ratios 0.08 start, 0.48 page/theme swap, 0.88 reach 100, 0.94 closing, 1.0 reset. Each timer captures `transitionGeneration` and ignores stale callbacks.

- [ ] **Step 5: Add theme phrases and lifecycle cleanup**

Call `ChatApi.speak(themePhrase)` once when a user starts theme switching. Display the same line in the transition overlay. Invoke `resetTransition()` from `aboutToDisappear()`.

- [ ] **Step 6: Run tests, build and commit**

Run: `python -m unittest tests.test_control_center_contract -v`

Run: `powershell -ExecutionPolicy Bypass -File tools/build-openharmony.ps1`

Expected: tests PASS and build succeeds.

```powershell
git add entry/src/main/ets/components/TacticalMotionCore.ets entry/src/main/ets/pages/ControlPanelPage.ets entry/src/main/ets/theme/TacticalTheme.ets tests/test_control_center_contract.py
git commit -m "fix: make tactical transitions reactive and interruptible"
```

---

### Task 6: Recompose all four surfaces into a clean Arknights-style control system

**Files:**
- Modify: `entry/src/main/ets/theme/TacticalTheme.ets`
- Modify: `entry/src/main/ets/pages/ControlPanelPage.ets`
- Modify: `entry/src/main/ets/pages/DeviceCenterPage.ets`
- Modify: `entry/src/main/ets/pages/HistoryPage.ets`
- Modify: `entry/src/main/ets/pages/SettingsPage.ets`
- Modify: `entry/src/main/ets/components/HarmonChatBubble.ets`
- Modify: `entry/src/main/ets/components/ChatChartPanel.ets`
- Modify: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: existing APIs and the new `TacticalToggle` and `TacticalMotionCore`.
- Produces: consistent type scale, compact real-device controls, truthful charts, conversation-first assistant and clean settings.

- [ ] **Step 1: Add failing visual-source contracts**

```python
def test_tactical_ui_has_clean_type_and_truthful_device_inventory(self):
    sources = "\n".join(path.read_text(encoding="utf-8") for path in ETS.rglob("*.ets"))
    device = self.read("pages/DeviceCenterPage.ets")
    settings = self.read("pages/SettingsPage.ets")
    shell = self.read("pages/ControlPanelPage.ets")
    self.assertNotRegex(sources, r"fontSize\((?:[1-9]|1[0-3])\)")
    self.assertNotIn("fan_01", sources)
    self.assertNotIn("exhaust_01", sources)
    self.assertIn("fan_02", device)
    self.assertNotIn("feedbackPanel()", settings.split("build()", 1)[1])
    self.assertNotIn("通信与安全传送", settings)
    self.assertIn("明日", shell)
    self.assertIn("家居", shell)

def test_charts_never_fabricate_no_data_values(self):
    shell = self.read("pages/ControlPanelPage.ets")
    chart = self.read("components/ChatChartPanel.ets")
    self.assertNotIn("[1]", shell.split("feedChartData", 1)[1].split("submitAssistantFeedback", 1)[0])
    self.assertIn("return undefined", shell.split("feedChartData", 1)[1].split("submitAssistantFeedback", 1)[0])
    self.assertIn("forEach", chart)
```

- [ ] **Step 2: Run RED verification**

Run: `python -m unittest tests.test_control_center_contract -v`

Expected: failures for existing 9-13vp text and stale device references.

- [ ] **Step 3: Apply the shared design tokens**

Add semantic typography constants `LABEL=14`, `BODY=16`, `TITLE=20`, `PAGE_TITLE=28`, touch target `44`, and the existing 0-4vp radius system to `TacticalTheme`. Replace raw small font sizes across active four-surface files.

- [ ] **Step 4: Recompose the shell and assistant**

Keep the Logo and four navigation labels. Use a single strong page title, no subtitle microcopy. Conversation bubbles use a left accent blade and a flat panel. Assistant events show only meaningful analysis, evidence, concrete action and result; ordinary operations remain context-only. Rating controls appear only for feedback-enabled successful adjustments and disappear after submission.

- [ ] **Step 5: Recompose device and settings surfaces**

Device categories use content-height single-column sections. Each device row has a compact primary state control with at least 44vp hit area; AC and curtain parameters expand below the row. Remove all stale mock IDs. Settings use the linked toggles, remove the dormant rating panel, keep clear and exit actions visually separated.

- [ ] **Step 6: Recompose data and charts**

Keep logs incrementally refreshed and preserve scroll position. Use actual totals from the backend. Fix the line chart to redraw every point after area fill, and render an empty state instead of synthetic values when no series exists.

- [ ] **Step 7: Run full tests, build and commit**

Run: `python -m unittest discover -s tests -v`

Run: `powershell -ExecutionPolicy Bypass -File tools/build-openharmony.ps1`

Expected: all tests PASS and signed HAP builds.

```powershell
git add entry/src/main/ets tests/test_control_center_contract.py
git commit -m "feat: overhaul four-surface tactical home UI"
```

---

### Task 7: Deploy backend and HAP to D6 and prove the complete behavior

**Files:**
- Verify: `backend/d6/*.py`
- Verify: `entry/build/default/outputs/default/entry-default-signed.hap`
- Create runtime evidence only in ignored `tests/*.png` or workspace `work/`.

**Interfaces:**
- Consumes: tested backend sources and signed HAP.
- Produces: D6 runtime with persistent settings, silent disabled guard and verified UI motion.

- [ ] **Step 1: Create a device-side rollback snapshot**

```powershell
$hdc='D:\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe'
$target='d6290341334135353210f41a68f0bb00'
& $hdc -t $target shell "mkdir -p /data/A9/backups/tactical_20260718 && cp /data/A9/smart_home/gateway_v6.py /data/A9/smart_home/adaptive_guard.py /data/A9/smart_home/proactive_intelligence.py /data/A9/backups/tactical_20260718/"
```

- [ ] **Step 2: Send backend files and restart only D6**

```powershell
& $hdc -t $target file send backend/d6/gateway_v6.py /data/A9/smart_home/gateway_v6.py
& $hdc -t $target file send backend/d6/adaptive_guard.py /data/A9/smart_home/adaptive_guard.py
& $hdc -t $target file send backend/d6/proactive_intelligence.py /data/A9/smart_home/proactive_intelligence.py
& $hdc -t $target shell "pkill -f gateway_v6.py || true; sh /data/A9/run_v6.sh"
```

Expected: `/api/health` responds successfully after restart.

- [ ] **Step 3: Install and launch the latest HAP**

```powershell
& $hdc -t $target install -r entry/build/default/outputs/default/entry-default-signed.hap
& $hdc -t $target shell aa start -a EntryAbility -b com.smarthome.openharmony
```

Expected: install and Ability start succeed.

- [ ] **Step 4: Verify settings persistence and inventory**

Toggle each setting through the UI, re-enter the page, restart the backend and confirm API/UI parity. Verify `/api/devices` excludes `fan_01` and `exhaust_01` and includes `fan_02`.

- [ ] **Step 5: Verify disabled kitchen silence with an isolated test database**

Run `tests/test_adaptive_guard_state_machine.py` on D6 or against the deployed module with a temporary DB. Do not inject a physical alarm or switch real actuators during this proof. Confirm zero TTS, notifier, action and incident side effects.

- [ ] **Step 6: Capture motion and UI evidence**

Capture transition frames near 0.3s, 0.8s, 1.4s and completion. Confirm progress increases, reaches 100, theme phrase appears, no overlay remains, no content overflows, no small text appears, and all controls respond.

- [ ] **Step 7: Inspect runtime logs and run final tests**

Run: `python -m unittest discover -s tests -v`

Inspect D6 process list, `/api/health`, guard status, hilog and gateway log. Expected: no ArkUI exception, no guard thread crash and no duplicate kitchen incidents.

- [ ] **Step 8: Commit deployment evidence notes**

```powershell
git add docs
git commit -m "docs: record D6 tactical overhaul verification"
```

## Self-Review

- Spec coverage: Tasks 2-3 cover kitchen silence, debounce, plan safety and truthful inventory; Tasks 4-6 cover reactive settings, motion, all four surfaces and theme phrases; Task 7 covers D6 deployment and real verification.
- Placeholder scan: every step contains concrete files, commands, behavior and expected results; no deferred implementation marker exists.
- Type consistency: backend files live under `backend/d6`; tests reference those relative paths; `TacticalToggle` uses `@Link`; `TacticalMotionCore` uses reactive `@Prop` state.
- Safety: physical kitchen alarm is never injected during verification; D6 target is explicit in every HDC command; device-side rollback copies are created before overwrite.
