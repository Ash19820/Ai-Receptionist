from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from margin_guard.db import initialize
from margin_guard.mcp.request_inbox import create_caller_request, get_open_requests
from margin_guard.receptionist_profile import find_faqs, load_profile


class ReceptionistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "requests.sqlite3"
        self.profile_path = root / "business.json"
        self.profile_path.write_text(
            json.dumps({
                "business_name": "Test Clinic",
                "languages": ["hi-IN", "en-IN"],
                "hours": [],
                "service_area": [],
                "services": [{"name": "Consultation"}],
                "faqs": [{"question": "Do you take walk-ins?", "answer": "Call first."}],
            }),
            encoding="utf-8",
        )
        self.old_db = os.environ.get("RECEPTIONIST_DB")
        self.old_profile = os.environ.get("BUSINESS_PROFILE")
        os.environ["RECEPTIONIST_DB"] = str(self.db_path)
        os.environ["BUSINESS_PROFILE"] = str(self.profile_path)
        initialize()

    def tearDown(self) -> None:
        if self.old_db is None:
            os.environ.pop("RECEPTIONIST_DB", None)
        else:
            os.environ["RECEPTIONIST_DB"] = self.old_db
        if self.old_profile is None:
            os.environ.pop("BUSINESS_PROFILE", None)
        else:
            os.environ["BUSINESS_PROFILE"] = self.old_profile
        self.temp_dir.cleanup()

    def test_profile_and_faq_are_loaded_from_business_configuration(self) -> None:
        self.assertEqual(load_profile()["business_name"], "Test Clinic")
        self.assertEqual(find_faqs("walk-ins"), [
            {"question": "Do you take walk-ins?", "answer": "Call first."}
        ])

    def test_caller_request_is_saved_for_review(self) -> None:
        result = create_caller_request(
            request_type="callback",
            summary="Asked about consultation hours",
            caller_confirmed=True,
            caller_name="Asha",
            caller_phone="+919876543210",
            service="Consultation",
            preferred_time="Tomorrow morning",
            source="phone",
        )
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("not a confirmed booking", result["message"])
        requests = get_open_requests()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["caller_name"], "Asha")
        self.assertEqual(requests[0]["source"], "phone")

    def test_invalid_request_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_caller_request(request_type="booking", summary="Book a slot", caller_confirmed=True)

    def test_invalid_phone_number_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_caller_request(
                request_type="callback",
                summary="Please call back",
                caller_confirmed=True,
                caller_phone="bad-number!",
            )

    def test_request_requires_explicit_caller_confirmation(self) -> None:
        with self.assertRaises(ValueError):
            create_caller_request(
                request_type="callback",
                summary="Please call back",
                caller_confirmed=False,
            )


if __name__ == "__main__":
    unittest.main()
