import unittest
from pathlib import Path

import numpy as np

from ai_receptionist.turn_detection import (
    SAMPLE_RATE,
    WINDOW_SECONDS,
    LocalSmartTurnDetector,
    prepare_smart_turn_audio,
)


class SmartTurnAudioWindowTests(unittest.TestCase):
    def test_short_audio_is_padded_at_the_start(self):
        audio = np.array([0.25, -0.25], dtype=np.float32)

        prepared = prepare_smart_turn_audio(audio)

        self.assertEqual(prepared.size, SAMPLE_RATE * WINDOW_SECONDS)
        self.assertEqual(prepared[-2:].tolist(), audio.tolist())
        self.assertTrue(np.all(prepared[:-2] == 0))

    def test_long_audio_keeps_the_most_recent_eight_seconds(self):
        audio = np.arange(SAMPLE_RATE * (WINDOW_SECONDS + 1), dtype=np.float32)

        prepared = prepare_smart_turn_audio(audio)

        self.assertEqual(prepared.size, SAMPLE_RATE * WINDOW_SECONDS)
        self.assertEqual(prepared[0], audio[SAMPLE_RATE])
        self.assertEqual(prepared[-1], audio[-1])


class SmartTurnModelSmokeTests(unittest.TestCase):
    def test_local_onnx_model_returns_a_probability(self):
        model_path = Path(__file__).parents[1] / "models" / "smart-turn-v3.2-cpu.onnx"
        if not model_path.is_file():
            self.skipTest("Download the Smart Turn model to run the local inference smoke test")

        detector = LocalSmartTurnDetector(model_path, cpu_threads=1)
        probability = detector.completion_probability(
            np.zeros(SAMPLE_RATE, dtype=np.float32)
        )

        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)


if __name__ == "__main__":
    unittest.main()
