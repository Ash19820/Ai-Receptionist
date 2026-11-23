"""Local semantic endpoint detection adapted from Pipecat Smart Turn v3."""

import math
from pathlib import Path

import numpy as np

from ai_receptionist._vendor.smart_turn_features import compute_whisper_log_mel_features


SAMPLE_RATE = 16_000
WINDOW_SECONDS = 8


def prepare_smart_turn_audio(audio: np.ndarray) -> np.ndarray:
    """Keep the final eight seconds and right-align shorter utterances."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    sample_count = SAMPLE_RATE * WINDOW_SECONDS
    if audio.size > sample_count:
        return audio[-sample_count:]
    if audio.size < sample_count:
        return np.pad(audio, (sample_count - audio.size, 0), mode="constant")
    return audio


class LocalSmartTurnDetector:
    """CPU ONNX end-of-turn classifier from Pipecat's Smart Turn v3 model."""

    def __init__(self, model_path: Path, cpu_threads: int = 1) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                "Smart Turn requires onnxruntime; install the project dependencies."
            ) from exc
        if not model_path.is_file():
            raise FileNotFoundError(f"Smart Turn model not found: {model_path}")
        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = max(1, cpu_threads)
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(str(model_path), sess_options=options)

    def completion_probability(self, audio: np.ndarray) -> float:
        window = prepare_smart_turn_audio(audio)
        features = compute_whisper_log_mel_features(window, do_normalize=True)
        output = self._session.run(
            None, {"input_features": np.expand_dims(features, axis=0)}
        )[0]
        probability = float(np.asarray(output)[0].item())
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise RuntimeError(f"Smart Turn returned an invalid probability: {probability}")
        return probability
