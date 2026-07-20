import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

try:
    from context_engine import ContextEngine
except ImportError:
    ContextEngine = None


class SecurityInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db_path = root / "db.sqlite"
        self.snapshot_path = root / "project_context.json"
        self.assertIsNotNone(ContextEngine, "context_engine module is missing")
        self.engine = ContextEngine(self.db_path, root, self.snapshot_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sensitive_values_do_not_survive_document_or_event_writes(self):
        marker = "NEVER_PERSIST_THIS_PASSWORD"
        self.engine.upsert_document(
            "secret-doc",
            source_type="doc",
            source_uri="secret.md",
            title="secret",
            content=f"password={marker}",
        )
        self.engine.record_event(
            "tool_call",
            f"Authorization: Bearer {marker}",
            details={"doorPassword": marker},
        )
        raw = self.db_path.read_bytes()
        self.assertNotIn(marker.encode(), raw)

    def test_safe_boolean_password_metadata_is_preserved(self):
        event_id = self.engine.record_event(
            "door",
            "manual password supplied",
            details={"passwordProvided": True},
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            details = json.loads(
                conn.execute(
                    "SELECT details_json FROM ai_context_events WHERE id=?",
                    (event_id,),
                ).fetchone()[0]
            )
        self.assertIs(details["passwordProvided"], True)

    def test_startup_scripts_load_root_only_env_instead_of_embedding_secrets(self):
        root = Path(__file__).resolve().parents[1]
        script_root = next(
            candidate for candidate in (root, root.parent)
            if (candidate / "run_v6.sh").exists()
        )
        backend = (script_root / "run_v6.sh").read_text(encoding="utf-8")
        tunnel = (script_root / "run_tunnel.sh").read_text(encoding="utf-8")
        self.assertIn(".a9_backend.env", backend)
        self.assertIn(".a9_tunnel.env", tunnel)
        self.assertIn("tunnel_client_fast.py", tunnel)
        for source in (backend, tunnel):
            self.assertNotRegex(
                source,
                r"(?m)^export\s+(?:[A-Z0-9_]*(?:KEY|TOKEN|PASSWORD))=.+$",
            )

    def test_autostart_config_keeps_startup_scripts_root_only(self):
        root = Path(__file__).resolve().parents[1]
        config_path = root / "deploy" / "smart_home.cfg"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        commands = config["jobs"][0]["cmds"]
        self.assertIn("chmod 0700 /data/A9/run_v6.sh", commands)
        self.assertIn("chmod 0700 /data/A9/run_tunnel.sh", commands)
        self.assertNotIn("chmod 0755 /data/A9/run_v6.sh", commands)
        self.assertNotIn("chmod 0755 /data/A9/run_tunnel.sh", commands)
        self.assertTrue(any("run_v6.sh" in command for command in commands))
        self.assertTrue(any("run_tunnel.sh" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
