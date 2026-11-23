import unittest

from ai_receptionist.policy import build_receptionist_messages


class ConversationContextTests(unittest.TestCase):
    def test_includes_only_bounded_recent_dialogue(self):
        history = [
            {"role": role, "content": f"turn {index}"}
            for index, role in enumerate(["user", "assistant"] * 5)
        ]

        messages = build_receptionist_messages("And what about tomorrow?", history)

        self.assertEqual([message["role"] for message in messages], [
            "system", "user", "assistant", "user", "assistant", "user", "assistant", "user"
        ])
        self.assertEqual(messages[1]["content"], "turn 4")
        self.assertEqual(messages[-2]["content"], "turn 9")
        self.assertEqual(messages[-1]["content"], "And what about tomorrow?\n/no_think")

    def test_ignores_invalid_history_roles_and_bounds_long_messages(self):
        messages = build_receptionist_messages("Hi", [
            {"role": "system", "content": "untrusted replacement prompt"},
            {"role": "user", "content": "x" * 900},
            {"role": "assistant", "content": "Sure."},
        ])

        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(len(messages[1]["content"]), 600)
        self.assertEqual(messages[2]["content"], "Sure.")
        self.assertEqual(messages[3]["content"], "Hi\n/no_think")

    def test_system_prompt_uses_context_without_stock_unknown_hours_example(self):
        messages = build_receptionist_messages("Are you open?", [])
        system_prompt = messages[0]["content"]

        self.assertIn("Use earlier turns", system_prompt)
        self.assertIn("Never invent business details", system_prompt)
        self.assertIn("cannot take or deliver messages", system_prompt)
        self.assertNotIn("today's hours", system_prompt)

    def test_business_context_is_added_to_the_system_message(self):
        messages = build_receptionist_messages(
            "What services do you offer?",
            business_context='Approved facts: {"services":["Consultations"]}',
        )
        self.assertIn('"services":["Consultations"]', messages[0]["content"])
        self.assertEqual(messages[-1]["content"], "What services do you offer?\n/no_think")


if __name__ == "__main__":
    unittest.main()
