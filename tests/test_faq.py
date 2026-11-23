import json
from pathlib import Path
import tempfile
import unittest

from ai_receptionist.business import BusinessFaq


class BusinessFaqTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "faq.json"
        self.path.write_text(
            json.dumps(
                [
                    {
                        "questions": ["What are your business hours?", "Are you open today?"],
                        "answer": "We are open from nine to five.",
                    },
                    {
                        "questions": ["Where are you located?", "What is your address?"],
                        "answer": "We are at 10 Main Street.",
                    },
                ]
            ),
            encoding="utf-8",
        )
        self.faq = BusinessFaq(self.path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_known_question_matches_approved_answer(self) -> None:
        self.assertEqual(
            self.faq.match("Are you open today?"),
            ("We are open from nine to five.", 1.0),
        )

    def test_unrelated_question_does_not_match(self) -> None:
        self.assertIsNone(self.faq.match("Do you repair washing machines?"))

    def test_multi_part_question_does_not_match_only_first_clause(self) -> None:
        self.assertIsNone(
            self.faq.match("Are you open today and what are your prices?"),
        )

    def test_curated_audio_cache_is_bounded(self) -> None:
        import numpy as np

        faq = BusinessFaq(self.path, cache_size=1)
        faq.store_speech("first", np.zeros(4, dtype=np.float32), 24000)
        faq.store_speech("second", np.ones(4, dtype=np.float32), 24000)
        self.assertIsNone(faq.cached_speech("first"))
        self.assertIsNotNone(faq.cached_speech("second"))

    def test_faq_file_changes_reload_without_restart(self) -> None:
        self.path.write_text(
            json.dumps([{"questions": ["Do you deliver?"], "answer": "Yes, we deliver locally."}]),
            encoding="utf-8",
        )
        self.assertEqual(
            self.faq.match("Do you deliver?"),
            ("Yes, we deliver locally.", 1.0),
        )


if __name__ == "__main__":
    unittest.main()
