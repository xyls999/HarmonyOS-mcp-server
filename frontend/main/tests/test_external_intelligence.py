import os
import tempfile
import unittest

from backend.d6.external_intelligence import ExternalIntelligenceCollector


class ExternalIntelligenceTests(unittest.TestCase):
    def test_location_is_auto_resolved_from_chinese_provider_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def location_fetch(url, _timeout):
                calls.append(url)
                return {"pro": "上海", "city": "上海市", "addr": "上海市"}

            collector = ExternalIntelligenceCollector(
                os.path.join(directory, "x.db"), location_fetcher=location_fetch)
            config = collector.resolve_location(force=True)
            self.assertEqual(config["locationName"], "上海市")
            self.assertEqual(config["locationSource"], "太平洋电脑网")
            self.assertEqual(config["locationConfidence"], "中")
            self.assertTrue(calls)
            self.assertIn("pconline.com.cn", calls[0])

    def test_location_fallback_rejects_non_chinese_or_low_quality_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            def location_fetch(_url, _timeout):
                return {"city": "London", "country": "UK"}

            collector = ExternalIntelligenceCollector(
                os.path.join(directory, "x.db"), location_fetcher=location_fetch)
            config = collector.resolve_location(force=True)
            self.assertEqual(config["locationName"], "当前位置")
            self.assertEqual(config["locationConfidence"], "未知")

    def test_normalizes_sources_hashes_and_bounds_items(self):
        with tempfile.TemporaryDirectory() as directory:
            def fetch(_url, _timeout):
                return {"items": [
                    {"title": "A", "description": "one", "url": "https://www.chinanews.com.cn/a", "image": "https://www.chinanews.com.cn/a.jpg"},
                    {"title": "B", "description": "two", "url": "https://www.chinanews.com.cn/b"},
                ]}
            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"), fetcher=fetch, max_items=1)
            result = collector.collect_category("news")
            self.assertTrue(result["available"])
            self.assertEqual(len(result["items"]), 1)
            item = result["items"][0]
            for key in ("content_hash", "source_url", "published_at", "fetched_at", "stale"):
                self.assertIn(key, item)
            self.assertEqual(len(collector.cached("news")), 1)

    def test_provider_failure_returns_stale_cache_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            def fail(_url, _timeout):
                raise TimeoutError("offline")
            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"), fetcher=fail)
            result = collector.collect_category("traffic")
            self.assertFalse(result["available"])
            self.assertTrue(result["stale"])
            self.assertEqual(result["items"], [])

    def test_persistent_config_controls_collection_without_exposing_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def fetch(url, _timeout):
                calls.append(url)
                return {"items": [{"title": "Configured", "url": "https://www.chinanews.com.cn/configured"}]}

            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"), fetcher=fetch)
            saved = collector.update_config({
                "enabled": True,
                "latitude": 31.2,
                "longitude": 121.5,
                "locationName": "测试地点",
                "trafficUrl": "https://ditu.amap.com/traffic/trafficsearch",
                "marketSymbol": "TEST",
            })
            self.assertTrue(saved["enabled"])
            self.assertEqual(saved["locationName"], "测试地点")
            self.assertNotIn("apiKey", saved)
            collector.collect_category("traffic")
            self.assertTrue(any("ditu.amap.com/traffic" in url for url in calls))
            collector.update_config({"enabled": False})
            calls.clear()
            disabled = collector.collect()
            self.assertFalse(disabled["enabled"])
            self.assertEqual(calls, [])

    def test_rss_fallback_normalizes_title_link_summary_and_time(self):
        with tempfile.TemporaryDirectory() as directory:
            rss = """<?xml version='1.0'?><rss><channel><item>
              <title>科技动态</title><link>https://www.chinanews.com.cn/item</link>
              <description><![CDATA[摘要 <b>内容</b>]]></description><pubDate>Sat, 19 Jul 2026 04:00:00 GMT</pubDate>
              <enclosure url='https://www.chinanews.com.cn/image.jpg' type='image/jpeg'/>
            </item></channel></rss>"""
            calls = []

            def fetch(url, _timeout):
                calls.append(url)
                if "chinanews.com.cn" in url and "finance.xml" not in url:
                    raise TimeoutError("tls")
                return rss

            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"), fetcher=fetch)
            result = collector.collect_category("technology")
            self.assertTrue(result["available"])
            self.assertEqual(result["items"][0]["title"], "科技动态")
            self.assertIn("摘要", result["items"][0]["summary"])
            self.assertEqual(result["items"][0]["image_url"], "https://www.chinanews.com.cn/image.jpg")
            self.assertTrue(any("chinanews.com.cn" in url for url in calls))

    def test_default_sources_are_chinese_websites_only(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"))
            for category in ("news", "technology"):
                url = collector._provider_url(category)
                self.assertTrue(url)
                self.assertTrue(all("chinanews.com.cn" in part for part in url.split("\n")))
            self.assertEqual(collector._provider_url("weather"), "")

    def test_collect_balances_categories_so_technology_is_not_starved_by_news(self):
        with tempfile.TemporaryDirectory() as directory:
            def fetch(url, _timeout):
                category = "technology" if "tech.xml" in url else "news"
                return {"items": [{"title": f"{category}-1", "url": "https://www.chinanews.com.cn/item"}]}

            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"), fetcher=fetch, max_items=8)
            result = collector.collect()
            categories = {item["category"] for item in result["items"]}
            self.assertIn("news", categories)
            self.assertIn("technology", categories)

    def test_gateway_frontend_cannot_edit_external_location_or_source(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "entry", "src", "main", "ets", "pages", "SettingsPage.ets"), encoding="utf-8") as stream:
            settings = stream.read()
        with open(os.path.join(os.path.dirname(__file__), "..", "entry", "src", "main", "ets", "api", "assistantApi.ets"), encoding="utf-8") as stream:
            api = stream.read()
        self.assertNotIn("TextInput({ text: this.externalLocationName", settings)
        self.assertNotIn("保存外部信息配置", settings)
        self.assertNotIn("updateExternalLocation", api)

    def test_configured_external_url_rejects_non_chinese_site(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = ExternalIntelligenceCollector(os.path.join(directory, "x.db"))
            with self.assertRaises(ValueError):
                collector.update_config({"trafficUrl": "https://example.test/traffic"})


if __name__ == "__main__":
    unittest.main()
