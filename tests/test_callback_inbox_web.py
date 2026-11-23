import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from ai_receptionist.callback_inbox import CallbackInbox
from ai_receptionist.web import callback_messages, delete_callback_message


class CallbackInboxRouteTests(unittest.TestCase):
    def test_inbox_routes_require_same_origin_and_allow_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = CallbackInbox(Path(directory) / "messages.sqlite3")
            saved = inbox.save_confirmed(
                "synthetic-draft", "Test Caller", "+91 98765 43210", "Please call back."
            )
            untrusted = Request({
                "type": "http",
                "headers": [(b"origin", b"https://untrusted.example")],
            })
            trusted = Request({
                "type": "http",
                "headers": [(b"origin", b"http://127.0.0.1:8765")],
            })

            async def exercise_routes():
                async def run_directly(function, *args):
                    return function(*args)

                with (
                    patch("ai_receptionist.web._get_callback_inbox", return_value=inbox),
                    patch("ai_receptionist.web.run_in_threadpool", side_effect=run_directly),
                ):
                    with self.assertRaises(HTTPException) as rejected:
                        await callback_messages(untrusted)
                    self.assertEqual(rejected.exception.status_code, 403)
                    listed = await callback_messages(trusted)
                    self.assertEqual(listed[0]["message_id"], saved.message_id)
                    deleted = await delete_callback_message(saved.message_id, trusted)
                    self.assertEqual(deleted, {"deleted": True})

            asyncio.run(exercise_routes())
            self.assertEqual(inbox.list_recent(), [])


if __name__ == "__main__":
    unittest.main()
