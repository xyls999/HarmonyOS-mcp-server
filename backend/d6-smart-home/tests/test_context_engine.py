import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

try:
    from context_engine import ContextEngine
    from adaptive_guard import AdaptiveGuard
except ImportError:
    ContextEngine = None
    AdaptiveGuard = None


class ContextEngineStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "smart_home.db"
        self.snapshot_path = self.root / "project_context.json"
        self.assertIsNotNone(ContextEngine, "context_engine module is missing")
        self.engine = ContextEngine(
            db_path=self.db_path,
            root_dir=self.root,
            snapshot_path=self.snapshot_path,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def seed_domain_tables(self):
        with closing(self.connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices(
                    id TEXT PRIMARY KEY, name TEXT, type TEXT, room TEXT,
                    status TEXT, is_on INTEGER, primary_value INTEGER, protocol TEXT
                );
                CREATE TABLE IF NOT EXISTS sensors(
                    id TEXT PRIMARY KEY, name TEXT, type TEXT, room TEXT,
                    current_value REAL, unit TEXT, is_alert INTEGER
                );
                CREATE TABLE IF NOT EXISTS scenes(
                    id TEXT PRIMARY KEY, name TEXT, description TEXT, is_active INTEGER
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO devices VALUES(?,?,?,?,?,?,?,?)",
                ("radar_01", "毫米波雷达", "radar", "全局", "online", 1, 0, "wifi"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO sensors VALUES(?,?,?,?,?,?,?)",
                ("temp_01", "客厅温度", "temperature", "客厅", 24.5, "°C", 0),
            )
            conn.execute(
                "INSERT OR REPLACE INTO scenes VALUES(?,?,?,?)",
                ("s1", "回家", "回家模式", 0),
            )
            conn.commit()

    def test_migrate_is_idempotent(self):
        self.engine.migrate()
        self.engine.migrate()
        with closing(self.connect()) as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertTrue(
            {
                "ai_context_documents",
                "ai_context_entities",
                "ai_context_events",
                "ai_context_sync_state",
                "ai_context_snapshots",
            }
            <= names
        )

    def test_redaction_is_recursive(self):
        value = {
            "password": "p",
            "nested": [{"token": "t"}, {"Authorization": "Bearer abc"}],
            "safe": "ok",
        }
        result = self.engine.redact_sensitive(value)
        self.assertEqual(result["safe"], "ok")
        self.assertEqual(result["password"], "<redacted>")
        self.assertEqual(result["nested"][0]["token"], "<redacted>")
        self.assertEqual(result["nested"][1]["Authorization"], "<redacted>")

    def test_redaction_preserves_boolean_door_password_policy_metadata(self):
        result = self.engine.redact_sensitive(
            {
                "doorPasswordRequiredEveryCall": True,
                "doorPasswordPersisted": False,
                "doorPassword": "never-store-this",
            }
        )
        self.assertIs(result["doorPasswordRequiredEveryCall"], True)
        self.assertIs(result["doorPasswordPersisted"], False)
        self.assertEqual(result["doorPassword"], "<redacted>")

    def test_redaction_masks_secret_patterns_inside_text(self):
        text = "API_KEY=abcdef1234567890 Authorization: Bearer abc.def.ghi"
        redacted = self.engine.redact_sensitive(text)
        self.assertNotIn("abcdef1234567890", redacted)
        self.assertNotIn("abc.def.ghi", redacted)
        self.assertIn("<redacted>", redacted)

    def test_redaction_masks_chinese_password_phrasing(self):
        redacted = self.engine.redact_sensitive("门禁密码是 246810，继续操作")
        self.assertNotIn("246810", redacted)
        self.assertIn("<redacted>", redacted)

    def test_record_event_never_persists_password(self):
        event_id = self.engine.record_event(
            "door",
            "door attempt",
            details={"password": "secret-value", "passwordProvided": True},
            entity_type="device",
            entity_id="door_01",
        )
        self.assertGreater(event_id, 0)
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT summary, details_json FROM ai_context_events WHERE id=?",
                (event_id,),
            ).fetchone()
        self.assertNotIn("secret-value", row[1])
        details = json.loads(row[1])
        self.assertEqual(details["password"], "<redacted>")
        self.assertIs(details["passwordProvided"], True)

    def test_upserts_document_and_entity_without_duplicates(self):
        self.engine.upsert_document(
            "doc:test",
            source_type="doc",
            source_uri="test.md",
            title="Test",
            content="radar capability",
        )
        self.engine.upsert_document(
            "doc:test",
            source_type="doc",
            source_uri="test.md",
            title="Test updated",
            content="radar capability updated",
        )
        self.engine.upsert_entity(
            "device",
            "custom_01",
            name="Custom Device",
            aliases=["custom"],
            capabilities={"actions": ["toggle"]},
            state={"online": True},
        )
        self.engine.upsert_entity(
            "device",
            "custom_01",
            name="Custom Device",
            aliases=["custom"],
            capabilities={"actions": ["toggle"]},
            state={"online": False},
        )
        with closing(self.connect()) as conn:
            docs = conn.execute("SELECT COUNT(*) FROM ai_context_documents").fetchone()[0]
            entities = conn.execute("SELECT COUNT(*) FROM ai_context_entities").fetchone()[0]
            title = conn.execute("SELECT title FROM ai_context_documents").fetchone()[0]
        self.assertEqual(docs, 1)
        self.assertEqual(entities, 1)
        self.assertEqual(title, "Test updated")

    def test_static_collection_extracts_python_symbols_and_markdown(self):
        (self.root / "sample.py").write_text(
            '"""Radar module."""\nclass RadarService:\n'
            '    """Millimeter-wave presence service."""\n'
            '    def zone(self, distance_cm):\n        return distance_cm\n',
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            "# A9 Project\n\n## Radar\n\n7 samples require 5 stable matches.\n",
            encoding="utf-8",
        )
        result = self.engine.collect_static_sources()
        self.assertGreaterEqual(result["documents"], 3)
        with closing(self.connect()) as conn:
            text = "\n".join(
                row[0]
                for row in conn.execute(
                    "SELECT content FROM ai_context_documents ORDER BY id"
                )
            )
        self.assertIn("RadarService", text)
        self.assertIn("7 samples require 5 stable matches", text)

    def test_database_collection_upserts_devices_sensors_and_scenes(self):
        self.seed_domain_tables()
        result = self.engine.collect_database_state()
        self.assertEqual(result["devices"], 1)
        self.assertEqual(result["sensors"], 1)
        self.assertEqual(result["scenes"], 1)
        with closing(self.connect()) as conn:
            rows = conn.execute(
                "SELECT entity_type, entity_id FROM ai_context_entities ORDER BY entity_type"
            ).fetchall()
        self.assertIn(("device", "radar_01"), rows)
        self.assertIn(("sensor", "temp_01"), rows)
        self.assertIn(("scene", "s1"), rows)

    def test_database_collection_includes_custom_device_registry(self):
        template = {
            "id": "custom_01", "name": "自定义净化器", "type": "purifier",
            "room": "客厅", "aliases": ["净化器"],
            "capabilities": [{"action": "toggle", "params": {"isOn": "bool"}}],
        }
        with closing(self.connect()) as conn:
            conn.execute(
                "CREATE TABLE device_registry(device_id TEXT PRIMARY KEY, template_json TEXT)"
            )
            conn.execute(
                "INSERT INTO device_registry VALUES(?,?)",
                ("custom_01", json.dumps(template, ensure_ascii=False)),
            )
            conn.commit()
        result = self.engine.collect_database_state()
        self.assertEqual(result["device_registry"], 1)
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT name,aliases_json,capabilities_json FROM ai_context_entities "
                "WHERE entity_type='device' AND entity_id='custom_01'"
            ).fetchone()
        self.assertEqual(row[0], "自定义净化器")
        self.assertIn("净化器", row[1])
        self.assertIn("toggle", row[2])

    def test_log_ingestion_uses_cursor_and_does_not_duplicate(self):
        log_path = self.root / "gateway.log"
        log_path.write_text(
            "[10:00] gateway started\n[10:01] password=do-not-store\n",
            encoding="utf-8",
        )
        first = self.engine.ingest_log(log_path, "gateway")
        second = self.engine.ingest_log(log_path, "gateway")
        self.assertEqual(first, 2)
        self.assertEqual(second, 0)
        log_path.write_text(log_path.read_text(encoding="utf-8") + "[10:02] radar online\n", encoding="utf-8")
        third = self.engine.ingest_log(log_path, "gateway")
        self.assertEqual(third, 1)
        with closing(self.connect()) as conn:
            rows = conn.execute(
                "SELECT summary FROM ai_context_events WHERE source='gateway' ORDER BY id"
            ).fetchall()
        joined = "\n".join(row[0] for row in rows)
        self.assertNotIn("do-not-store", joined)
        self.assertIn("radar online", joined)

    def test_log_ingestion_batches_database_connections(self):
        log_path = self.root / "large.log"
        log_path.write_text(
            "".join(f"line {index}\n" for index in range(200)), encoding="utf-8"
        )
        original_connect = self.engine._connect
        calls = 0

        def counted_connect():
            nonlocal calls
            calls += 1
            return original_connect()

        self.engine._connect = counted_connect
        self.assertEqual(self.engine.ingest_log(log_path, "large"), 200)
        self.assertLessEqual(calls, 3, "log ingestion must use batch inserts")

    def test_snapshot_is_atomic_valid_and_contains_entity_groups(self):
        self.seed_domain_tables()
        self.engine.collect_database_state()
        self.engine.upsert_document(
            "doc:overview",
            source_type="doc",
            source_uri="README.md",
            title="Overview",
            content="A9 smart home capabilities",
        )
        snapshot = self.engine.rebuild_snapshot()
        self.assertTrue(self.snapshot_path.exists())
        self.assertFalse(self.snapshot_path.with_suffix(".json.tmp").exists())
        loaded = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["schemaVersion"], "1.0")
        for key in (
            "devices",
            "sensors",
            "scenes",
            "apis",
            "capabilities",
            "safety",
            "documentation",
            "recentActivity",
            "collectionStats",
        ):
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["devices"][0]["id"], "radar_01")

    def test_first_turn_greeting_skips_large_context(self):
        self.assertEqual(self.engine.build_prompt_context("你好", is_first_turn=True), "")

    def test_first_turn_with_device_request_is_not_skipped(self):
        self.engine.upsert_entity(
            "device",
            "radar_01",
            name="毫米波雷达",
            aliases=["毫米波", "人体存在"],
            capabilities={"enabled": True},
            state={"online": True},
        )
        text = self.engine.build_prompt_context("你好，毫米波现在开着吗", is_first_turn=True)
        self.assertIn("毫米波", text)

    def test_exact_entity_and_recent_event_outscore_generic_document(self):
        self.engine.upsert_document(
            "doc:generic-door",
            source_type="doc",
            source_uri="README.md",
            title="Door overview",
            content="Door operations can fail for several generic reasons.",
        )
        self.engine.upsert_entity(
            "device",
            "door_01",
            name="入户门",
            aliases=["door"],
            capabilities={"actions": ["query", "open", "close"]},
            state={"online": True},
        )
        self.engine.record_event(
            "operation_failed",
            "door_01 command failed due to timeout",
            entity_type="device",
            entity_id="door_01",
            severity="error",
        )
        hits = self.engine.search("door_01 最近为什么失败")
        self.assertEqual(hits[0]["entity_id"], "door_01")
        self.assertIn(hits[0]["kind"], {"entity", "event"})

    def test_search_finds_older_matching_event_beyond_recent_window(self):
        self.engine.record_event(
            "operation", "rare_history_marker device action", entity_id="old_01"
        )
        for index in range(30):
            self.engine.record_event("noise", f"unrelated event {index}")
        hits = self.engine.search("rare_history_marker", event_limit=5)
        self.assertTrue(
            any(hit.get("entity_id") == "old_01" for hit in hits),
            "older matching event must remain searchable",
        )

    def test_search_reads_original_operation_history_without_copying_it(self):
        with closing(self.connect()) as conn:
            conn.execute(
                "CREATE TABLE device_operations("
                "id INTEGER PRIMARY KEY, device_id TEXT, action TEXT, params_json TEXT, "
                "result TEXT, source TEXT, scene_id TEXT, created_at TEXT)"
            )
            conn.execute(
                "INSERT INTO device_operations VALUES(1,?,?,?,?,?,?,?)",
                ("custom_01", "calibrate", '{"note":"rare_operation_payload"}', "ok", "api", None, "2026-07-17 10:00:00"),
            )
            conn.commit()
        hits = self.engine.search("rare_operation_payload")
        self.assertTrue(any(hit.get("kind") == "history" for hit in hits))
        self.assertIn("custom_01", json.dumps(hits, ensure_ascii=False))

    def test_search_reads_guard_feedback_and_app_telemetry_as_live_history(self):
        self.assertIsNotNone(AdaptiveGuard)
        guard = AdaptiveGuard(self.db_path, executor=lambda _action: {"success": True})
        incident = guard.process_snapshot({"sensors": [{
            "id": "temp_01", "type": "temperature", "room": "客厅",
            "value": 33, "online": True, "isAlert": True,
        }]})[0]
        guard.submit_feedback(incident["id"], 9, "高温先制冷，恢复后提醒主人")
        guard.record_app_telemetry({
            "eventType": "button_result", "page": "settings",
            "action": "guard.enable", "result": "ok", "metadata": {"enabled": True},
        })
        feedback = self.engine.search("高温 制冷 主人", limit=20)
        telemetry = self.engine.search("settings guard enable", limit=20)
        self.assertTrue(any(item.get("table") == "guard_feedback" for item in feedback))
        self.assertTrue(any(item.get("table") == "app_telemetry_events" for item in telemetry))

    def test_prompt_is_large_but_bounded_and_advertises_tools(self):
        for index in range(80):
            self.engine.upsert_document(
                f"doc:{index}",
                source_type="doc",
                source_uri=f"doc-{index}.md",
                title=f"项目功能 {index}",
                content=("整个项目功能、设备、接口和最近日志。" * 100),
                priority=60,
            )
        text = self.engine.build_prompt_context("整个项目功能和最近日志", is_first_turn=False)
        self.assertLessEqual(len(text), 48_000)
        self.assertIn("可调用工具", text)
        self.assertIn("search_context", text)
        self.assertIn("door_control", text)

    def test_prompt_reads_snapshot_tool_catalog_on_each_substantive_turn(self):
        self.engine.upsert_entity(
            "mcp_tool", "unique_snapshot_tool", name="unique_snapshot_tool",
            capabilities={"description": "snapshot proof"}, state={},
        )
        self.engine.rebuild_snapshot()
        text = self.engine.build_prompt_context("完全无关的问题", is_first_turn=False)
        self.assertIn("unique_snapshot_tool", text)


if __name__ == "__main__":
    unittest.main()
