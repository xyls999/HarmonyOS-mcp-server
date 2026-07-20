# Diamond Device Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace device-page plus/minus controls with an accessible in-track diamond slider that previews locally and sends one command on release.

**Architecture:** Add a focused ArkUI `TacticalDiamondSlider` presentation component backed by the native `Slider`. Keep network commands, optimistic state and rollback in `DeviceCenterPage`; the component emits preview and commit callbacks only.

**Tech Stack:** OpenHarmony ArkTS API 12, ArkUI `Slider`, Python `unittest` contract tests, Hvigor, HDC.

## Global Constraints

- Temperature is 16–30℃ with step 1; percentage controls are 0–100% with step 10.
- `Begin` and `Moving` never call a device API; `End` and `Click` commit once.
- Every slider remains at least 44vp high and uses existing theme tokens.
- The diamond stays inside the slider frame and does not reintroduce button-corner diamonds.
- Door-password behavior and device toggle behavior are unchanged.

---

### Task 1: Diamond slider component contract

**Files:**
- Create: `entry/src/main/ets/components/TacticalDiamondSlider.ets`
- Modify: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: `TacticalTheme`, ArkUI `SliderChangeMode`.
- Produces: `TacticalDiamondSlider` props `value`, `min`, `max`, `step`, `unit`, `enabled`, `isDark`; callbacks `onPreview?: (value: number) => void`, `onCommit?: (value: number) => void`.

- [ ] **Step 1: Write the failing contract test**

Add a test asserting the component uses native `Slider`, handles `Begin`, `Moving`, `End`, and `Click`, calls preview separately from commit, uses 44vp height, and renders an in-track `diamondThumb`.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_device_ranges_use_native_diamond_slider_with_release_commit`

Expected: FAIL because `TacticalDiamondSlider.ets` does not exist.

- [ ] **Step 3: Implement the minimal component**

Use one local `@State previewValue`, synchronize it from `value` when not dragging, and route modes as follows:

```ts
if (mode === SliderChangeMode.Begin || mode === SliderChangeMode.Moving) {
  this.dragging = true;
  this.onPreview?.(value);
} else {
  this.dragging = false;
  this.onCommit?.(value);
}
```

Use a transparent native block plus an overlay `diamondThumb` positioned from the normalized value, keeping all decoration inside a 44vp frame.

- [ ] **Step 4: Verify GREEN**

Run the targeted unittest and expect PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add diamond device slider`

### Task 2: Replace device range buttons

**Files:**
- Modify: `entry/src/main/ets/pages/DeviceCenterPage.ets`
- Modify: `tests/test_control_center_contract.py`

**Interfaces:**
- Consumes: `TacticalDiamondSlider` callbacks.
- Produces: local preview map keyed by device id and commit helpers for brightness, speed, curtain position and AC temperature.

- [ ] **Step 1: Write failing integration tests**

Assert that `standardControls`, `curtainControls`, and the AC temperature row instantiate `TacticalDiamondSlider`; assert the old `stepperButton` builder and calls are absent; assert commit callbacks call `DeviceApi.setBrightness`, `setFanSpeed`, `setCurtainPosition`, and `setAcTemperature`.

- [ ] **Step 2: Verify RED**

Run the two device-page contract tests and expect failure on missing slider integration.

- [ ] **Step 3: Implement minimal integration**

Add preview values without mutating server snapshots during drag. On commit, update the relevant preview and call the existing `runAction`. Preserve device offline/busy disabling and API failure toast/refresh behavior.

- [ ] **Step 4: Verify GREEN and full regression**

Run targeted tests, then `python -m unittest discover -s tests -p 'test_*.py'`; expect every test to pass.

- [ ] **Step 5: Commit**

Commit message: `feat: replace device steppers with sliders`

### Task 3: Build, deploy, and visually verify

**Files:**
- Modify: `C:\Users\xyls\Desktop\明日家居_D6_最终产品前后端对齐与验收文档_20260718.md`
- Copy deliverable: `C:\Users\xyls\Documents\Codex\2026-07-17\new-chat\outputs\明日家居_D6_最终产品前后端对齐与验收文档_20260718.md`

**Interfaces:**
- Consumes: signed Release HAP from `tools/build-openharmony.ps1`.
- Produces: installed bundle on D6 `d6290341334135353210f41a68f0bb00` and screenshots.

- [ ] **Step 1: Build and Release-sign**

Run: `powershell -ExecutionPolicy Bypass -File tools/build-openharmony.ps1`

Expected: `BUILD SUCCESSFUL`, `profile type is: release`, and `Sign Hap success!`.

- [ ] **Step 2: Install only on D6**

Send and install `entry-default-signed.hap` with HDC target `d6290341334135353210f41a68f0bb00`; expect `install bundle successfully`.

- [ ] **Step 3: True-device interaction check**

Open the device page, inspect top and bottom sections, drag one safe control, verify its displayed value follows the finger and one result toast appears after release. Restore the original device value after the test.

- [ ] **Step 4: Update documentation and evidence**

Append slider ranges, commit semantics, test totals, build/install evidence, and screenshot paths to the alignment document and copy it to outputs.

- [ ] **Step 5: Final repository check**

Run `git status --short` and ensure only intentional documentation changes remain or commit them with `docs: record diamond slider verification`.
