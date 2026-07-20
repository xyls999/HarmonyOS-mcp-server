import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "backend" / "d6" / "device_solution_knowledge.py"


class DeviceSolutionKnowledgeContractTests(unittest.TestCase):
    def test_catalog_exists_and_expands_to_at_least_one_thousand_chinese_entries(self):
        self.assertTrue(MODULE.exists(), "缺少设备—异常—处理策略知识服务")
        namespace = {}
        exec(compile(MODULE.read_text("utf-8"), str(MODULE), "exec"), namespace)
        catalog = namespace["build_catalog"]()
        self.assertGreaterEqual(len(catalog), 1000)
        self.assertTrue(all(item["text"].strip() for item in catalog))
        self.assertTrue(all(item["source"]["url"].startswith("https://") for item in catalog))

    def test_retrieval_only_returns_actions_supported_by_current_devices(self):
        self.assertTrue(MODULE.exists(), "缺少设备—异常—处理策略知识服务")
        namespace = {}
        exec(compile(MODULE.read_text("utf-8"), str(MODULE), "exec"), namespace)
        service = namespace["DeviceSolutionKnowledge"]()
        hits = service.search(
            "客厅湿度超过75%，当前有人，怎样调整",
            available_devices={"ac_01": {"actions": ["dry", "cool", "off"]}},
            limit=8,
        )
        self.assertTrue(hits)
        self.assertTrue(any(hit["meta"].get("action") == "dry" for hit in hits))
        self.assertTrue(all(hit["meta"].get("deviceId") in {None, "ac_01"} for hit in hits))
        self.assertTrue(all(hit["meta"].get("action") != "unlock" for hit in hits))

    def test_gateway_exposes_bounded_knowledge_stats_and_search_interfaces(self):
        gateway = (ROOT / "backend" / "d6" / "gateway_v6.py").read_text("utf-8")
        self.assertIn('"/api/ai/knowledge/stats"', gateway)
        self.assertIn('"/api/ai/knowledge/search"', gateway)
        self.assertIn("_search_device_solutions", gateway)

    def test_live_state_query_contains_only_actionable_observations(self):
        self.assertTrue(MODULE.exists())
        namespace = {}
        exec(compile(MODULE.read_text("utf-8"), str(MODULE), "exec"), namespace)
        self.assertIn("build_state_query", namespace)
        query = namespace["build_state_query"]({
            "time": {"hour": 0, "minute": 45},
            "sensors": {
                "humid_01": {"value": 79, "online": True},
                "temp_01": {"value": 25, "online": True},
                "radar_01": {"present": False, "online": True},
                "heat_01": {"value": 21, "is_alert": True, "online": True},
            },
            "devices": {
                "ac_01": {"is_on": True, "online": True},
                "curtain_01": {"primary_value": 80, "online": True},
            },
        })
        self.assertIn("湿度达到或超过75%", query)
        self.assertIn("毫米波连续确认无人且空调仍开", query)
        self.assertIn("热敏", query)
        self.assertIn("夜间", query)
        self.assertNotIn("温度达到或超过30℃", query)
        service = namespace["DeviceSolutionKnowledge"]()
        hits = service.search(query, available_devices={
            "ac_01": {"actions": ["dry", "cool", "off"]},
            "fan_02": {"actions": ["on", "off"]},
            "curtain_01": {"actions": ["set_position"]},
            "door_01": {"actions": ["deny", "alarm", "record"]},
        }, limit=6)
        self.assertTrue(hits)
        self.assertNotIn("door_access", {hit["meta"]["family"] for hit in hits})
        self.assertIn("exhaust_fan", {hit["meta"]["family"] for hit in hits})

        heat_only_query = namespace["build_state_query"]({
            "time": {"hour": 1, "minute": 20},
            "sensors": {"heat_01": {"value": 2, "is_alert": True, "online": True}},
            "devices": {"fan_02": {"is_on": True, "online": True}},
        })
        heat_hits = service.search(heat_only_query, available_devices={
            "fan_02": {"actions": ["on", "off"]},
            "door_01": {"actions": ["deny", "alarm", "record"]},
        }, limit=6)
        self.assertNotIn("door_access", {hit["meta"]["family"] for hit in heat_hits})
        self.assertEqual(
            {hit["meta"]["condition"] for hit in heat_hits},
            {"厨房烟雾或热敏报警"},
        )


if __name__ == "__main__":
    unittest.main()
