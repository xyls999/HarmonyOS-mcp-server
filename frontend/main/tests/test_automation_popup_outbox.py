import tempfile
import unittest
from pathlib import Path

from backend.d6.automation.popup_outbox import PopupOutbox


class PopupOutboxTests(unittest.TestCase):
    def test_urgent_items_preempt_routine_and_ack_is_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "popup.db"
            outbox = PopupOutbox(path)
            routine = outbox.enqueue("automation", {"ruleId": "A001", "actions": [{"success": True}]}, urgent=False)
            urgent = outbox.enqueue("alarm", {"ruleId": "A005", "actions": [{"success": True}]}, urgent=True)
            self.assertIsNotNone(routine)
            self.assertIsNotNone(urgent)
            items = outbox.pending()
            self.assertEqual(items[0]["id"], urgent)
            self.assertTrue(items[0]["requiresAcknowledgement"])
            self.assertFalse(items[1]["requiresAcknowledgement"])
            self.assertTrue(outbox.acknowledge(urgent))
            reopened = PopupOutbox(path)
            self.assertEqual([item["id"] for item in reopened.pending()], [routine])

    def test_empty_or_duplicate_rule_batch_does_not_spam_popups(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = PopupOutbox(Path(directory) / "popup.db")
            self.assertIsNone(outbox.enqueue("automation", {"ruleId": "A001", "actions": []}))
            first = outbox.enqueue("automation", {"ruleId": "A001", "actions": [{"success": True}]})
            second = outbox.enqueue("automation", {"ruleId": "A001", "actions": [{"success": True}]})
            self.assertIsNotNone(first)
            self.assertIsNone(second)

    def test_acknowledged_adjustment_stays_until_feedback_then_leaves_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = PopupOutbox(Path(directory) / "popup.db")
            popup_id = outbox.enqueue("automation", {"ruleId": "A001", "actions": [{"success": True}]}, urgent=False, requires_ack=True)
            self.assertTrue(outbox.acknowledge(popup_id))
            self.assertEqual(len(outbox.pending()), 1)
            self.assertEqual(outbox.submit_feedback(popup_id, 9)["score"], 9)
            self.assertEqual(outbox.pending(), [])


if __name__ == "__main__":
    unittest.main()
