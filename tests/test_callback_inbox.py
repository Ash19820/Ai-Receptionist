from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from ai_receptionist.callback_inbox import CallbackInbox, CallbackMessageWorkflow


class CallbackInboxTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "private" / "messages.sqlite3"
        self.inbox = CallbackInbox(self.path, retention_days=7)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_callback_is_not_saved_without_consent_and_final_confirmation(self):
        workflow = CallbackMessageWorkflow(self.inbox)
        with self.assertRaises(ValueError):
            workflow.prepare("Asha", "+91 98765 43210", "Please call me.")
        notice = workflow.request_consent()
        self.assertIn("No one is automatically notified", notice)
        self.assertIn("Gemini", notice)
        self.assertIsNone(workflow.observe_user_transcript("uh-huh"))
        self.assertEqual(self.inbox.list_recent(), [])
        self.assertEqual(workflow.observe_user_transcript("Yes, please."), "consent_given")
        draft = workflow.prepare("Asha", "+91 98765 43210", "Please call me after lunch.")
        with self.assertRaises(ValueError):
            workflow.save(draft["draft_id"])
        self.assertEqual(self.inbox.list_recent(), [])

    def test_clear_confirmation_saves_once_and_can_be_deleted(self):
        workflow = CallbackMessageWorkflow(self.inbox)
        workflow.request_consent()
        workflow.observe_user_transcript("I agree")
        draft = workflow.prepare("Asha", "+91 98765 43210", "Please call me after lunch.")
        self.assertIsNone(workflow.observe_user_transcript("uh-huh"))
        self.assertEqual(workflow.observe_user_transcript("Yes, that's correct."), "message_confirmed")
        saved = workflow.save(draft["draft_id"])
        duplicate = self.inbox.save_confirmed(
            draft["draft_id"], "Asha", "+91 98765 43210", "Please call me after lunch."
        )
        self.assertEqual(duplicate.message_id, saved.message_id)
        self.assertEqual(len(self.inbox.list_recent()), 1)
        self.assertTrue(self.inbox.delete(saved.message_id))
        self.assertEqual(self.inbox.list_recent(), [])

    def test_declined_confirmation_never_persists(self):
        workflow = CallbackMessageWorkflow(self.inbox)
        workflow.request_consent()
        workflow.observe_user_transcript("yes")
        draft = workflow.prepare("Asha", "+91 98765 43210", "Please call me.")
        self.assertEqual(workflow.observe_user_transcript("No, don't save it."), "message_declined")
        with self.assertRaises(ValueError):
            workflow.save(draft["draft_id"])
        self.assertEqual(self.inbox.list_recent(), [])

    def test_expired_messages_are_deleted(self):
        saved = self.inbox.save_confirmed("draft-1", "Asha", "+91 98765 43210", "Please call me.")
        expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE callback_messages SET expires_at = ? WHERE message_id = ?",
                (expired, saved.message_id),
            )
        self.assertEqual(self.inbox.prune_expired(), 1)
        self.assertEqual(self.inbox.list_recent(), [])

    def test_database_and_new_directory_are_private(self):
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_simultaneous_workers_can_initialize_the_same_inbox(self):
        path = Path(self.temp_dir.name) / "shared" / "messages.sqlite3"
        with ThreadPoolExecutor(max_workers=4) as workers:
            inboxes = list(workers.map(lambda _: CallbackInbox(path), range(4)))
        self.assertEqual(len(inboxes[0].list_recent()), 0)

    def test_rejects_invalid_phone_and_retention(self):
        with self.assertRaises(ValueError):
            self.inbox.validate_details("Asha", "123", "Please call.")
        with self.assertRaises(ValueError):
            CallbackInbox(self.path.parent / "bad.sqlite3", retention_days=0)


if __name__ == "__main__":
    unittest.main()
