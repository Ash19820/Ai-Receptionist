import unittest

from ai_receptionist.stream_buffer import append_pcm16_bounded


class PcmBufferTests(unittest.TestCase):
    def test_appends_until_limit_without_truncating_samples(self) -> None:
        buffer = bytearray()

        self.assertFalse(append_pcm16_bounded(buffer, b"\x01\x00\x02\x00", 6))
        self.assertTrue(append_pcm16_bounded(buffer, b"\x03\x00\x04\x00", 6))
        self.assertEqual(buffer, b"\x01\x00\x02\x00\x03\x00")

    def test_reports_overflow_and_keeps_buffer_bounded(self) -> None:
        buffer = bytearray(b"\x01\x00")

        overflowed = append_pcm16_bounded(buffer, b"\x02\x00\x03\x00", 4)

        self.assertTrue(overflowed)
        self.assertEqual(buffer, b"\x01\x00\x02\x00")

    def test_rejects_misaligned_pcm16(self) -> None:
        with self.assertRaises(ValueError):
            append_pcm16_bounded(bytearray(), b"\x01", 4)

    def test_rejects_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            append_pcm16_bounded(bytearray(), b"\x01\x00", 3)


if __name__ == "__main__":
    unittest.main()
