"""Language routing helpers for configurable speech services."""

from __future__ import annotations

import unicodedata


DEFAULT_TTS_ROUTES = "hi=piper,en=kokoro"

# The agent currently prompts for Hindi in Devanagari and English in Latin
# script. Additional scripts can be mapped here and enabled through routes.
_SCRIPT_LANGUAGE_CODES = {
    "DEVANAGARI": "hi",
    "BENGALI": "bn",
    "GURMUKHI": "pa",
    "GUJARATI": "gu",
    "ORIYA": "or",
    "TAMIL": "ta",
    "TELUGU": "te",
    "KANNADA": "kn",
    "MALAYALAM": "ml",
}


def parse_tts_routes(value: str = DEFAULT_TTS_ROUTES) -> dict[str, str]:
    """Parse comma-separated language=provider entries."""
    routes: dict[str, str] = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            language, provider = (part.strip().lower() for part in item.split("=", 1))
        except ValueError as exc:
            raise ValueError(
                "VOICE_TTS_ROUTES entries must use language=provider, "
                "for example 'hi=piper,en=kokoro'."
            ) from exc
        if not language or not provider:
            raise ValueError(
                "VOICE_TTS_ROUTES entries must use language=provider, "
                "for example 'hi=piper,en=kokoro'."
            )
        if language in routes:
            raise ValueError(f"VOICE_TTS_ROUTES contains duplicate language '{language}'.")
        routes[language] = provider
    if not routes:
        raise ValueError("VOICE_TTS_ROUTES must contain at least one language=provider entry.")
    return routes


def detect_response_language(text: str, latin_language: str = "en") -> str | None:
    """Return a compact language code from the first supported script found."""
    for character in text:
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        if "LATIN" in name:
            return latin_language.lower()
        for script, language in _SCRIPT_LANGUAGE_CODES.items():
            if script in name:
                return language
        return None
    return None
