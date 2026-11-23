from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    sample_rate: int = 16_000
    frame_ms: int = 30
    speech_threshold: float = 0.012
    end_silence_seconds: float = 0.75
    max_utterance_seconds: float = 20.0
    partial_transcription_interval: float = 1.25
    partial_transcription_min_seconds: float = 1.0
    business_profile_path: Path = Path("business_profile.json")
    faq_path: Path = Path("business_faq.json")
    callback_message_db_path: Path = Path("data/callback_messages.sqlite3")
    callback_message_retention_days: int = 7
    whisper_model_path: Path = Path("models/faster-whisper-base.en")
    smart_turn_model_path: Path = Path("models/smart-turn-v3.2-cpu.onnx")
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 4
    llama_model_path: Path = Path("models/Qwen3-0.6B-Q8_0.gguf")
    kokoro_model_path: Path = Path("models/kokoro-v1.0.int8.onnx")
    kokoro_voices_path: Path = Path("models/voices-v1.0.bin")
    kokoro_voice: str = "af_heart"
    max_answer_tokens: int = 48
    llm_timeout_seconds: float = 20.0

    @classmethod
    def from_environment(cls) -> "Settings":
        """Read local-only settings. No provider or cloud configuration exists."""
        return cls(
            speech_threshold=float(os.getenv("VOICE_SPEECH_THRESHOLD", "0.012")),
            end_silence_seconds=float(os.getenv("VOICE_END_SILENCE_SECONDS", "0.75")),
            max_utterance_seconds=float(os.getenv("VOICE_MAX_UTTERANCE_SECONDS", "20")),
            partial_transcription_interval=float(
                os.getenv("VOICE_PARTIAL_INTERVAL_SECONDS", "1.25")
            ),
            partial_transcription_min_seconds=float(
                os.getenv("VOICE_PARTIAL_MIN_SECONDS", "1.0")
            ),
            business_profile_path=Path(
                os.getenv("BUSINESS_PROFILE_PATH", "business_profile.json")
            ),
            faq_path=Path(os.getenv("BUSINESS_FAQ_PATH", "business_faq.json")),
            callback_message_db_path=Path(
                os.getenv("CALLBACK_MESSAGE_DB_PATH", "data/callback_messages.sqlite3")
            ),
            callback_message_retention_days=int(
                os.getenv("CALLBACK_MESSAGE_RETENTION_DAYS", "7")
            ),
            whisper_model_path=Path(
                os.getenv("WHISPER_MODEL_PATH", "models/faster-whisper-base.en")
            ),
            smart_turn_model_path=Path(
                os.getenv("SMART_TURN_MODEL_PATH", "models/smart-turn-v3.2-cpu.onnx")
            ),
            whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            whisper_cpu_threads=int(os.getenv("WHISPER_CPU_THREADS", "4")),
            llama_model_path=Path(
                os.getenv("LLAMA_MODEL_PATH", "models/Qwen3-0.6B-Q8_0.gguf")
            ),
            kokoro_model_path=Path(os.getenv("KOKORO_MODEL_PATH", "models/kokoro-v1.0.int8.onnx")),
            kokoro_voices_path=Path(os.getenv("KOKORO_VOICES_PATH", "models/voices-v1.0.bin")),
            kokoro_voice=os.getenv("KOKORO_VOICE", "af_heart"),
            max_answer_tokens=int(os.getenv("MAX_ANSWER_TOKENS", "48")),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        )
