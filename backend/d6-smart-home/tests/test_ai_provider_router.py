import json
import unittest
from urllib.error import HTTPError

try:
    from ai_provider_router import ProviderRouter, contains_multimodal_content, extract_text_content
except ImportError:
    ProviderRouter = None
    contains_multimodal_content = None
    extract_text_content = None


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ProviderRouterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ProviderRouter)
        self.models = {
            "deepseek": {"url": "https://deepseek.invalid/chat/completions", "key": "d", "model": "deepseek-chat"},
            "astron": {"url": "https://astron.invalid/chat/completions", "key": "a", "model": "astron"},
            "iflytek": {"url": "https://iflytek.invalid/chat/completions", "key": "i", "model": "vision"},
            "codex": {"url": "https://codex.invalid/responses", "key": "c", "model": "gpt-test", "wireApi": "responses"},
        }

    def test_text_prefers_deepseek(self):
        calls = []

        def opener(request, **_kwargs):
            calls.append(request.full_url)
            return FakeResponse({"choices": [{"message": {"content": "deepseek-ok"}}]})

        router = ProviderRouter(self.models, opener=opener)
        result = router.complete([{"role": "user", "content": "hello"}])
        self.assertEqual(result.text, "deepseek-ok")
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(calls, [self.models["deepseek"]["url"]])

    def test_multimodal_prefers_iflytek(self):
        calls = []
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "看图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
        ]}]

        def opener(request, **_kwargs):
            calls.append(request.full_url)
            return FakeResponse({"choices": [{"message": {"content": "iflytek-ok"}}]})

        self.assertTrue(contains_multimodal_content(messages))
        router = ProviderRouter(self.models, opener=opener)
        result = router.complete(messages)
        self.assertEqual(result.provider, "iflytek")
        self.assertEqual(calls, [self.models["iflytek"]["url"]])

    def test_text_extraction_ignores_binary_multimodal_payloads(self):
        content = [
            {"type": "text", "text": "识别这个面板"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,SECRET_BINARY"}},
        ]
        self.assertEqual(extract_text_content(content), "识别这个面板")

    def test_text_failover_ends_with_codex_responses(self):
        calls = []

        def opener(request, **_kwargs):
            calls.append((request.full_url, json.loads(request.data.decode("utf-8"))))
            if request.full_url != self.models["codex"]["url"]:
                raise HTTPError(request.full_url, 503, "unavailable", {}, None)
            return FakeResponse({"output": [{"type": "message", "content": [{"type": "output_text", "text": "codex-ok"}]}]})

        router = ProviderRouter(self.models, opener=opener)
        result = router.complete([{"role": "user", "content": "hello"}])
        self.assertEqual(result.text, "codex-ok")
        self.assertEqual(result.provider, "codex")
        self.assertEqual([url for url, _ in calls], [
            self.models["deepseek"]["url"], self.models["astron"]["url"],
            self.models["iflytek"]["url"], self.models["codex"]["url"],
        ])
        self.assertIn("input", calls[-1][1])
        self.assertNotIn("messages", calls[-1][1])

    def test_multimodal_failover_skips_text_only_providers(self):
        calls = []

        def opener(request, **_kwargs):
            calls.append(request.full_url)
            if "iflytek" in request.full_url:
                raise HTTPError(request.full_url, 500, "failed", {}, None)
            return FakeResponse({"output_text": "codex-vision-ok"})

        router = ProviderRouter(self.models, opener=opener)
        result = router.complete([{"role": "user", "content": [{"type": "input_image", "image_url": "data:image/png;base64,AA=="}]}])
        self.assertEqual(result.provider, "codex")
        self.assertEqual(calls, [self.models["iflytek"]["url"], self.models["codex"]["url"]])

    def test_missing_keys_are_skipped_without_leaking_them(self):
        models = {name: dict(cfg) for name, cfg in self.models.items()}
        models["deepseek"]["key"] = ""
        calls = []

        def opener(request, **_kwargs):
            calls.append(request.full_url)
            return FakeResponse({"choices": [{"message": {"content": "astron-ok"}}]})

        result = ProviderRouter(models, opener=opener).complete([{"role": "user", "content": "hello"}])
        self.assertEqual(result.provider, "astron")
        self.assertEqual(calls, [models["astron"]["url"]])
        self.assertNotIn("key", result.errors)


if __name__ == "__main__":
    unittest.main()
