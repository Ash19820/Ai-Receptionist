"""Small provider registry used to keep speech models replaceable."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class SpeechProviderError(ValueError):
    """Raised when a configured speech provider is unavailable."""


STTFactory = Callable[[], Any]
TTSFactory = Callable[[str], Any]


@dataclass
class SpeechProviderRegistry:
    """Maps stable provider names to Pipecat service factories.

    Factories receive only the language they need and import provider-specific
    packages lazily. A replacement model therefore changes its adapter and
    configuration, while the call pipeline stays the same.
    """

    _stt_factories: dict[str, STTFactory] = field(default_factory=dict)
    _tts_factories: dict[str, TTSFactory] = field(default_factory=dict)

    def register_stt(self, name: str, factory: STTFactory) -> None:
        self._register(self._stt_factories, name, factory, "STT")

    def register_tts(self, name: str, factory: TTSFactory) -> None:
        self._register(self._tts_factories, name, factory, "TTS")

    @staticmethod
    def _register(registry: dict, name: str, factory: Callable, kind: str) -> None:
        key = name.strip().lower()
        if not key:
            raise ValueError(f"{kind} provider name cannot be empty.")
        if key in registry:
            raise ValueError(f"{kind} provider '{key}' is already registered.")
        registry[key] = factory

    def create_stt(self, name: str) -> Any:
        return self._create(self._stt_factories, name, "STT")

    def create_tts(self, name: str, language: str) -> Any:
        return self._create(self._tts_factories, name, "TTS", language)

    @staticmethod
    def _create(registry: dict, name: str, kind: str, *args: Any) -> Any:
        key = name.strip().lower()
        try:
            factory = registry[key]
        except KeyError as exc:
            available = ", ".join(sorted(registry)) or "none"
            raise SpeechProviderError(
                f"Unknown {kind} provider '{key}'. Registered providers: {available}."
            ) from exc
        return factory(*args)


SPEECH_PROVIDERS = SpeechProviderRegistry()


def load_provider_plugins(module_names: str | None = None) -> None:
    """Load optional modules that register additional speech adapters.

    Set ``SPEECH_PROVIDER_MODULES`` to a comma-separated list of import paths.
    Each module registers factories with ``SPEECH_PROVIDERS`` when imported.
    """
    configured_modules = module_names
    if configured_modules is None:
        configured_modules = os.getenv("SPEECH_PROVIDER_MODULES", "")
    for module_name in configured_modules.split(","):
        module_name = module_name.strip()
        if module_name:
            importlib.import_module(module_name)
