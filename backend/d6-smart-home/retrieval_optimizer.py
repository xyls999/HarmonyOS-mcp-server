"""Deterministic hybrid retrieval for the D6 assistant.

This is intentionally dependency-free.  It fuses the static command RAG and
the persistent ContextEngine without pretending that TF-IDF is an embedding
model.  A future embedding provider can be added as another ranked source.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any


class HybridRetriever:
    """Fuse static RAG and long-term SQLite context with rank-based scoring."""

    _ALIASES = {
        "灯": "灯光 客厅主灯 厨房灯 卧室灯 卫生间灯",
        "空调": "客厅空调 制冷 除湿 温度",
        "门": "门禁 开门 关门 解锁 锁门",
        "换气": "换气扇 排风扇 卫生间",
        "温度": "客厅温度 室内温度 热敏",
        "湿度": "客厅湿度 室内湿度",
        "无人": "毫米波 存在感知 人体感应",
    }

    def __init__(self, cache_ttl: float = 3.0) -> None:
        self.cache_ttl = max(0.0, float(cache_ttl))
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    @classmethod
    def expand_query(cls, query: str) -> str:
        text = " ".join(str(query or "").split()).strip()
        if not text:
            return ""
        additions = [value for key, value in cls._ALIASES.items() if key in text]
        return f"{text} {' '.join(additions)}".strip()

    @staticmethod
    def _identity(hit: dict[str, Any]) -> str:
        entity = str(hit.get("entity_id") or hit.get("entityId") or "")
        if entity:
            return f"entity:{entity}"
        title = str(hit.get("title") or "")
        content = str(hit.get("content") or hit.get("text") or "")
        return hashlib.sha1(f"{entity}|{title}|{content}".encode("utf-8")).hexdigest()

    def retrieve(self, query: str, *, rag: Any = None, context_engine: Any = None,
                 knowledge: Any = None, available_devices: dict[str, Any] | None = None,
                 limit: int = 12) -> list[dict[str, Any]]:
        original = " ".join(str(query or "").split()).strip()
        if not original:
            return []
        safe_limit = max(1, min(40, int(limit)))
        cache_key = f"{original}|{safe_limit}"
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] <= self.cache_ttl:
            return [dict(item) for item in cached[1]]

        expanded = self.expand_query(original)
        fused: dict[str, dict[str, Any]] = {}

        def add(hit: dict[str, Any], source: str, rank: int) -> None:
            item = dict(hit)
            identity = self._identity(item)
            rrf = 1.0 / (60.0 + rank)
            existing = fused.get(identity)
            if existing is None:
                # Source scores use different scales (TF-IDF vs. SQLite lexical
                # scores), so only rank contributes to fusion; raw scores never
                # let one backend drown out the other.
                item["score"] = rrf * 100.0
                item["retrieval"] = "hybrid"
                item["retrievalSources"] = [source]
                fused[identity] = item
            else:
                existing["score"] = float(existing.get("score") or 0.0) + rrf * 100.0
                sources = existing.setdefault("retrievalSources", [])
                if source not in sources:
                    sources.append(source)

        if rag is not None:
            try:
                rag_hits = rag.search(original, n=12)
                if expanded != original:
                    rag_hits = list(rag_hits) + list(rag.search(expanded, n=8))
                for rank, hit in enumerate(rag_hits, 1):
                    add({
                        "kind": "rag",
                        "title": hit.get("meta", {}).get("name") or hit.get("category", "知识匹配"),
                        "content": hit.get("text", ""),
                        "entity_id": hit.get("meta", {}).get("device") or hit.get("meta", {}).get("sensor"),
                        "source": "static_rag",
                        "category": hit.get("category"),
                        "meta": hit.get("meta", {}),
                        "score": hit.get("score", 0),
                    }, "rag", rank)
            except Exception:
                pass

        if context_engine is not None:
            try:
                context_hits = context_engine.search(original, limit=24, event_limit=40)
                for rank, hit in enumerate(context_hits, 1):
                    add(hit, "long_term_context", rank)
            except Exception:
                pass

        if knowledge is not None:
            try:
                knowledge_hits = knowledge.search(
                    expanded, available_devices=available_devices or {}, limit=24,
                )
                for rank, hit in enumerate(knowledge_hits, 1):
                    add({
                        "kind": "device_solution",
                        "title": hit.get("meta", {}).get("deviceName") or "设备处理策略",
                        "content": hit.get("text", ""),
                        "entity_id": hit.get("meta", {}).get("deviceId") or hit.get("meta", {}).get("family"),
                        "source": hit.get("source", {}),
                        "category": "device_solution",
                        "meta": hit.get("meta", {}),
                    }, "device_solution_knowledge", rank)
            except Exception:
                pass

        ordered = sorted(
            fused.values(),
            key=lambda item: (-float(item.get("score") or 0.0), str(item.get("title") or "")),
        )
        results = ordered[:safe_limit]
        # Keep the hybrid contract visible: if both backends returned hits, do
        # not let a large event table crowd every static capability out.
        for source in ("rag", "long_term_context", "device_solution_knowledge"):
            if any(source in item.get("retrievalSources", []) for item in results):
                continue
            replacement = next((item for item in ordered
                                if source in item.get("retrievalSources", [])), None)
            if replacement is not None and results:
                results[-1] = replacement
                results.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("title") or "")))
        self._cache[cache_key] = (time.monotonic(), [dict(item) for item in results])
        if len(self._cache) > 64:
            oldest = sorted(self._cache, key=lambda key: self._cache[key][0])[:16]
            for key in oldest:
                self._cache.pop(key, None)
        return results
