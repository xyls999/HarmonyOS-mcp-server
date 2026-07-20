import json
import unittest

try:
    from notification_service import NotificationService
except ImportError:
    NotificationService = None


class FakeResponse:
    status = 200

    def __init__(self, payload='{"success":true}'):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload.encode("utf-8")


class NotificationServiceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(NotificationService)

    def test_qmsg_mode_sends_without_logging_secret(self):
        calls = []
        logs = []
        service = NotificationService(
            {"enabled": True, "mode": "qmsg", "qmsgKey": "TOP_SECRET_QMSG"},
            opener=lambda request, **_kwargs: calls.append(request) or FakeResponse(),
            logger=logs.append,
            clock=lambda: 1000,
        )
        self.assertTrue(service.send("door_open", "门禁打开", "门已打开"))
        self.assertIn("TOP_SECRET_QMSG", calls[0].full_url)
        self.assertNotIn("TOP_SECRET_QMSG", "\n".join(logs))

    def test_onebot_group_mode_uses_expected_payload(self):
        calls = []
        service = NotificationService(
            {"enabled": True, "mode": "onebot", "webhookUrl": "http://127.0.0.1:5700/send_group_msg", "groupId": "12345"},
            opener=lambda request, **_kwargs: calls.append(request) or FakeResponse("{}"),
            clock=lambda: 1000,
        )
        self.assertTrue(service.send("kitchen_alarm", "厨房报警", "烟雾报警"))
        body = json.loads(calls[0].data.decode("utf-8"))
        self.assertEqual(body["group_id"], 12345)
        self.assertIn("厨房报警", body["message"])

    def test_duplicate_notification_is_cooled_down(self):
        calls = []
        service = NotificationService(
            {"enabled": True, "mode": "onebot", "webhookUrl": "http://notify.invalid", "cooldownSeconds": 60},
            opener=lambda request, **_kwargs: calls.append(request) or FakeResponse("{}"),
            clock=lambda: 1000,
        )
        self.assertTrue(service.send("door_open", "门禁", "打开"))
        self.assertFalse(service.send("door_open", "门禁", "打开"))
        self.assertEqual(len(calls), 1)

    def test_disabled_or_unconfigured_service_is_safe_noop(self):
        service = NotificationService({"enabled": False})
        self.assertFalse(service.send("door_open", "门禁", "打开"))
        self.assertFalse(NotificationService({"enabled": True, "mode": "qmsg"}).send("door_open", "门禁", "打开"))


if __name__ == "__main__":
    unittest.main()
