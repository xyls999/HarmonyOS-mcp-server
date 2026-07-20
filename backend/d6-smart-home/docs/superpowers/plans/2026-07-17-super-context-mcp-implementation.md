# A9 Super Context and MCP Implementation Plan

**Status:** Complete on 2026-07-18 (Asia/Shanghai). Local and device suites: 54/54; active source compile: pass; deployed core hashes: 13/13; HTTP/MCP/context/radar/door rejection/autostart/reversible light checks: pass. Real door actuation and whole-device reboot were intentionally not performed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagent execution is disabled for this workspace; execute inline with review checkpoints.

**Goal:** Build, test, deploy, and document a large-scale AI context collection and MCP layer for the A9 smart-home backend while preserving real hardware semantics and enforcing explicit door passwords.

**Architecture:** Add a focused `ContextEngine` for collection, SQLite persistence, retrieval, and prompt packing; add a transport-neutral `SuperMCP` dispatcher; integrate both into the existing gateway. Treat the field startup package as the source of truth for hardware behavior, while keeping the HTTP gateway as the orchestration layer.

**Tech Stack:** Python 3.14 standard library, SQLite, JSON-RPC 2.0, MCP 2025-11-25, `unittest`, HarmonyOS HDC.

## Global Constraints

- No pip dependencies on the A9 device.
- Main database: `/data/A9/control/data/smart_home.db`.
- Generated snapshot: `/data/A9/smart_home/project_context.json`.
- Automatic prompt context default maximum: 48,000 characters.
- Millimeter-wave presence remains enabled; `radar_presence` and `radar_light` are independent.
- Door open and close require a password supplied for that call; never persist or log it.
- Field package `central_controller.py`, `devices.json`, `ac_ir_codes.json`, and protocol documents are authoritative for hardware behavior.
- Radar source is bathroom H3863; valid distance is 20-110cm; zones are 20-35, 40-55, 60-85, and 90-110cm; stability is 5 of 7 samples.
- Edge command security is HMAC-SM3-TAG32 plus nonce; do not describe it as end-to-end SM2/SM4/TLS.
- No real door actuation test and no whole-device reboot test.
- Existing files must be backed up before device deployment.
- Workspace is not a Git repository. Replace commit steps with SHA-256 checkpoint manifests and device timestamp backups.

---

## File Map

**Create locally and deploy:**

- `context_engine.py`: schema migration, redaction, collectors, retrieval, prompt packing, snapshot generation.
- `super_mcp.py`: MCP JSON-RPC dispatcher, resource registry, tool registry, schema validation.
- `tests/test_context_engine.py`: context persistence, redaction, retrieval, greeting, dynamic entity tests.
- `tests/test_super_mcp.py`: MCP lifecycle, resource, tool, validation, error tests.
- `tests/test_gateway_context.py`: gateway integration tests with fake engine and fake MCP.
- `tests/test_hardware_contract.py`: field package radar, door, and rate-limit contract tests.
- `tests/test_security_invariants.py`: recursive secret and password persistence checks.

**Modify locally and deploy:**

- `gateway_v6.py`: context initialization, prompt injection, context APIs, `/mcp`, event write-through, tool handlers.
- `hardware_bridge.py`: explicit door-password boundary, use field controller, remove duplicate rate-limit write.
- `mcp_server_enhanced.py`: stdio wrapper around `SuperMCP`.
- `connect/central_controller.py`: field-package authoritative copy plus explicit-password API helper.
- `connect/devices.json`: field-package authoritative copy plus `radar_presence.enabled=true` without changing `radar_light` behavior.
- `connect/ac_ir_codes.json`: field-package authoritative codebook.
- `run_v6.sh`: syntax-safe launch and root-only runtime environment loading.

**Documentation:**

- `docs/A9_SUPER_CONTEXT_MCP_ALIGNMENT.md`: implementation-aligned source document.
- Desktop delivery: `A9智慧家居_超级上下文_MCP_前后端完整对齐文档.md`.

---

### Task 1: Establish the authoritative hardware baseline

**Files:**

- Baseline from: `C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717\central_controller.py`
- Baseline from: `C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717\devices.json`
- Baseline from: `C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717\ac_ir_codes.json`
- Modify: `C:\Users\xyls\Desktop\A9_backend_upgrade\hardware_bridge.py`
- Create: `C:\Users\xyls\Desktop\A9_backend_upgrade\tests\test_hardware_contract.py`

**Interfaces:**

- Produces `verify_door_password_explicit(config: dict, password: str | None) -> bool`.
- Produces `get_radar_feature_config(config: dict) -> dict`.
- Preserves all existing `central_controller.py` public functions used by `hardware_bridge.py`.

- [ ] **Step 1: Synchronize untouched field baselines into the local backend tree**

Create `connect/`, copy the three authoritative files without editing their content, then record hashes. This is baseline synchronization, not feature implementation.

Run:

```powershell
New-Item -ItemType Directory -Force C:\Users\xyls\Desktop\A9_backend_upgrade\connect
Copy-Item C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717\central_controller.py C:\Users\xyls\Desktop\A9_backend_upgrade\connect\central_controller.py
Copy-Item C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717\devices.json C:\Users\xyls\Desktop\A9_backend_upgrade\connect\devices.json
Copy-Item C:\Users\xyls\Desktop\A9_现场启动脚本包_20260717\ac_ir_codes.json C:\Users\xyls\Desktop\A9_backend_upgrade\connect\ac_ir_codes.json
Get-FileHash C:\Users\xyls\Desktop\A9_backend_upgrade\connect\*
```

Expected: copied hashes exactly equal the field-package hashes.

- [ ] **Step 2: Write failing hardware contract tests**

```python
def test_explicit_door_password_does_not_fall_back_to_environment():
    os.environ["A9_DOOR_PASSWORD"] = "must-not-be-used"
    with self.assertRaisesRegex(ValueError, "password required for this request"):
        controller.verify_door_password_explicit(self.config, None)

def test_radar_presence_defaults_enabled_and_is_not_radar_light():
    feature = controller.get_radar_feature_config(self.config)
    self.assertTrue(feature["enabled"])
    self.assertEqual(feature["source_device"], "bathroom")
    self.assertNotIn("radar_light", feature)

def test_radar_zone_gaps_remain_unmatched():
    self.assertIsNone(controller.radar_zone_for_distance(self.config, 38))

def test_hardware_bridge_does_not_preconsume_rate_limit():
    self.assertNotIn("_enforce_rate(device_id)", inspect.getsource(bridge.hw_toggle))
```

- [ ] **Step 3: Run RED**

Run:

```powershell
python -m unittest tests.test_hardware_contract -v
```

Expected: failure because explicit password and radar feature helpers do not exist, and bridge still pre-enforces rate limits.

- [ ] **Step 4: Implement the minimal hardware contract**

Add to `central_controller.py`:

```python
def verify_door_password_explicit(config, password):
    if not password:
        raise ValueError("door password required for this request")
    return verify_door_password(config, password)

def get_radar_feature_config(config):
    radar = config.get("radar", {})
    presence = radar.get("radar_presence", {"enabled": True})
    return {
        "enabled": bool(presence.get("enabled", True)),
        "source_device": radar.get("source_device", "bathroom"),
        "sensor": radar.get("sensor", "Rd-03 V2"),
    }
```

Update `hardware_bridge.py` to require an explicit door password for API calls and remove bridge-level `_enforce_rate(device_id)` calls. Keep error classification; central controller remains the only rate-limit writer.

Add to `devices.json` under `radar`:

```json
"radar_presence": {
  "enabled": true,
  "description": "毫米波人体存在感知总开关"
}
```

- [ ] **Step 5: Run GREEN and checkpoint**

Run:

```powershell
python -m unittest tests.test_hardware_contract -v
Get-FileHash C:\Users\xyls\Desktop\A9_backend_upgrade\connect\central_controller.py,C:\Users\xyls\Desktop\A9_backend_upgrade\hardware_bridge.py
```

Expected: all hardware contract tests pass.

---

### Task 2: Context storage, redaction, and event journal

**Files:**

- Create: `context_engine.py`
- Create: `tests/test_context_engine.py`
- Create: `tests/test_security_invariants.py`

**Interfaces:**

- Produces `ContextEngine(db_path, root_dir, snapshot_path, max_chars=48000)`.
- Produces `migrate()`, `redact_sensitive(value)`, `record_event(...)`, `upsert_entity(...)`, and `upsert_document(...)`.

- [ ] **Step 1: Write failing schema and redaction tests**

```python
def test_migrate_is_idempotent(self):
    self.engine.migrate()
    self.engine.migrate()
    names = {row[0] for row in self.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    self.assertTrue({"ai_context_documents", "ai_context_entities", "ai_context_events", "ai_context_sync_state", "ai_context_snapshots"} <= names)

def test_redaction_is_recursive(self):
    value = {"password": "p", "nested": [{"token": "t"}], "safe": "ok"}
    self.assertEqual(self.engine.redact_sensitive(value)["safe"], "ok")
    self.assertEqual(self.engine.redact_sensitive(value)["password"], "<redacted>")
    self.assertEqual(self.engine.redact_sensitive(value)["nested"][0]["token"], "<redacted>")

def test_record_event_never_persists_password(self):
    self.engine.record_event("door", "attempt", details={"password": "secret"})
    raw = self.conn.execute("SELECT details_json FROM ai_context_events").fetchone()[0]
    self.assertNotIn("secret", raw)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_context_engine tests.test_security_invariants -v`

Expected: import failure for missing `context_engine`.

- [ ] **Step 3: Implement minimal storage and redaction**

Implement parameterized schema creation and methods with per-operation connections. Sensitive key matching must include `password`, `passcode`, `token`, `secret`, `api_key`, `authorization`, `private_key`, `shared_key`, `salt`, and `hash` when values originate outside explicitly safe metadata.

- [ ] **Step 4: Run GREEN and checkpoint**

Run: `python -m unittest tests.test_context_engine tests.test_security_invariants -v`

Expected: schema and redaction tests pass with no warnings.

---

### Task 3: Full collectors and atomic project snapshot

**Files:**

- Modify: `context_engine.py`
- Modify: `tests/test_context_engine.py`

**Interfaces:**

- Produces `collect_static_sources() -> dict`.
- Produces `collect_database_state() -> dict`.
- Produces `ingest_log(path: Path, source: str) -> int`.
- Produces `rebuild_snapshot() -> dict`.

- [ ] **Step 1: Write failing collector tests**

```python
def test_static_collection_extracts_python_symbols_and_markdown(self):
    result = self.engine.collect_static_sources()
    self.assertGreater(result["documents"], 0)
    hits = self.engine.search("radar zone stable samples", limit=10)
    self.assertTrue(any("radar" in item["content"].lower() for item in hits))

def test_log_ingestion_uses_cursor_and_does_not_duplicate(self):
    first = self.engine.ingest_log(self.log_path, "gateway")
    second = self.engine.ingest_log(self.log_path, "gateway")
    self.assertGreater(first, 0)
    self.assertEqual(second, 0)

def test_snapshot_is_valid_and_contains_all_entity_groups(self):
    snapshot = self.engine.rebuild_snapshot()
    self.assertTrue(self.snapshot_path.exists())
    for key in ("devices", "sensors", "scenes", "apis", "capabilities", "safety", "collectionStats"):
        self.assertIn(key, snapshot)
```

- [ ] **Step 2: Run RED**

Expected: missing collector methods.

- [ ] **Step 3: Implement AST, Markdown, database, and log collectors**

Use `ast.parse` for Python symbol extraction, heading-aware Markdown chunks, table allowlists for database collection, and byte offsets for append-only logs. Write the snapshot to `project_context.json.tmp`, flush, then `os.replace`.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_context_engine -v`

Expected: all collector and snapshot tests pass.

---

### Task 4: Retrieval, large-context packing, and greeting behavior

**Files:**

- Modify: `context_engine.py`
- Modify: `tests/test_context_engine.py`

**Interfaces:**

- Produces `is_opening_greeting(text: str, is_first_turn: bool) -> bool`.
- Produces `search(query: str, limit=40, event_limit=60) -> list[dict]`.
- Produces `build_prompt_context(query: str, *, is_first_turn: bool, live_state: dict | None=None) -> str`.

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_first_turn_greeting_skips_large_context(self):
    self.assertEqual(self.engine.build_prompt_context("你好", is_first_turn=True), "")

def test_first_turn_with_device_request_is_not_skipped(self):
    text = self.engine.build_prompt_context("你好，毫米波现在开着吗", is_first_turn=True)
    self.assertIn("毫米波", text)

def test_exact_entity_and_recent_event_outscore_generic_document(self):
    hits = self.engine.search("door_01 最近为什么失败")
    self.assertEqual(hits[0]["entity_id"], "door_01")

def test_prompt_is_large_but_bounded(self):
    text = self.engine.build_prompt_context("整个项目功能和最近日志", is_first_turn=False)
    self.assertLessEqual(len(text), 48000)
    self.assertIn("可调用工具", text)
```

- [ ] **Step 2: Run RED**

Expected: missing retrieval and prompt methods.

- [ ] **Step 3: Implement deterministic hybrid scoring**

Score exact IDs and aliases first, then phrase overlap, token overlap, source priority, severity, and recency. Pack sections in the specification order and deduplicate by content hash.

- [ ] **Step 4: Run GREEN**

Run: `python -m unittest tests.test_context_engine -v`

Expected: retrieval tests pass deterministically.

---

### Task 5: MCP protocol core, resources, and tools

**Files:**

- Create: `super_mcp.py`
- Create: `tests/test_super_mcp.py`
- Modify: `mcp_server_enhanced.py`

**Interfaces:**

- Produces `SuperMCP(context_engine, tool_handlers=None)`.
- Produces `dispatch(message: dict, auth: dict | None=None) -> dict | None`.
- Produces `list_tools()`, `list_resources()`, and `read_resource(uri)`.

- [ ] **Step 1: Write failing MCP contract tests**

```python
def test_initialize_declares_tools_and_resources(self):
    result = self.mcp.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
    self.assertEqual(result["result"]["protocolVersion"], "2025-11-25")
    self.assertIn("tools", result["result"]["capabilities"])
    self.assertIn("resources", result["result"]["capabilities"])

def test_tools_call_returns_structured_content(self):
    result = self.call("search_context", {"query": "radar"})
    self.assertFalse(result["result"]["isError"])
    self.assertIn("structuredContent", result["result"])

def test_unknown_method_uses_json_rpc_error(self):
    result = self.mcp.dispatch({"jsonrpc": "2.0", "id": 3, "method": "unknown"})
    self.assertEqual(result["error"]["code"], -32601)
```

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_super_mcp -v`

Expected: import failure for missing `super_mcp`.

- [ ] **Step 3: Implement MCP dispatcher and stable generic tools**

Implement `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, `resources/list`, and `resources/read`. Tool business failures use `isError=true`; protocol failures use JSON-RPC errors. Tool definitions include JSON Schema and annotations.

- [ ] **Step 4: Replace stdio wrapper**

`mcp_server_enhanced.py` must read one JSON object per line from stdin, write only JSON-RPC to stdout, and send logs to stderr.

- [ ] **Step 5: Run GREEN**

Run: `python -m unittest tests.test_super_mcp -v`

Expected: MCP tests pass.

---

### Task 6: Gateway context injection and HTTP APIs

**Files:**

- Modify: `gateway_v6.py`
- Create: `tests/test_gateway_context.py`

**Interfaces:**

- Initializes global `_context_engine` and `_super_mcp` in `main()`.
- Adds context APIs and authenticated `/mcp` POST.
- Adds `GET /mcp` returning 405 when SSE is not offered.

- [ ] **Step 1: Write failing gateway integration tests**

Test source-level route registration and behavior through an in-process `ThreadingHTTPServer` using temporary database paths and fake hardware handlers. Verify:

```python
self.assertIn('/api/ai/context/search', source)
self.assertIn('p == "/mcp"', source)
self.assertIn('build_prompt_context', source)
self.assertNotIn('"/api/health"', source)
```

Add an integration assertion that `_chat` passes packed context to the upstream `chat()` function for substantive messages and passes no large context for a first-turn greeting.

- [ ] **Step 2: Run RED**

Run: `python -m unittest tests.test_gateway_context -v`

Expected: missing routes and context integration.

- [ ] **Step 3: Implement minimal gateway integration**

Add imports, startup initialization, GET/POST routes, Origin/auth checks for `/mcp`, context stats/search/rebuild/events handlers, and automatic context injection before `chat()`.

- [ ] **Step 4: Add write-through events**

Record device actions, scene activation, linkage changes, custom device changes, security blocks, and MCP calls. Pass only redacted data.

- [ ] **Step 5: Run GREEN**

Run: `python -m unittest tests.test_gateway_context tests.test_security_invariants -v`

Expected: gateway integration and security tests pass.

---

### Task 7: Dynamic devices, capabilities, radar, and door MCP tools

**Files:**

- Modify: `super_mcp.py`
- Modify: `gateway_v6.py`
- Modify: `tests/test_super_mcp.py`
- Modify: `tests/test_hardware_contract.py`

**Interfaces:**

- Tool handlers: `list_devices`, `get_device`, `control_device`, `toggle_device`, `register_device`, `register_capability`, `get_radar_config`, `set_radar_enabled`, `door_control`.

- [ ] **Step 1: Write failing dynamic and safety tests**

```python
def test_registered_device_is_immediately_searchable_and_controllable(self):
    self.call("register_device", self.custom_device)
    self.assertEqual(self.call("get_device", {"device_id": "custom_01"})["result"]["structuredContent"]["id"], "custom_01")

def test_door_tool_rejects_missing_password_before_handler(self):
    result = self.call("door_control", {"action": "open"})
    self.assertTrue(result["result"]["isError"])
    self.assertIn("manual password", result["result"]["content"][0]["text"])

def test_radar_presence_switch_does_not_change_radar_light(self):
    before = self.linkage("radar_light")
    self.call("set_radar_enabled", {"enabled": True})
    self.assertEqual(self.linkage("radar_light"), before)
```

- [ ] **Step 2: Run RED**

Expected: missing handlers and validation.

- [ ] **Step 3: Implement safe handler registration**

Use generic tools, not one tool per device. Resolve dynamic capabilities from `device_registry` and `ai_context_entities`. Allow only the executor types named in the specification. Never accept shell, Python code, file paths, or arbitrary URLs.

- [ ] **Step 4: Implement door and radar invariants**

Door handlers require non-empty `password`, remove it before event logging, and call the explicit hardware boundary. Radar config writes only `radar_presence`; it must not mutate `radar_light`.

- [ ] **Step 5: Run GREEN**

Run: `python -m unittest tests.test_super_mcp tests.test_hardware_contract tests.test_security_invariants -v`

Expected: all dynamic and safety tests pass.

---

### Task 8: Full local verification and deployment bundle

**Files:** all modified source and tests.

- [ ] **Step 1: Run complete local suite**

```powershell
python -m unittest discover -s C:\Users\xyls\Desktop\A9_backend_upgrade\tests -p "test_*.py" -v
python -m compileall C:\Users\xyls\Desktop\A9_backend_upgrade
```

Expected: zero failures and compile exit code 0.

- [ ] **Step 2: Run secret-pattern scan**

Scan generated JSON, tests, source, and planned documentation. Expected: no real passwords, API keys, tokens, shared keys, or private keys in new artifacts.

- [ ] **Step 3: Create local checkpoint manifest**

```powershell
Get-FileHash -Algorithm SHA256 C:\Users\xyls\Desktop\A9_backend_upgrade\gateway_v6.py,C:\Users\xyls\Desktop\A9_backend_upgrade\context_engine.py,C:\Users\xyls\Desktop\A9_backend_upgrade\super_mcp.py,C:\Users\xyls\Desktop\A9_backend_upgrade\hardware_bridge.py
```

Save hashes in the deployment log.

---

### Task 9: Device backup, deploy, launch, and runtime verification

**Files:** `/data/A9/smart_home/*`, `/data/A9/run_v6.sh`, `/etc/init/smart_home.cfg`.

- [ ] **Step 1: Create timestamped device backup**

Backup source, startup script, config, and database without deleting existing backups. Resolve and verify every backup path remains under `/data/A9/backups/`.

- [ ] **Step 2: Deploy source and field baseline**

Use `hdc file send` where reliable; verify device SHA-256 equals local SHA-256 for every deployed file before launch.

- [ ] **Step 3: Run device syntax and unit tests**

Use the portable Python loader. Expected: source AST parse succeeds and tests that do not actuate hardware pass.

- [ ] **Step 4: Start gateway and condition-wait for health**

Run `/data/A9/run_v6.sh`, then poll `/health` for up to 30 seconds. Do not use a fixed long sleep.

- [ ] **Step 5: Verify runtime APIs and MCP**

Verify:

- `/health`
- `/api/ai/context/stats`
- `/api/ai/context/search`
- MCP `initialize`
- MCP `tools/list`
- MCP `resources/list`
- `project_context.json` validity
- database context row counts
- `radar_presence.enabled=true`
- missing-password door rejection
- no password in logs/events

- [ ] **Step 6: Run reversible physical test**

Read current state of one light, toggle once, then restore the exact original state. Do not test door, curtain, fan, air conditioner, buzzer, or radar auto-light actuation.

- [ ] **Step 7: Verify startup integration**

Confirm `/etc/init/smart_home.cfg` references executable, verified `/data/A9/run_v6.sh`. Restart the gateway process once and re-run health checks. Do not reboot the device.

---

### Task 10: Alignment documentation and final evidence

**Files:**

- Create: `docs/A9_SUPER_CONTEXT_MCP_ALIGNMENT.md`
- Create desktop delivery: `C:\Users\xyls\Desktop\A9智慧家居_超级上下文_MCP_前后端完整对齐文档.md`

- [ ] **Step 1: Generate implementation-aligned documentation**

Include actual schemas, actual routes, MCP requests/responses, front-end types, server examples, custom device registration, radar/door rules, deployment, rollback, security, and measured test results.

- [ ] **Step 2: Verify every documented route against source**

Extract route strings from `gateway_v6.py` and compare with the API tables. Any undocumented source route or nonexistent documented route is a failure.

- [ ] **Step 3: Re-run final verification**

Run the complete local suite, device health checks, MCP checks, context statistics, and documentation secret scan fresh.

- [ ] **Step 4: Report evidence**

Report exact test counts, device process/port state, context row counts, snapshot size, MCP tool/resource counts, radar state, door rejection evidence, startup configuration, backup path, and remaining external credential-rotation limitation.
