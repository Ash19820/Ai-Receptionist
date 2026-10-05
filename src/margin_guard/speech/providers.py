"""Built-in lazy adapters from speech-provider names to Pipecat services."""

from __future__ import annotations

import os

from margin_guard.speech.registry import SPEECH_PROVIDERS


def _create_whisper_stt():
    from pipecat.services.whisper.stt import WhisperSTTService

    return WhisperSTTService(
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        settings=WhisperSTTService.Settings(
            model=os.getenv("WHISPER_MODEL", "base"),
            language=None,
        ),
    )


def _create_sarvam_stt():
    from pipecat.services.sarvam.stt import SarvamSTTService

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("Set SARVAM_API_KEY to use Sarvam speech recognition.")
    return SarvamSTTService(
        api_key=api_key,
        settings=SarvamSTTService.Settings(
            model=os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
        ),
    )


def _language_enum(language: str):
    from pipecat.transcriptions.language import Language

    values = {
        "bn": Language.BN,
        "en": Language.EN_IN,
        "gu": Language.GU,
        "hi": Language.HI,
        "kn": Language.KN,
        "ml": Language.ML,
        "mr": Language.MR,
        "or": Language.OR,
        "pa": Language.PA,
        "ta": Language.TA,
        "te": Language.TE,
    }
    try:
        return values[language.lower().split("-", 1)[0]]
    except KeyError as exc:
        raise ValueError(f"No configured Pipecat language mapping for '{language}'.") from exc


def _create_piper_tts(language: str):
    from pipecat.services.piper.tts import PiperTTSService
    from pipecat.transcriptions.language import Language

    language_key = language.lower().split("-", 1)[0]
    environment_key = f"PIPER_{language_key.upper()}_VOICE"
    default_voices = {"hi": "hi_IN-priyamvada-medium"}
    voice = os.getenv(environment_key) or default_voices.get(language_key)
    if not voice:
        raise RuntimeError(
            f"Set {environment_key} to a Piper voice for language '{language_key}'."
        )
    return PiperTTSService(
        settings=PiperTTSService.Settings(
            voice=voice,
            language=_language_enum(language_key),
        ),
    )


def _create_kokoro_tts(language: str):
    import sys

    if language.lower().split("-", 1)[0] != "en":
        raise ValueError(
            "Kokoro is configured here for English. Choose another TTS provider for this route."
        )
    if sys.version_info >= (3, 14):
        raise RuntimeError(
            "The published kokoro-onnx package does not support Python 3.14 yet. "
            "Use Python 3.13 or older and install the voice-local extra."
        )
    from pipecat.services.kokoro.tts import KokoroTTSService
    from pipecat.transcriptions.language import Language

    return KokoroTTSService(
        settings=KokoroTTSService.Settings(
            voice=os.getenv("KOKORO_VOICE", "af_heart"),
            language=Language.EN,
        ),
    )


def _create_sarvam_tts(language: str):
    from pipecat.services.sarvam.tts import SarvamTTSService

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("Set SARVAM_API_KEY to use Sarvam speech output.")
    return SarvamTTSService(
        api_key=api_key,
        settings=SarvamTTSService.Settings(
            model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
            voice=os.getenv("SARVAM_TTS_VOICE", "shubh"),
            language=_language_enum(language),
            pace=float(os.getenv("SARVAM_TTS_PACE", "1.0")),
            temperature=float(os.getenv("SARVAM_TTS_TEMPERATURE", "0.8")),
        ),
    )


def _create_gemini_tts(language: str):
    from pipecat.services.google.tts import GeminiTTSService

    api_key = os.getenv("GEMINI_TTS_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_TTS_API_KEY to use Gemini speech output.")
    return GeminiTTSService(
        api_key=api_key,
        settings=GeminiTTSService.Settings(
            model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts"),
            voice=os.getenv("GEMINI_TTS_VOICE", "Kore"),
            prompt=(
                "Speak like a warm, attentive local business receptionist. "
                "Use natural conversational pacing and gentle expression. "
                f"Speak naturally in {language}."
            ),
        ),
    )


SPEECH_PROVIDERS.register_stt("whisper", _create_whisper_stt)
SPEECH_PROVIDERS.register_stt("sarvam", _create_sarvam_stt)
SPEECH_PROVIDERS.register_tts("piper", _create_piper_tts)
SPEECH_PROVIDERS.register_tts("kokoro", _create_kokoro_tts)
SPEECH_PROVIDERS.register_tts("sarvam", _create_sarvam_tts)
SPEECH_PROVIDERS.register_tts("gemini", _create_gemini_tts)


def create_stt_service(provider: str):
    """Create the configured recognizer through the shared adapter registry."""
    return SPEECH_PROVIDERS.create_stt(provider)


def create_tts_service(provider: str, language: str):
    """Create a voice service through the shared adapter registry."""
    return SPEECH_PROVIDERS.create_tts(provider, language)
