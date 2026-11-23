import logging
import re
import threading
import time
from collections.abc import Sequence

import numpy as np

from ai_receptionist.config import Settings
from ai_receptionist.policy import build_receptionist_messages

logger = logging.getLogger(__name__)

class LocalWhisper:
    def __init__(self, settings: Settings) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Speech recognition requires faster-whisper; install the project dependencies."
            ) from exc
        if not settings.whisper_model_path.is_dir():
            raise FileNotFoundError(
                f"Whisper model directory not found: {settings.whisper_model_path}. "
                "Download the model before starting; runtime model downloads are disabled."
            )
        self.model = WhisperModel(
            str(settings.whisper_model_path),
            device="cpu",
            compute_type=settings.whisper_compute_type,
            cpu_threads=settings.whisper_cpu_threads,
        )
        self._lock = threading.Lock()

    def transcribe(self, audio: str | np.ndarray) -> str:
        with self._lock:
            segments, _info = self.model.transcribe(
                audio,
                language="en",
                beam_size=1,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()

    def transcribe_partial(self, audio: np.ndarray) -> str:
        """Transcribe an in-progress audio snapshot for live captions."""
        with self._lock:
            segments, _info = self.model.transcribe(
                audio,
                language="en",
                beam_size=1,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()


class LocalLlamaResponder:
    def __init__(self, settings: Settings) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "Local response generation requires llama-cpp-python; install the project dependencies."
            ) from exc
        if not settings.llama_model_path.is_file():
            raise FileNotFoundError(
                f"Local LLM file not found: {settings.llama_model_path}. "
                "Download the selected GGUF model to that path; local mode will not use a cloud fallback."
            )
        self.settings = settings
        self._lock = threading.Lock()
        self.model = Llama(
            model_path=str(settings.llama_model_path),
            n_ctx=1024,
            n_threads=settings.whisper_cpu_threads,
            verbose=False,
        )

    def respond(
        self,
        text: str,
        history: Sequence[dict[str, str]] = (),
        business_context: str = "",
    ) -> str:
        with self._lock:
            stream = self.model.create_chat_completion(
                messages=build_receptionist_messages(
                    text, history, business_context=business_context
                ),
                max_tokens=self.settings.max_answer_tokens,
                temperature=0.7,
                top_p=0.8,
                top_k=20,
                presence_penalty=0.3,
                stream=True,
            )
            deadline = time.monotonic() + self.settings.llm_timeout_seconds
            pieces: list[str] = []
            for event in stream:
                if time.monotonic() >= deadline:
                    close = getattr(stream, "close", None)
                    if close is not None:
                        close()
                    logger.warning("Local language model timed out; discarded the partial answer.")
                    return "Sorry, I'm taking too long to answer. Please try again."
                delta = event["choices"][0].get("delta", {}).get("content")
                if delta:
                    pieces.append(delta)
            answer = "".join(pieces).strip()
        # Keep Qwen's internal reasoning out of both the transcript and speech output,
        # even if the model ignores the non-thinking instruction.
        answer = re.sub(r"<think>.*?</think>", " ", answer, flags=re.IGNORECASE | re.DOTALL)
        answer = re.sub(r"<think>.*$", " ", answer, flags=re.IGNORECASE | re.DOTALL)
        answer = re.sub(r"</?think>", " ", answer, flags=re.IGNORECASE)
        answer = re.sub(r"\s+", " ", answer).strip()
        return answer or "Sorry, I couldn't come up with an answer just now."


class LocalKokoro:
    def __init__(self, settings: Settings) -> None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError(
                "Local speech synthesis requires kokoro-onnx; install the project dependencies."
            ) from exc
        for path in (settings.kokoro_model_path, settings.kokoro_voices_path):
            if not path.is_file():
                raise FileNotFoundError(f"Kokoro asset not found: {path}")
        self.voice = settings.kokoro_voice
        self.model = Kokoro(str(settings.kokoro_model_path), str(settings.kokoro_voices_path))
        self._lock = threading.Lock()

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        with self._lock:
            audio, sample_rate = self.model.create(
                text,
                voice=self.voice,
                speed=1.0,
                lang="en-us",
            )
        return np.asarray(audio, dtype=np.float32), sample_rate

    def close(self) -> None:
        voices = getattr(self.model, "voices", None)
        close = getattr(voices, "close", None)
        if close is not None:
            close()
