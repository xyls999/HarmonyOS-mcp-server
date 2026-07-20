import inspect
import unittest

from backend.d6.retrieval_optimizer import HybridRetriever


class _Rag:
    def search(self, query, n=5):
        return [{"text": "打开客厅空调 制冷", "category": "device_control",
                 "meta": {"device": "ac_01", "action": "on"}, "score": 4.0}]


class _Context:
    def search(self, query, limit=40, event_limit=60):
        return [{"kind": "event", "title": "客厅空调最近关闭",
                 "content": "设备操作 ac_01", "entity_id": "ac_01", "score": 80.0}]


class HybridRetrieverTests(unittest.TestCase):
    def test_retriever_accepts_source_device_solution_knowledge(self):
        parameters = inspect.signature(HybridRetriever.retrieve).parameters
        self.assertIn("knowledge", parameters)

    def test_fuses_static_rag_and_long_term_context_without_losing_sources(self):
        hits = HybridRetriever(cache_ttl=0).retrieve("打开空调", rag=_Rag(), context_engine=_Context(), limit=8)
        self.assertTrue(hits)
        self.assertIn("rag", hits[0]["retrievalSources"])
        self.assertIn("long_term_context", hits[0]["retrievalSources"])
        self.assertEqual(hits[0]["retrieval"], "hybrid")

    def test_expands_device_terms_but_does_not_invent_scene_names(self):
        expanded = HybridRetriever.expand_query("空调太热")
        self.assertIn("制冷", expanded)
        self.assertNotIn("睡眠模式", expanded)


if __name__ == "__main__":
    unittest.main()
