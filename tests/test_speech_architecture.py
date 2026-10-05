from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from margin_guard.speech.config import detect_response_language, parse_tts_routes
from margin_guard.speech.registry import (
    SPEECH_PROVIDERS,
    SpeechProviderError,
    SpeechProviderRegistry,
    load_provider_plugins,
)


class SpeechArchitectureTests(unittest.TestCase):
    def test_routes_can_select_independent_models_by_language(self) -> None:
        self.assertEqual(
            parse_tts_routes("hi=piper,en=kokoro,bn=next-model"),
            {"hi": "piper", "en": "kokoro", "bn": "next-model"},
        )

    def test_invalid_or_duplicate_routes_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "language=provider"):
            parse_tts_routes("hi")
        with self.assertRaisesRegex(ValueError, "duplicate language"):
            parse_tts_routes("hi=piper,hi=other")

    def test_response_language_detection_uses_script_mapping(self) -> None:
        self.assertEqual(detect_response_language("Hello वहाँ"), "en")
        self.assertEqual(detect_response_language(" नमस्ते"), "hi")
        self.assertEqual(detect_response_language("বাংলা"), "bn")
        self.assertEqual(detect_response_language("hola", latin_language="es"), "es")
        self.assertIsNone(detect_response_language("123?!"))

    def test_registered_adapter_can_be_replaced_without_pipeline_changes(self) -> None:
        registry = SpeechProviderRegistry()
        registry.register_stt("offline", lambda: "recognizer-v1")
        registry.register_tts("natural", lambda language: f"voice-v1:{language}")
        self.assertEqual(registry.create_stt("offline"), "recognizer-v1")
        self.assertEqual(registry.create_tts("natural", "hi"), "voice-v1:hi")

    def test_unknown_provider_names_list_registered_adapters(self) -> None:
        registry = SpeechProviderRegistry()
        registry.register_stt("whisper", lambda: object())
        with self.assertRaisesRegex(SpeechProviderError, "Registered providers: whisper"):
            registry.create_stt("missing")

    def test_external_provider_module_registers_without_pipeline_edits(self) -> None:
        token = uuid4().hex
        module_name = f"speech_plugin_{token}"
        provider_name = f"plugin_{token}"
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, f"{module_name}.py").write_text(
                "from margin_guard.speech.registry import SPEECH_PROVIDERS\n"
                f"SPEECH_PROVIDERS.register_tts('{provider_name}', lambda language: language)\n",
                encoding="utf-8",
            )
            sys.path.insert(0, directory)
            try:
                load_provider_plugins(module_name)
                self.assertEqual(SPEECH_PROVIDERS.create_tts(provider_name, "hi"), "hi")
            finally:
                sys.path.remove(directory)
                sys.modules.pop(module_name, None)
                importlib.invalidate_caches()


if __name__ == "__main__":
    unittest.main()
