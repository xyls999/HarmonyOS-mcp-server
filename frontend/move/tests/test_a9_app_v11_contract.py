from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class A9AppV11ContractTest(unittest.TestCase):
    def test_app_uses_public_app_route_and_jwt_auth(self) -> None:
        http = source("entry/src/main/ets/api/http.ets")
        auth = source("entry/src/main/ets/api/authApi.ets")
        all_api = "\n".join(
            source(str(path.relative_to(ROOT)))
            for path in (ROOT / "entry/src/main/ets/api").glob("*.ets")
        )
        self.assertIn("static readonly BASE: string = 'http://yuanzhe.tech'", http)
        self.assertIn("/api/app/auth/login", auth)
        self.assertIn("/api/app/auth/refresh", http)
        self.assertNotIn("/d6/", all_api)
        self.assertNotIn("X-API-Key", all_api)

    def test_protected_writes_are_signed(self) -> None:
        signer = source("entry/src/main/ets/api/requestSigner.ets")
        http = source("entry/src/main/ets/api/http.ets")
        self.assertIn("X-App-Timestamp", signer)
        self.assertIn("X-App-Nonce", signer)
        self.assertIn("X-App-Signature", signer)
        self.assertIn("RequestSigner.headers", http)
        self.assertIn("bodyText", http)

    def test_chat_uses_120_second_read_timeout(self) -> None:
        chat = source("entry/src/main/ets/api/chatApi.ets")
        http = source("entry/src/main/ets/api/http.ets")
        self.assertIn("Http.CHAT_TIMEOUT", chat)
        self.assertIn("postResult('/api/app/chat/send', body, true, Http.CHAT_TIMEOUT)", chat)
        self.assertIn("Http.rawRequest(path, method, body, protectedPath, timeout)", http)
        self.assertIn("Http.rawRequest(path, method, body, true, timeout)", http)

    def test_chat_syncs_history_actions_and_feedback_ui(self) -> None:
        chat = source("entry/src/main/ets/api/chatApi.ets")
        page = source("entry/src/main/ets/pages/ChatPage.ets")
        bubble = source("entry/src/main/ets/components/ChatBubble.ets")
        self.assertIn("/api/app/ai/context", chat)
        self.assertIn("execution", chat)
        self.assertIn("actions", bubble)
        self.assertIn("feedbackDialog", page)
        self.assertIn("DeviceApi.syncAssistantActions", page)

    def test_device_control_body_is_flat(self) -> None:
        device = source("entry/src/main/ets/api/deviceApi.ets")
        self.assertIn("fan_speed", device)
        self.assertIn("body.temperature", device)
        self.assertIn("body.mode", device)
        self.assertNotIn("params: params", device)

    def test_successful_device_actions_survive_stale_refreshes(self) -> None:
        device = source("entry/src/main/ets/api/deviceApi.ets")
        self.assertIn("stateOverrides", device)
        self.assertIn("DeviceApi.rememberState", device)
        self.assertIn("DeviceApi.applyOverride", device)
        self.assertIn(".map((item: Json): Device => DeviceApi.applyOverride(normalizeDevice(item)))", device)

    def test_home_has_no_scene_shortcuts_or_online_rate(self) -> None:
        home = source("entry/src/main/ets/pages/HomePage.ets")
        self.assertNotIn("SceneApi", home)
        self.assertNotIn("回家", home)
        self.assertNotIn("离家", home)
        self.assertNotIn("睡眠", home)
        self.assertNotIn("在线率", home)

    def test_living_room_ambient_light_is_hidden(self) -> None:
        device_api = source("entry/src/main/ets/api/deviceApi.ets")
        self.assertNotIn("offlineDevice('light_05'", device_api)
        self.assertIn("device.id !== 'light_05'", device_api)

    def test_records_include_alerts_and_security_events(self) -> None:
        history = source("entry/src/main/ets/pages/HistoryPage.ets")
        api = source("entry/src/main/ets/api/v5Api.ets")
        self.assertIn("getAlerts", history)
        self.assertIn("getSecurityEvents", history)
        self.assertIn("/api/app/security/events", api)


if __name__ == "__main__":
    unittest.main()
