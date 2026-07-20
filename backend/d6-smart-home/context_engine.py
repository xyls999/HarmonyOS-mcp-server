"""Persistent, redacted context storage for the A9 smart-home gateway.

SQLite transaction behavior follows Python 3.14's sqlite3 documentation:
https://docs.python.org/3/library/sqlite3.html
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CST = timezone(timedelta(hours=8))
REDACTED = "<redacted>"
SENSITIVE_KEYS = (
    "password",
    "passcode",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "private_key",
    "shared_key",
)
SAFE_SENSITIVE_METADATA_KEYS = {
    "passwordprovided",
    "password_provided",
    "passwordrequired",
    "password_required",
    "doorpasswordrequiredeverycall",
    "doorpasswordpersisted",
}

_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passcode|authorization|"
    r"private[_-]?key|shared[_-]?key)\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_CHINESE_PASSWORD_RE = re.compile(
    r"(?i)(门禁)?密码\s*(?:是|为|[:=：])\s*[^\s，,。;；]+"
)


def _now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


class ContextEngine:
    """Own context persistence and redaction without executing device actions."""

    def __init__(
        self,
        db_path: str | Path,
        root_dir: str | Path,
        snapshot_path: str | Path,
        max_chars: int = 48_000,
    ) -> None:
        self.db_path = Path(db_path)
        self.root_dir = Path(root_dir)
        self.snapshot_path = Path(snapshot_path)
        self.max_chars = max(4_000, int(max_chars))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def migrate(self) -> None:
        """Create context tables and indexes; safe to run on every startup."""
        schema = """
        CREATE TABLE IF NOT EXISTS ai_context_documents (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_uri TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            keywords_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            priority INTEGER NOT NULL DEFAULT 50,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_context_documents_source
            ON ai_context_documents(source_type, source_uri);

        CREATE TABLE IF NOT EXISTS ai_context_entities (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            name TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            capabilities_json TEXT NOT NULL DEFAULT '{}',
            state_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'runtime',
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(entity_type, entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_context_entities_name
            ON ai_context_entities(entity_type, name);

        CREATE TABLE IF NOT EXISTS ai_context_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            summary TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'gateway',
            severity TEXT NOT NULL DEFAULT 'info',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_context_events_time
            ON ai_context_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_context_events_entity
            ON ai_context_events(entity_type, entity_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS ai_context_sync_state (
            source_uri TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL DEFAULT '',
            cursor_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'ok',
            error TEXT NOT NULL DEFAULT '',
            last_synced_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ai_context_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_hash TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
        with closing(self._connect()) as conn, conn:
            conn.executescript(schema)

    @staticmethod
    def _is_sensitive_key(key: Any) -> bool:
        normalized = re.sub(r"[^a-z0-9_]", "", str(key).lower())
        return any(part in normalized for part in SENSITIVE_KEYS)

    @classmethod
    def _redact_text(cls, value: str) -> str:
        value = _CHINESE_PASSWORD_RE.sub(
            lambda match: f"{match.group(1) or ''}密码={REDACTED}", value
        )
        value = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
        value = _SK_RE.sub(REDACTED, value)
        return _ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}={REDACTED}",
            value,
        )

    @classmethod
    def redact_sensitive(cls, value: Any) -> Any:
        """Recursively redact secrets while preserving safe boolean metadata."""
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9_]", "", str(key).lower())
                if normalized in SAFE_SENSITIVE_METADATA_KEYS and isinstance(item, bool):
                    result[key] = item
                elif cls._is_sensitive_key(key):
                    result[key] = REDACTED
                else:
                    result[key] = cls.redact_sensitive(item)
            return result
        if isinstance(value, list):
            return [cls.redact_sensitive(item) for item in value]
        if isinstance(value, tuple):
            return [cls.redact_sensitive(item) for item in value]
        if isinstance(value, str):
            return cls._redact_text(value)
        return value

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def upsert_document(
        self,
        document_id: str,
        *,
        source_type: str,
        source_uri: str,
        title: str,
        content: str,
        keywords: list[str] | None = None,
        metadata: dict | None = None,
        priority: int = 50,
    ) -> None:
        safe_content = str(self.redact_sensitive(content))
        safe_keywords = self.redact_sensitive(keywords or [])
        safe_metadata = self.redact_sensitive(metadata or {})
        content_hash = hashlib.sha256(safe_content.encode("utf-8")).hexdigest()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO ai_context_documents(
                    id, source_type, source_uri, title, content, content_hash,
                    keywords_json, metadata_json, priority, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_type=excluded.source_type,
                    source_uri=excluded.source_uri,
                    title=excluded.title,
                    content=excluded.content,
                    content_hash=excluded.content_hash,
                    keywords_json=excluded.keywords_json,
                    metadata_json=excluded.metadata_json,
                    priority=excluded.priority,
                    updated_at=excluded.updated_at
                """,
                (
                    str(document_id),
                    str(source_type),
                    str(source_uri),
                    str(self.redact_sensitive(title)),
                    safe_content,
                    content_hash,
                    self._json(safe_keywords),
                    self._json(safe_metadata),
                    max(0, min(100, int(priority))),
                    _now(),
                ),
            )

    def upsert_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        name: str,
        aliases: list[str] | None = None,
        capabilities: dict | list | None = None,
        state: dict | None = None,
        source: str = "runtime",
        enabled: bool = True,
    ) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO ai_context_entities(
                    entity_type, entity_id, name, aliases_json,
                    capabilities_json, state_json, source, enabled, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    name=excluded.name,
                    aliases_json=excluded.aliases_json,
                    capabilities_json=excluded.capabilities_json,
                    state_json=excluded.state_json,
                    source=excluded.source,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    str(entity_type),
                    str(entity_id),
                    str(self.redact_sensitive(name)),
                    self._json(self.redact_sensitive(aliases or [])),
                    self._json(self.redact_sensitive(capabilities or {})),
                    self._json(self.redact_sensitive(state or {})),
                    str(source),
                    1 if enabled else 0,
                    _now(),
                ),
            )

    def record_event(
        self,
        event_type: str,
        summary: str,
        *,
        details: dict | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        source: str = "gateway",
        severity: str = "info",
    ) -> int:
        safe_summary = str(self.redact_sensitive(summary))
        safe_details = self.redact_sensitive(details or {})
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                INSERT INTO ai_context_events(
                    event_type, entity_type, entity_id, summary,
                    details_json, source, severity, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event_type),
                    entity_type,
                    entity_id,
                    safe_summary,
                    self._json(safe_details),
                    str(source),
                    str(severity),
                    _now(),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def _stable_id(*parts: str) -> str:
        value = "\x1f".join(str(part) for part in parts)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    def collect_static_sources(self) -> dict[str, Any]:
        """Index Python symbols and heading-aware Markdown sections."""
        documents = 0
        errors: list[dict[str, str]] = []
        excluded = {".git", "__pycache__", ".pytest_cache", "baseline_backup"}

        for path in sorted(self.root_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md"}:
                continue
            try:
                relative = path.relative_to(self.root_dir).as_posix()
                if any(part in excluded for part in path.relative_to(self.root_dir).parts):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if path.suffix.lower() == ".py":
                    tree = ast.parse(text, filename=relative)
                    module_doc = ast.get_docstring(tree) or ""
                    module_content = f"Python module: {relative}\n{module_doc}".strip()
                    self.upsert_document(
                        f"python:{self._stable_id(relative, 'module')}",
                        source_type="python",
                        source_uri=relative,
                        title=relative,
                        content=module_content,
                        keywords=[path.stem, "python", "module"],
                        metadata={"symbolType": "module"},
                        priority=65,
                    )
                    documents += 1
                    for node in ast.walk(tree):
                        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                            continue
                        symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
                        signature = ast.get_source_segment(text, node)
                        if signature:
                            signature = signature.splitlines()[0]
                        content = "\n".join(
                            item
                            for item in (
                                f"{symbol_type}: {node.name}",
                                f"source: {relative}:{getattr(node, 'lineno', 1)}",
                                signature or "",
                                ast.get_docstring(node) or "",
                            )
                            if item
                        )
                        self.upsert_document(
                            f"python:{self._stable_id(relative, symbol_type, node.name, str(getattr(node, 'lineno', 1)))}",
                            source_type="python_symbol",
                            source_uri=relative,
                            title=f"{relative}::{node.name}",
                            content=content,
                            keywords=[path.stem, node.name, symbol_type],
                            metadata={
                                "symbolType": symbol_type,
                                "symbol": node.name,
                                "line": getattr(node, "lineno", 1),
                            },
                            priority=70,
                        )
                        documents += 1
                else:
                    sections: list[tuple[str, str]] = []
                    title = path.name
                    buffer: list[str] = []
                    for line in text.splitlines():
                        if line.lstrip().startswith("#"):
                            if buffer:
                                sections.append((title, "\n".join(buffer).strip()))
                            title = line.lstrip("# ").strip() or path.name
                            buffer = [line]
                        else:
                            buffer.append(line)
                    if buffer:
                        sections.append((title, "\n".join(buffer).strip()))
                    for index, (section_title, content) in enumerate(sections or [(path.name, text)]):
                        if not content:
                            continue
                        self.upsert_document(
                            f"markdown:{self._stable_id(relative, str(index), section_title)}",
                            source_type="markdown",
                            source_uri=relative,
                            title=f"{relative} - {section_title}",
                            content=content,
                            keywords=[path.stem, section_title],
                            metadata={"section": section_title, "sectionIndex": index},
                            priority=60,
                        )
                        documents += 1
            except (OSError, SyntaxError, UnicodeError) as exc:
                errors.append({"source": str(path), "error": str(exc)})
        return {"documents": documents, "errors": errors}

    def collect_database_state(self) -> dict[str, int]:
        """Mirror current domain tables into normalized context entities."""
        table_map = {"devices": "device", "sensors": "sensor", "scenes": "scene"}
        counts = {table: 0 for table in table_map}
        counts["device_registry"] = 0
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            existing = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table, entity_type in table_map.items():
                if table not in existing:
                    continue
                rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
                for index, row in enumerate(rows):
                    data = dict(row)
                    entity_id = data.get("id") or data.get(f"{entity_type}_id") or str(index)
                    name = data.get("name") or str(entity_id)
                    aliases = [
                        str(value)
                        for key in ("room", "type", "description")
                        if (value := data.get(key)) not in (None, "")
                    ]
                    capabilities = {
                        key: data[key]
                        for key in ("type", "protocol", "unit")
                        if key in data and data[key] is not None
                    }
                    self.upsert_entity(
                        entity_type,
                        str(entity_id),
                        name=str(name),
                        aliases=aliases,
                        capabilities=capabilities,
                        state=data,
                        source=f"database:{table}",
                        enabled=bool(data.get("enabled", data.get("is_enabled", 1))),
                    )
                    counts[table] += 1
            if "device_registry" in existing:
                for row in conn.execute(
                    "SELECT device_id, template_json FROM device_registry ORDER BY device_id"
                ):
                    try:
                        template = json.loads(row["template_json"])
                    except (TypeError, ValueError):
                        continue
                    entity_id = str(template.get("id") or row["device_id"])
                    self.upsert_entity(
                        "device",
                        entity_id,
                        name=str(template.get("name") or entity_id),
                        aliases=template.get("aliases") or [],
                        capabilities=template.get("capabilities") or [],
                        state={
                            "type": template.get("type", "custom"),
                            "room": template.get("room", ""),
                            "custom": True,
                            "linkageTriggers": template.get("linkage_triggers", []),
                        },
                        source="database:device_registry",
                        enabled=True,
                    )
                    counts["device_registry"] += 1
        return counts

    def _read_sync_cursor(self, source_uri: str) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT cursor_json FROM ai_context_sync_state WHERE source_uri=?",
                (source_uri,),
            ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return {}

    def _write_sync_cursor(self, source_uri: str, cursor: dict[str, Any]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO ai_context_sync_state(
                    source_uri, content_hash, cursor_json, status, error, last_synced_at
                ) VALUES(?, '', ?, 'ok', '', ?)
                ON CONFLICT(source_uri) DO UPDATE SET
                    cursor_json=excluded.cursor_json,
                    status='ok', error='', last_synced_at=excluded.last_synced_at
                """,
                (source_uri, self._json(cursor), _now()),
            )

    def ingest_log(self, path: str | Path, source: str) -> int:
        """Ingest only newly appended log bytes and persist a durable cursor."""
        log_path = Path(path)
        source_uri = f"log:{log_path.resolve()}"
        cursor = self._read_sync_cursor(source_uri)
        size = log_path.stat().st_size
        offset = int(cursor.get("offset", 0) or 0)
        if offset < 0 or offset > size:
            offset = 0
        with log_path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read()
        lines = payload.decode("utf-8", errors="replace").splitlines()
        nonempty_lines = [line.strip() for line in lines if line.strip()]
        if nonempty_lines:
            created_at = _now()
            details_json = self._json(self.redact_sensitive({"path": str(log_path)}))
            rows = [
                (
                    "log", None, None,
                    str(self.redact_sensitive(line)), details_json,
                    str(source), "info", created_at,
                )
                for line in nonempty_lines
            ]
            with closing(self._connect()) as conn, conn:
                conn.executemany(
                    """
                    INSERT INTO ai_context_events(
                        event_type, entity_type, entity_id, summary,
                        details_json, source, severity, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        self._write_sync_cursor(source_uri, {"offset": size, "size": size})
        return len(nonempty_lines)

    @staticmethod
    def _loads(value: str, fallback: Any) -> Any:
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    def rebuild_snapshot(self) -> dict[str, Any]:
        """Build a redacted machine-readable context snapshot using atomic replace."""
        entity_groups: dict[str, list[dict[str, Any]]] = {
            "device": [], "sensor": [], "scene": [], "api": [],
            "capability": [], "rule": [], "mcp_tool": [],
        }
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                "SELECT * FROM ai_context_entities WHERE enabled=1 ORDER BY entity_type, name"
            ):
                item = {
                    "id": row["entity_id"],
                    "name": row["name"],
                    "aliases": self._loads(row["aliases_json"], []),
                    "capabilities": self._loads(row["capabilities_json"], {}),
                    "state": self._loads(row["state_json"], {}),
                    "source": row["source"],
                    "updatedAt": row["updated_at"],
                }
                entity_groups.setdefault(row["entity_type"], []).append(item)
            documentation = [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "source": row["source_uri"],
                    "type": row["source_type"],
                    "priority": row["priority"],
                    "updatedAt": row["updated_at"],
                }
                for row in conn.execute(
                    "SELECT id,title,source_uri,source_type,priority,updated_at "
                    "FROM ai_context_documents ORDER BY priority DESC, updated_at DESC"
                )
            ]
            recent = [
                {
                    "id": row["id"], "type": row["event_type"],
                    "entityType": row["entity_type"], "entityId": row["entity_id"],
                    "summary": row["summary"],
                    "details": self._loads(row["details_json"], {}),
                    "source": row["source"], "severity": row["severity"],
                    "createdAt": row["created_at"],
                }
                for row in conn.execute(
                    "SELECT * FROM ai_context_events ORDER BY id DESC LIMIT 100"
                )
            ]
            stats = {
                "documents": conn.execute("SELECT COUNT(*) FROM ai_context_documents").fetchone()[0],
                "entities": conn.execute("SELECT COUNT(*) FROM ai_context_entities").fetchone()[0],
                "events": conn.execute("SELECT COUNT(*) FROM ai_context_events").fetchone()[0],
            }

        snapshot = self.redact_sensitive(
            {
                "schemaVersion": "1.0",
                "generatedAt": _now(),
                "project": {"name": "A9 smart home backend", "root": str(self.root_dir)},
                "runtime": {"contextMaxChars": self.max_chars},
                "capabilities": entity_groups.get("capability", []),
                "devices": entity_groups.get("device", []),
                "sensors": entity_groups.get("sensor", []),
                "scenes": entity_groups.get("scene", []),
                "automations": entity_groups.get("rule", []),
                "apis": entity_groups.get("api", []),
                "mcpTools": entity_groups.get("mcp_tool", []),
                "protocols": [],
                "safety": {
                    "doorPasswordRequiredEveryCall": True,
                    "doorPasswordPersisted": False,
                    "radarPresenceEnabled": True,
                },
                "documentation": documentation,
                "recentActivity": recent,
                "collectionStats": stats,
            }
        )
        serialized = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
        temp_path = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self.snapshot_path)
        snapshot_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO ai_context_snapshots(snapshot_hash,summary_json,created_at) VALUES(?,?,?)",
                (snapshot_hash, self._json(snapshot["collectionStats"]), _now()),
            )
            conn.execute(
                "DELETE FROM ai_context_snapshots WHERE id NOT IN "
                "(SELECT id FROM ai_context_snapshots ORDER BY id DESC LIMIT 20)"
            )
        return snapshot

    @staticmethod
    def _normalize_search_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value).lower()).strip()

    @classmethod
    def _search_terms(cls, value: str) -> set[str]:
        normalized = cls._normalize_search_text(value)
        terms = set(re.findall(r"[a-z0-9_./:-]+", normalized))
        for sequence in re.findall(r"[\u3400-\u9fff]+", normalized):
            terms.add(sequence)
            terms.update(sequence[index : index + 2] for index in range(max(0, len(sequence) - 1)))
        return {term for term in terms if term}

    @classmethod
    def is_opening_greeting(cls, text: str, is_first_turn: bool) -> bool:
        """Return true only for a first-turn greeting with no substantive request."""
        if not is_first_turn:
            return False
        normalized = re.sub(r"[\s，。！？,.!?、~～]+", "", str(text).lower())
        greetings = {
            "", "你好", "您好", "嗨", "哈喽", "hello", "hi", "早上好",
            "下午好", "晚上好", "在吗", "开始", "开始吧",
        }
        return normalized in greetings

    @classmethod
    def _score_text(cls, query: str, searchable: str) -> float:
        query_normalized = cls._normalize_search_text(query)
        searchable_normalized = cls._normalize_search_text(searchable)
        if not query_normalized or not searchable_normalized:
            return 0.0
        score = 0.0
        if query_normalized == searchable_normalized:
            score += 500.0
        elif query_normalized in searchable_normalized:
            score += 120.0
        overlap = cls._search_terms(query) & cls._search_terms(searchable)
        score += len(overlap) * 20.0
        score += sum(min(30.0, len(term) * 3.0) for term in overlap)
        return score

    def search(self, query: str, limit: int = 40, event_limit: int = 60) -> list[dict[str, Any]]:
        """Search entities, recent events, and indexed sources with deterministic scoring."""
        query_normalized = self._normalize_search_text(query)
        hits: list[dict[str, Any]] = []
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                "SELECT * FROM ai_context_entities WHERE enabled=1 ORDER BY updated_at DESC"
            ):
                aliases = self._loads(row["aliases_json"], [])
                capabilities = self._loads(row["capabilities_json"], {})
                state = self._loads(row["state_json"], {})
                searchable = self._json(
                    {
                        "id": row["entity_id"], "name": row["name"],
                        "aliases": aliases, "capabilities": capabilities, "state": state,
                    }
                )
                score = self._score_text(query, searchable) + 35.0
                if row["entity_id"].lower() in query_normalized:
                    score += 1_000.0
                if self._normalize_search_text(row["name"]) in query_normalized:
                    score += 800.0
                if any(self._normalize_search_text(alias) in query_normalized for alias in aliases if alias):
                    score += 700.0
                if score > 35.0:
                    hits.append(
                        {
                            "kind": "entity", "score": score,
                            "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                            "title": row["name"], "content": searchable,
                            "source": row["source"], "updated_at": row["updated_at"],
                        }
                    )

            recent_rows = conn.execute(
                "SELECT * FROM ai_context_events ORDER BY id DESC LIMIT ?",
                (max(1, min(1_000, int(event_limit))),),
            ).fetchall()
            event_rows = list(recent_rows)
            seen_event_ids = {row["id"] for row in event_rows}
            search_terms = sorted(
                (term for term in self._search_terms(query) if len(term) >= 2),
                key=lambda term: (-len(term), term),
            )[:6]
            if search_terms:
                clauses = []
                params: list[Any] = []
                for term in search_terms:
                    clauses.append("(summary LIKE ? OR details_json LIKE ? OR COALESCE(entity_id,'') LIKE ?)")
                    pattern = f"%{term}%"
                    params.extend((pattern, pattern, pattern))
                params.append(500)
                matched_rows = conn.execute(
                    "SELECT * FROM ai_context_events WHERE " + " OR ".join(clauses) +
                    " ORDER BY id DESC LIMIT ?",
                    params,
                ).fetchall()
                event_rows.extend(row for row in matched_rows if row["id"] not in seen_event_ids)
            for recency_index, row in enumerate(event_rows):
                details = self._loads(row["details_json"], {})
                searchable = self._json(
                    {
                        "summary": row["summary"], "details": details,
                        "entityId": row["entity_id"], "type": row["event_type"],
                    }
                )
                score = self._score_text(query, searchable) + max(0.0, 50.0 - recency_index)
                if row["entity_id"] and str(row["entity_id"]).lower() in query_normalized:
                    score += 1_000.0
                if row["severity"] in {"error", "critical", "warning"}:
                    score += 80.0
                if score > max(0.0, 50.0 - recency_index):
                    hits.append(
                        {
                            "kind": "event", "score": score,
                            "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                            "title": row["summary"], "content": searchable,
                            "source": row["source"], "updated_at": row["created_at"],
                        }
                    )

            history_tables = {
                "device_operations": ("device_id", ["device_id", "action", "params_json", "result", "source", "scene_id", "created_at"]),
                "sensor_readings": ("sensor_id", ["sensor_id", "value", "unit", "created_at"]),
                "chat_history": (None, ["role", "content", "intent_json", "emotion", "source", "created_at"]),
                "conversation_memory": (None, ["role", "content", "summary", "created_at"]),
                "linkage_log": ("rule_key", ["rule_key", "trigger_event", "action_taken", "result", "detail_json", "created_at"]),
                "security_events": (None, ["rule_id", "severity", "category", "input_text", "matched_text", "reason", "source", "created_at"]),
                "remote_access_log": (None, ["client_id", "endpoint", "method", "ip_address", "status_code", "created_at"]),
                "memory_store": (None, ["namespace", "key", "value", "content", "created_at", "updated_at"]),
                "push_history": (None, ["title", "message", "content", "status", "created_at"]),
                "scheduled_tasks": (None, ["name", "description", "action_json", "status", "created_at"]),
                "guard_incidents": ("id", ["id", "signature", "rule_key", "room", "guard_level", "mode", "evidence_json", "planned_actions_json", "executed_actions_json", "status", "created_at", "resolved_at"]),
                "guard_feedback": ("incident_id", ["incident_id", "score", "better_action", "notes", "created_at", "updated_at"]),
                "guard_learning": ("signature", ["signature", "sample_count", "average_score", "guidance", "updated_at"]),
                "app_telemetry_events": (None, ["event_type", "page", "action", "result", "metadata_json", "created_at"]),
            }
            existing_tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table, (entity_column, desired_columns) in history_tables.items():
                if table not in existing_tables or not search_terms:
                    continue
                actual_columns = {
                    row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
                }
                selected_columns = [column for column in desired_columns if column in actual_columns]
                if not selected_columns:
                    continue
                clauses = []
                params = []
                for term in search_terms:
                    pattern = f"%{term}%"
                    for column in selected_columns:
                        clauses.append(f'CAST("{column}" AS TEXT) LIKE ?')
                        params.append(pattern)
                order_column = "id" if "id" in actual_columns else "rowid"
                sql = (
                    f'SELECT {", ".join(f"\"{column}\"" for column in selected_columns)} '
                    f'FROM "{table}" WHERE {" OR ".join(clauses)} '
                    f'ORDER BY "{order_column}" DESC LIMIT 100'
                )
                for history_row in conn.execute(sql, params):
                    data = dict(zip(selected_columns, history_row))
                    safe_data = self.redact_sensitive(data)
                    content = self._json(safe_data)
                    score = self._score_text(query, content) + 25.0
                    entity_id = str(data.get(entity_column)) if entity_column and data.get(entity_column) is not None else None
                    if entity_id and entity_id.lower() in query_normalized:
                        score += 1_000.0
                    hits.append(
                        {
                            "kind": "history", "score": score,
                            "table": table,
                            "entity_type": table, "entity_id": entity_id,
                            "title": f"{table} history", "content": content,
                            "source": f"database:{table}",
                            "updated_at": data.get("created_at") or data.get("updated_at"),
                        }
                    )

            for row in conn.execute(
                "SELECT * FROM ai_context_documents ORDER BY priority DESC, updated_at DESC"
            ):
                searchable = "\n".join(
                    (row["title"], row["content"], row["keywords_json"], row["source_uri"])
                )
                score = self._score_text(query, searchable) + float(row["priority"]) / 10.0
                if score > float(row["priority"]) / 10.0:
                    hits.append(
                        {
                            "kind": "document", "score": score,
                            "entity_type": None, "entity_id": None,
                            "title": row["title"], "content": row["content"],
                            "source": row["source_uri"], "updated_at": row["updated_at"],
                            "content_hash": row["content_hash"],
                        }
                    )

        kind_order = {"entity": 0, "event": 1, "history": 2, "document": 3}
        hits.sort(
            key=lambda item: (
                -item["score"], kind_order.get(item["kind"], 9),
                str(item.get("entity_id") or ""), str(item.get("title") or ""),
            )
        )
        deduplicated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            identity = hit.get("content_hash") or hashlib.sha256(
                str(hit.get("content", "")).encode("utf-8")
            ).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            deduplicated.append(hit)
            if len(deduplicated) >= max(1, int(limit)):
                break
        return deduplicated

    def build_prompt_context(
        self,
        query: str,
        *,
        is_first_turn: bool,
        live_state: dict | None = None,
    ) -> str:
        """Pack matched knowledge and live state into a bounded AI context block."""
        if self.is_opening_greeting(query, is_first_turn):
            return ""
        hits = self.search(query)
        snapshot_core: dict[str, Any] = {}
        if self.snapshot_path.exists():
            try:
                snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                snapshot_core = {
                    "generatedAt": snapshot.get("generatedAt"),
                    "collectionStats": snapshot.get("collectionStats", {}),
                    "safety": snapshot.get("safety", {}),
                    "capabilities": [
                        {"id": item.get("id"), "name": item.get("name")}
                        for item in snapshot.get("capabilities", [])
                    ],
                    "mcpTools": [item.get("id") or item.get("name") for item in snapshot.get("mcpTools", [])],
                }
            except (OSError, ValueError, TypeError):
                snapshot_core = {}
        sections = [
            "[A9 超级上下文｜由服务端自动注入]",
            "使用规则：优先匹配下列实时实体、操作记录和项目资料；不确定时调用工具查询，禁止编造设备状态。",
            "安全边界：门锁开门/关门每次都必须由用户在该次请求中手工提供密码；不得从环境变量、历史、日志或上下文补取密码，也不得保存或回显密码。毫米波人体存在开关与雷达灯光联动开关相互独立。",
            "可调用工具：search_context、get_project_overview、get_context_stats、get_live_status、list_devices、get_device、list_sensors、get_recent_operations、get_recent_logs、get_linkage_config、get_radar_config、list_capabilities、toggle_device、control_device、activate_scene、set_linkage_config、set_radar_enabled、register_device、unregister_device、register_capability、invoke_capability、rebuild_context、door_control。",
        ]
        if snapshot_core:
            sections.append("每轮已读取 project_context.json 核心目录：\n" + self._json(snapshot_core))
        if live_state:
            sections.append(
                "实时状态：\n" + self._json(self.redact_sensitive(live_state))
            )
        if hits:
            sections.append("相关匹配：")
        for hit in hits:
            sections.append(
                self._json(
                    self.redact_sensitive(
                        {
                            "kind": hit["kind"], "score": round(hit["score"], 2),
                            "entityType": hit.get("entity_type"),
                            "entityId": hit.get("entity_id"), "title": hit.get("title"),
                            "source": hit.get("source"), "content": hit.get("content"),
                            "updatedAt": hit.get("updated_at"),
                        }
                    )
                )
            )
        sections.append("[A9 超级上下文结束]")
        packed = "\n\n".join(sections)
        if len(packed) <= self.max_chars:
            return packed
        closing = "\n\n[A9 超级上下文因长度上限截断；完整资料可通过 context.search/context.snapshot 继续读取]\n[A9 超级上下文结束]"
        return packed[: max(0, self.max_chars - len(closing))] + closing
