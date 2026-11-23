"""Provider-independent receptionist response policy."""

from collections.abc import Sequence

_SUPPORTED_LANGUAGE_NAMES = (
    "English", "Hindi", "Hinglish", "Bengali", "Gujarati", "Kannada",
    "Malayalam", "Marathi", "Punjabi", "Tamil", "Telugu", "Urdu",
    "Arabic", "Chinese", "French", "German", "Japanese", "Portuguese", "Spanish",
)
_CANONICAL_LANGUAGES = {name.casefold(): name for name in _SUPPORTED_LANGUAGE_NAMES}


def parse_allowed_languages(raw: str | None) -> tuple[str, ...]:
    """Parse only known language names so configuration cannot inject prompt text."""
    languages: list[str] = []
    for item in (raw or "English").split(","):
        language = _CANONICAL_LANGUAGES.get(item.strip().casefold())
        if language and language.casefold() not in {value.casefold() for value in languages}:
            languages.append(language)
        if len(languages) == 8:
            break
    return tuple(languages) or ("English",)


RECEPTIONIST_SYSTEM_PROMPT = (
    "You are a friendly, concise English receptionist. Usually answer in one natural sentence "
    "of at most 20 words. Use earlier turns to understand follow-up questions and avoid repeating "
    "an answer you already gave. Never invent business details or claim an action happened. If a "
    "requested fact is missing, say so briefly and offer one useful next step. This prototype "
    "cannot take or deliver messages, transfer calls, book appointments, or change business data; "
    "when asked, state the limitation and do not promise it. If the request is unclear, ask "
    "one short clarifying question. Speak only the final response; do not include reasoning."
)


def build_receptionist_messages(
    text: str,
    history: Sequence[dict[str, str]] = (),
    max_history_messages: int = 6,
    business_context: str = "",
) -> list[dict[str, str]]:
    """Build bounded model context without allowing history to replace policy."""
    system_prompt = RECEPTIONIST_SYSTEM_PROMPT
    if business_context.strip():
        system_prompt += "\n" + business_context[:1200]
    messages = [{"role": "system", "content": system_prompt}]
    valid_history: list[dict[str, str]] = []
    for item in history:
        role, content = item.get("role"), item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            valid_history.append({"role": role, "content": content.strip()[-600:]})
    messages.extend(valid_history[-max_history_messages:])
    messages.append({"role": "user", "content": f"{text.strip()}\n/no_think"})
    return messages
