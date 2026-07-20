import importlib.util
import pathlib
import sys
import unittest
import json


ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTER = ROOT / "backend" / "d6" / "ai_provider_router.py"
GATEWAY = ROOT / "backend" / "d6" / "gateway_v6.py"


class AiProviderRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ai_provider_router_contract", ROUTER)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def test_text_and_multimodal_routes_match_product_contract(self):
        self.assertEqual(self.module.TEXT_CHAIN, ("deepseek", "codex"))
        self.assertEqual(self.module.MULTIMODAL_CHAIN, ("iflytek", "codex"))
        self.assertFalse(self.module.contains_multimodal_content([
            {"role": "user", "content": "检查家庭状态"}
        ]))
        self.assertTrue(self.module.contains_multimodal_content([
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}
        ]))

    def test_gateway_exposes_local_sanitized_ai_and_tts_status(self):
        source = GATEWAY.read_text(encoding="utf-8")
        self.assertIn("def _public_ai_config", source)
        self.assertIn("def _public_tts_config", source)
        ai_route = source.split('elif p == "/api/ai/config":', 1)[1].split("else:", 1)[0]
        tts_route = source.split('elif p == "/api/tts/config":', 1)[1].split("elif", 1)[0]
        self.assertIn("_public_ai_config()", ai_route)
        self.assertIn("_public_tts_config()", tts_route)
        self.assertNotIn("127.0.0.1:8081", ai_route)
        self.assertNotIn("127.0.0.1:8081", tts_route)

    def test_keyless_offline_provider_can_be_selected_first(self):
        opened = []

        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self):
                return json.dumps({"choices": [{"message": {"content": "离线回复"}}]}).encode()

        def opener(request, **_):
            opened.append(request)
            return Response()

        router = self.module.ProviderRouter({
            "offline": {
                "url": "http://192.168.1.11:8080/v1/chat/completions",
                "model": "local-model", "requiresKey": False,
            }
        }, opener=opener)
        result = router.complete([{"role": "user", "content": "你好"}], preferred_provider="offline")
        self.assertEqual(result.provider, "offline")
        self.assertEqual(result.text, "离线回复")
        self.assertNotIn("Authorization", opened[0].headers)


if __name__ == "__main__":
    unittest.main()
