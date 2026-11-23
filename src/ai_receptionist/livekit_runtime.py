"""Configuration and shared prompt policy for the optional LiveKit runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from ai_receptionist.policy import parse_allowed_languages


@dataclass(frozen=True)
class LiveKitRuntimeConfig:
    url: str
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    gemini_api_key: str = field(repr=False)
    model: str = "gemini-3.8-live"
    voice: str = "Puck"

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LiveKitRuntimeConfig":
        values = os.environ if environment is None else environment
        url = values.get("LIVEKIT_URL", "").strip().rstrip("/")
        api_key = values.get("LIVEKIT_API_KEY", "").strip()
        api_secret = values.get("LIVEKIT_API_SECRET", "").strip()
        gemini_key = values.get("GEMINI_API_KEY", "").strip()
        google_key = values.get("GOOGLE_API_KEY", "").strip()
        if gemini_key and google_key and gemini_key != google_key:
            raise ValueError(
                "Set only one matching Gemini key: GEMINI_API_KEY or GOOGLE_API_KEY."
            )
        gemini_key = google_key or gemini_key

        missing = [
            name
            for name, value in (
                ("LIVEKIT_URL", url),
                ("LIVEKIT_API_KEY", api_key),
                ("LIVEKIT_API_SECRET", api_secret),
                ("GEMINI_API_KEY", gemini_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "LiveKit voice needs these .env settings: " + ", ".join(missing)
            )

        parsed_url = urlsplit(url)
        if (
            parsed_url.scheme not in {"ws", "wss"}
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("LIVEKIT_URL must be a ws:// or wss:// LiveKit server URL.")

        model = values.get("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
        voice = values.get("LIVEKIT_GEMINI_VOICE", "Puck").strip()
        if not model or len(model) > 120:
            raise ValueError("GEMINI_LIVE_MODEL must be a short model name.")
        if not voice or len(voice) > 80:
            raise ValueError("LIVEKIT_GEMINI_VOICE must be a short voice name.")
        return cls(url, api_key, api_secret, gemini_key, model, voice)


def build_livekit_instructions(
    business_context: str = "", allowed_languages: tuple[str, ...] = ("English",)
) -> str:
    """Create bounded receptionist instructions shared by LiveKit sessions."""
    languages = parse_allowed_languages(",".join(allowed_languages))
    default_language = languages[0]
    if len(languages) == 1:
        language_rule = (
            f"Speak only in {default_language}. Never switch languages because of a short "
            "acknowledgement, filler, name, borrowed word, or unclear audio."
        )
    else:
        language_rule = (
            f"Use only these languages: {', '.join(languages)}. Start in {default_language}; "
            "switch only after a substantive request in another listed language or a clear request to switch."
        )
    instructions = (
        "You are a concise, friendly AI receptionist. Give natural, short spoken answers. "
        "Use only approved business facts; missing details are unknown. Never invent facts or "
        "claim an action happened unless an application tool confirms it. "
        + language_rule
        + " If a caller asks for a person, explain that live transfer and staff notification are "
        "not configured, and offer a callback message for someone to review. Do not say staff "
        "were contacted. For callback messages, get a clear yes to the consent notice before "
        "asking for personal details, read the details back, then require a separate clear yes "
        "before saving. Treat short acknowledgements and background noise as neither consent "
        "nor confirmation. After saving, state that the message is in the local inbox and no "
        "one was automatically notified."
    )
    if business_context.strip():
        instructions += "\n" + business_context.strip()[:1200]
    return instructions
