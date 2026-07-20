# 100-Rule Smart Adjustment Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `test-driven-development` and `verification-before-completion` for every task. Steps use checkbox syntax and must be completed in order.

**Goal:** 在 D6 上实现 100 条可审计的智能联动规则，直接执行真实设备动作，并以紧急/普通双队列弹窗和中文播报反馈结果。

**Architecture:** 新增 `backend/d6/automation/` 模块，将规则目录、快照、状态机、执行回执、弹窗 outbox 和 AI 候选规则分离；`gateway_v6.py` 只负责生命周期、API 和现有硬件适配。前端只消费弹窗/执行结果，不复制规则判断。

**Tech Stack:** Python 3.14 标准库、SQLite WAL、现有 `execute_device_commands`、OpenHarmony ArkTS、Hvigor、D6 HDC。

## Global Constraints

- 规则总数严格为 100：A001–A020 默认核心，B021–B100 自动解锁。
- 所有规则统一校验输入新鲜度、设备能力、在线状态、手动保护和冲突组。
- AI 动作直接执行；弹窗只表示执行后告知/已读，不是审批。
- 自动开门、自动尝试门禁密码和 AI 改写安全权限永久禁止。
- 紧急警报独立队列，普通一条规则一张弹窗；无触发不弹。
- 光敏开关必播，亮度变化至少 20% 且连续稳定 3 次才播，同类 600 秒去重。
- 新闻、科技、股市正文不能作为设备动作输入；天气只用结构化中文字段。
- 每个任务必须先写失败测试并看到 RED，再写最小实现并看到 GREEN。
- 每次提交前运行 `python -m unittest discover -s tests`、`git diff --check` 和敏感信息扫描。

---

## Task 1: 规则目录与 schema 校验

**Files:**
- Create: `backend/d6/automation/__init__.py`
- Create: `backend/d6/automation/rule_schema.py`
- Create: `backend/d6/automation/rule_catalog.json`
- Test: `tests/test_automation_catalog.py`

**Interfaces:**
- `load_catalog(path: Path | str) -> list[dict]`
- `validate_rule(rule: dict, devices: set[str], sensors: set[str]) -> list[str]`
- `validate_catalog(rules: list[dict]) -> None`
- `rule_requires_ack_popup(rule: dict) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
def test_catalog_has_exactly_100_unique_rules():
    rules = load_catalog(CATALOG)
    assert len(rules) == 100
    assert len({rule["id"] for rule in rules}) == 100

def test_catalog_has_twenty_core_and_eighty_unlockable_rules():
    rules = load_catalog(CATALOG)
    assert sum(rule["tier"] == "core" for rule in rules) == 20
    assert sum(rule["tier"] == "unlockable" for rule in rules) == 80

def test_catalog_rejects_any_automatic_door_action():
    bad = {"id": "X", "actions": [{"deviceId": "door_01", "action": "open"}]}
    assert any("door" in error for error in validate_rule(bad, {"door_01"}, set()))
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_automation_catalog -v`

Expected: FAIL because the automation package and catalog do not exist.

- [ ] **Step 3: Implement the catalog and validator**

`validate_rule` must reject missing `id`, duplicate IDs, invalid tiers, unknown devices/sensors, absent freshness/cooldown fields, unbounded thresholds, and any `door_01` action other than `query`/`record`.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_automation_catalog -v`

Expected: all catalog tests PASS and `validate_catalog(load_catalog(...))` returns without errors.

- [ ] **Step 5: Commit**

```powershell
git add backend/d6/automation tests/test_automation_catalog.py
git commit -m "feat: add validated 100-rule automation catalog"
```

## Task 2: Atomic snapshot, persistent rule state and manual protection

**Files:**
- Create: `backend/d6/automation/snapshot_builder.py`
- Create: `backend/d6/automation/rule_state_store.py`
- Test: `tests/test_automation_snapshot_and_state.py`

**Interfaces:**
- `build_snapshot(device_status, sensor_status, weather, now, history) -> dict`
- `is_fresh(value: dict, now: float, ttl: int) -> bool`
- `RuleStateStore.record_sample(rule_id, snapshot_version, matched) -> dict`
- `RuleStateStore.start_cooldown(rule_id, until_ts) -> None`
- `RuleStateStore.set_manual_override(device_id, until_ts, source) -> None`
- `RuleStateStore.is_protected(device_id, now) -> bool`

- [ ] **Step 1: Write failing tests**

```python
def test_snapshot_has_one_timestamp_for_all_inputs():
    snapshot = build_snapshot({"light_01": {"isOn": True}}, {"humid_01": {"value": 78}}, {"rainProbability": 80}, 1000, {})
    assert snapshot["version"] == 1000
    assert snapshot["devices"]["light_01"]["isOn"] is True

def test_stale_weather_is_unavailable_not_zero():
    assert not is_fresh({"value": 80, "ts": 1}, 1000, 60)

def test_manual_override_survives_restart():
    store = RuleStateStore(path)
    store.set_manual_override("curtain_01", 2000, "app")
    assert RuleStateStore(path).is_protected("curtain_01", 1500)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_automation_snapshot_and_state -v`

Expected: FAIL with missing modules/classes.

- [ ] **Step 3: Implement SQLite WAL state store**

Use one immutable snapshot object per evaluation. Missing/stale values are represented as `available=False`; never substitute zero. Store sample streaks, cooldowns, unlock state, manual overrides and last snapshot version transactionally.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_automation_snapshot_and_state -v`

Expected: PASS, including a fresh process reopening the same database.

- [ ] **Step 5: Commit**

```powershell
git add backend/d6/automation/snapshot_builder.py backend/d6/automation/rule_state_store.py tests/test_automation_snapshot_and_state.py
git commit -m "feat: add atomic automation snapshots and persistent state"
```

## Task 3: Deterministic evaluator, conflict resolution and action receipts

**Files:**
- Create: `backend/d6/automation/smart_adjustment_engine.py`
- Test: `tests/test_smart_adjustment_engine.py`

**Interfaces:**
- `evaluate_rules(rules, snapshot, state_store) -> EvaluationPlan`
- `resolve_conflicts(candidates) -> list[dict]`
- `execute_plan(plan, executor, state_store, now) -> ExecutionBatch`
- `EvaluationPlan` fields: `snapshotVersion`, `ruleIds`, `actions`, `skipped`, `conflicts`.
- `ExecutionBatch` fields: `success`, `ruleId`, `changedCount`, `results`, `receiptId`.

- [ ] **Step 1: Write failing tests**

```python
def test_humidity_rule_requires_three_samples_and_hysteresis():
    engine = make_engine()
    assert engine.evaluate("A001", humidity=78).actions == []
    assert engine.evaluate("A001", humidity=78).actions == []
    assert engine.evaluate("A001", humidity=78).actions[0]["deviceId"] == "ac_01"
    assert engine.evaluate("A001", humidity=65).release is True

def test_conflict_winner_is_stable_and_door_open_is_rejected():
    plan = resolve_conflicts([cool_action(priority=70), heat_action(priority=60)])
    assert plan[0]["action"] == "cool"
    with pytest.raises(ValueError):
        resolve_conflicts([{"deviceId": "door_01", "action": "open"}])

def test_partial_hardware_failure_returns_each_device_result():
    result = execute_plan(plan, executor_with_one_failure, store, now=1000)
    assert result.changedCount == 1
    assert result.results[1]["success"] is False
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_smart_adjustment_engine -v`

Expected: FAIL because the evaluator and receipt types do not exist.

- [ ] **Step 3: Implement evaluator**

Use fixed precedence `priority → specificity → rule ID`, per-device conflict groups, persisted streak/cooldown, manual override checks, and existing `execute_device_commands`. Record before state, command result, after state and `changed` explicitly. Never count a no-op as a change.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_smart_adjustment_engine -v`

Expected: PASS with deterministic results under reordered input and duplicate evaluations.

- [ ] **Step 5: Commit**

```powershell
git add backend/d6/automation/smart_adjustment_engine.py tests/test_smart_adjustment_engine.py
git commit -m "feat: evaluate smart adjustments with safe conflict resolution"
```

## Task 4: Dual popup outbox and Chinese speech policy

**Files:**
- Create: `backend/d6/automation/popup_outbox.py`
- Modify: `backend/d6/gateway_v6.py`
- Test: `tests/test_automation_popup_outbox.py`

**Interfaces:**
- `enqueue_alarm(event, now) -> Popup`
- `enqueue_rule_result(receipt, now) -> Popup | None`
- `list_pending(priority=None, limit=20) -> list[Popup]`
- `acknowledge(popup_id) -> bool`
- `speech_text(receipt) -> str`

- [ ] **Step 1: Write failing tests**

```python
def test_alarm_preempts_routine_popup():
    outbox.enqueue_rule_result(routine_receipt, now=100)
    outbox.enqueue_alarm(smoke_alarm, now=101)
    assert outbox.list_pending(limit=1)[0]["priority"] == "critical"

def test_one_rule_one_popup_lists_all_devices_and_noop_has_none():
    popup = outbox.enqueue_rule_result(two_device_receipt, now=100)
    assert len(popup["deviceResults"]) == 2
    assert outbox.enqueue_rule_result(noop_receipt, now=101) is None

def test_light_speech_requires_delta_and_three_stable_samples():
    assert speech_policy.should_speak("light_01", "on", 100, stable_samples=3)
    assert not speech_policy.should_speak("light_01", "brightness", 10, stable_samples=3)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_automation_popup_outbox -v`

Expected: FAIL because the outbox and speech policy do not exist.

- [ ] **Step 3: Implement priority queues and crash-safe acknowledgement**

Use SQLite outbox rows and a stable incident key. Critical alarms bypass routine cooldown. Routine receipts produce one concise Chinese popup per rule if at least one action was attempted; no-op/no-trigger produces none. Speech deduplication does not suppress popup persistence.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_automation_popup_outbox -v`

Expected: PASS, including restart recovery and duplicate event merging.

- [ ] **Step 5: Commit**

```powershell
git add backend/d6/automation/popup_outbox.py backend/d6/gateway_v6.py tests/test_automation_popup_outbox.py
git commit -m "feat: add priority automation popups and speech dedupe"
```

## Task 5: Gateway lifecycle, five-minute cycle, urgent sensors and APIs

**Files:**
- Modify: `backend/d6/gateway_v6.py`
- Modify: `backend/d6/automation/smart_adjustment_engine.py`
- Test: `tests/test_gateway_automation_contract.py`

**Interfaces:**
- `POST /api/ai/automation/evaluate`
- `GET /api/ai/automation/catalog`
- `GET /api/ai/automation/status`
- `GET /api/ai/automation/executions`
- `GET /api/ai/automation/popups`
- `POST /api/ai/automation/popups/acknowledge`

- [ ] **Step 1: Write failing tests**

```python
def test_cycle_uses_monotonic_fixed_schedule_and_deduplicates_manual_trigger():
    source = GATEWAY.read_text(encoding="utf-8")
    assert "smart_adjustment_engine" in source
    assert "next_run += 300.0" in source
    assert "/api/ai/automation/evaluate" in source

def test_alarm_event_bypasses_routine_cooldown_and_enters_popup_outbox():
    result = run_urgent_alarm(smoke_payload)
    assert result["popup"]["priority"] == "critical"
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_gateway_automation_contract -v`

Expected: FAIL because the new routes and lifecycle wiring are absent.

- [ ] **Step 3: Integrate without duplicating old guard rules**

Initialize the engine after hardware bridge load, feed it the existing `_DEVICE_STATUS`/`_SENSOR_STATUS` and external structured weather cache, run it from the fixed five-minute loop, and invoke urgent evaluation from kitchen/security event handlers. Existing AdaptiveGuard remains the safety owner for A003–A005/A018–A020; the engine consumes its receipts and does not issue duplicate safety commands.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_gateway_automation_contract -v`

Expected: PASS for route shapes, no duplicate action owner, and alarm priority.

- [ ] **Step 5: Commit**

```powershell
git add backend/d6/gateway_v6.py backend/d6/automation tests/test_gateway_automation_contract.py
git commit -m "feat: wire automation engine into D6 gateway"
```

## Task 6: AI rule expansion and long-term feedback

**Files:**
- Create: `backend/d6/automation/ai_rule_expander.py`
- Modify: `backend/d6/gateway_v6.py`
- Test: `tests/test_ai_rule_expander.py`

**Interfaces:**
- `parse_candidate(model_text) -> dict`
- `validate_candidate(candidate, catalog, capabilities) -> list[str]`
- `simulate_candidate(candidate, snapshots) -> SimulationReport`
- `promote_if_eligible(candidate, report, state_store) -> bool`

- [ ] **Step 1: Write failing tests**

```python
def test_generated_rule_cannot_add_door_open_or_alarm_disable():
    candidate = parse_candidate('{"actions":[{"deviceId":"door_01","action":"open"}]}')
    assert any("door" in error for error in validate_candidate(candidate, catalog, capabilities))

def test_candidate_needs_seven_dry_runs_and_three_days_without_conflict():
    assert not promote_if_eligible(candidate, report_with_six_runs, store)
    assert promote_if_eligible(candidate, report_with_seven_runs_three_days, store)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_ai_rule_expander -v`

Expected: FAIL because candidate parsing and promotion are absent.

- [ ] **Step 3: Implement constrained AI extension**

Accept structured JSON only, reject free-form commands, pin validator/catalog versions, store model/provider and rule hash, simulate without hardware calls, and promote only low-risk candidates satisfying the seven-run/three-day/no-conflict gate. Feedback may adjust bounded thresholds but never permissions or devices.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_ai_rule_expander -v`

Expected: PASS for malformed input, capability mismatch, door bypass and promotion lifecycle.

- [ ] **Step 5: Commit**

```powershell
git add backend/d6/automation/ai_rule_expander.py backend/d6/gateway_v6.py tests/test_ai_rule_expander.py
git commit -m "feat: constrain AI-generated automation rules"
```

## Task 7: OpenHarmony popup consumer and automatic adjustment speech

**Files:**
- Modify: `entry/src/main/ets/api/assistantApi.ets`
- Modify: `entry/src/main/ets/pages/ControlPanelPage.ets`
- Modify: `entry/src/main/ets/api/types.ets`
- Test: `tests/test_control_center_contract.py`

**Interfaces:**
- `AssistantApi.getAutomationPopups(since, limit)`
- `AssistantApi.acknowledgeAutomationPopup(id)`
- `AutomationPopup` type with `id`, `priority`, `kind`, `title`, `reason`, `deviceResults`, `createdAt`, `acknowledged`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_frontend_reads_automation_popups_and_keeps_alarm_priority():
    source = read("api/assistantApi.ets") + read("pages/ControlPanelPage.ets")
    assert "/api/ai/automation/popups" in source
    assert "critical" in source
    assert "我已知晓" in source
    assert "自动联动" in source
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_frontend_reads_automation_popups_and_keeps_alarm_priority -v`

Expected: FAIL because the new API/type/consumer are absent.

- [ ] **Step 3: Implement concise popup consumer**

Poll the outbox with the existing feed timer, render one top-priority popup, render a rule batch as one card with device rows, preserve the existing alarm acknowledgement path, and use `ChatApi.speak` only for policy-approved speech. Do not show rule JSON, model text or internal IDs.

- [ ] **Step 4: Run GREEN and build**

Run: `python -m unittest tests.test_control_center_contract.ControlCenterContractTests.test_frontend_reads_automation_popups_and_keeps_alarm_priority -v`

Then build: `& 'D:\devEco\DevEco Studio\tools\hvigor\bin\hvigorw.bat' assembleHap --mode module -p product=default -p module=entry@default -p buildMode=debug --no-daemon`

Expected: test PASS and `BUILD SUCCESSFUL`.

- [ ] **Step 5: Commit**

```powershell
git add entry/src/main/ets/api/assistantApi.ets entry/src/main/ets/pages/ControlPanelPage.ets entry/src/main/ets/api/types.ets tests/test_control_center_contract.py
git commit -m "feat: render concise automation result popups"
```

## Task 8: D6 deployment, real-device verification and documentation

**Files:**
- Modify: `docs/A9智能家居功能展示与验收文档.md`
- Modify: `C:\Users\xyls\Desktop\同步文档.md`
- Test/fixture: `work/verify_automation_d6.py`

- [ ] **Step 1: Write the D6 verification fixture**

The fixture must call `/api/health`, `/api/ai/automation/status`, `/api/ai/automation/catalog`, `/api/ai/automation/evaluate` in dry-run mode, `/api/ai/automation/popups`, and `/api/devices`; it must print rule count, enabled/unlocked counts, popup priority and device online states.

- [ ] **Step 2: Run the fixture before deployment**

Run: `python work/verify_automation_d6.py`

Expected before deployment: FAIL with missing route or catalog endpoint.

- [ ] **Step 3: Deploy backend and HAP**

```powershell
$hdc='D:\command-line-tools\sdk\default\openharmony\toolchains\hdc.exe'
& $hdc file send backend\d6\automation /data/A9/smart_home/automation
& $hdc file send backend\d6\gateway_v6.py /data/A9/smart_home/gateway_v6.py
& $hdc shell 'setsid sh /data/A9/run_v6.sh >/data/A9/run_v6_setsid.log 2>&1 &'
& $hdc file send entry\build\default\outputs\default\entry-default-signed.hap /data/local/tmp/entry-default-signed.hap
& $hdc shell 'aa force-stop com.smarthome.openharmony; bm install -p /data/local/tmp/entry-default-signed.hap; rm -f /data/local/tmp/entry-default-signed.hap; aa start -a EntryAbility -b com.smarthome.openharmony'
```

- [ ] **Step 4: Run GREEN on D6**

Run: `& $hdc shell '/data/A9/bin/python3 /data/local/tmp/verify_automation_d6.py'`

Expected: health 200, catalog 100, no removed devices, all actions auditable, no door-open rule, and real device status online where the field network is available.

- [ ] **Step 5: Update docs and commit**

Record rule count, active tier, popup examples, voice policy, D6 PID, HAP install result, test count, and any offline capability in both desktop documents. Then run `git diff --check`, secret scan, full tests, and commit:

```powershell
git add docs work/verify_automation_d6.py
git commit -m "docs: record 100-rule automation deployment"
```

## Checkpoints

### After Tasks 1–3

- [ ] Catalog count/validation, snapshot persistence, conflict resolution and action receipts pass.
- [ ] No hardware command is made by a rule with stale data or a door action.

### After Tasks 4–6

- [ ] Critical popup priority, routine per-rule popup, speech policy and AI candidate promotion pass.
- [ ] Gateway five-minute and urgent paths do not duplicate existing AdaptiveGuard actions.

### After Tasks 7–8

- [ ] ArkTS build succeeds, D6 health/API checks return 200, real reversible light/curtain/AC actions are restored after test.
- [ ] Full Python suite passes with zero failures and both desktop documents match the deployed behavior.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Existing AdaptiveGuard duplicates core safety rules | Duplicate commands, noisy speech | Keep one action owner; engine consumes safety receipts for A003–A005/A018–A020 |
| Weather cache stale or malformed | Wrong curtain/AC action | TTL, schema validation, unavailable state and automatic relock |
| Rule flapping or manual conflict | User loses control | Hysteresis, minimum dwell, persisted manual override |
| Popup storm hides smoke alert | Safety visibility failure | Separate critical queue and priority preemption |
| Device command accepted but state unchanged | False user feedback | Mandatory hardware readback and `changed` field |
| AI extension broadens permissions | Security breach | Fixed capability enum, candidate dry-run, seven-run/three-day promotion, permanent door/security deny |
| D6 restart loses pending feedback | Missing audit trail | SQLite WAL and popup outbox transaction |
