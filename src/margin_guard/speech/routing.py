"""Pipecat processor that chooses a TTS adapter for each full response."""

from __future__ import annotations

from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ManuallySwitchServiceFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from margin_guard.speech.config import detect_response_language


class ResponseLanguageTTSRouter(FrameProcessor):
    """Route assistant text to services keyed by language code."""

    def __init__(
        self,
        services: dict[str, object],
        default_language: str,
        latin_language: str = "en",
    ):
        super().__init__()
        self._services = services
        self._default_language = default_language
        self._latin_language = latin_language
        self._selected_service = None
        self._pending_text: list[LLMTextFrame] = []

    async def _select_and_flush(self, language: str, direction: FrameDirection) -> None:
        language = language if language in self._services else self._default_language
        service = self._services[language]
        await self.push_frame(ManuallySwitchServiceFrame(service=service), direction)
        for text_frame in self._pending_text:
            await self.push_frame(text_frame, direction)
        self._pending_text.clear()
        self._selected_service = service

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, LLMFullResponseStartFrame):
                self._selected_service = None
                self._pending_text.clear()
            elif isinstance(frame, LLMTextFrame) and self._selected_service is None:
                self._pending_text.append(frame)
                language = detect_response_language(
                    "".join(item.text for item in self._pending_text),
                    latin_language=self._latin_language,
                )
                if language:
                    await self._select_and_flush(language, direction)
                return
            elif isinstance(frame, LLMFullResponseEndFrame) and self._selected_service is None:
                await self._select_and_flush(self._default_language, direction)

        await self.push_frame(frame, direction)
