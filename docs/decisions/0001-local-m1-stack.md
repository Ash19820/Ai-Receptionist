# Decision 0001: Local M1 voice stack

**Date:** 2026-10-20
**Status:** Initial implementation; requires installation and laptop validation.

## Decision

Build a single-process Python 3.12 application. Use PortAudio through `sounddevice` for microphone and speaker I/O, a small energy-based end-of-turn detector, `faster-whisper` with local `tiny.en` int8 weights for English ASR, `llama-cpp-python` with Qwen3-0.6B GGUF for local response generation, and `kokoro-onnx` with int8 Kokoro weights for local English speech.

Each stage sits behind a small interface. The initial runtime uses local model paths. Model downloads are an explicit setup step; keep model files out of Git.

### M1 update — 2026-10-25

Keep the existing app and provider interfaces, but use Pipecat's Smart Turn v3 CPU ONNX model and upstream Whisper-style feature extraction behind `EndOfTurnDetector`. This reuses the semantic endpointing component without importing Pipecat's full runtime. The browser energy detector still detects speech starts; Smart Turn judges pauses, and the configured silence timeout is the fallback. See [`open-source-adaptations.md`](../research/open-source-adaptations.md) for upstream links, trade-offs, and preliminary measurements.

The Qwen adapter now sends bounded conversation history and follows Qwen3's non-thinking sampler guidance. This addresses observed repeated replies while preserving the small local model. Human live-call verification remains an M1 exit condition.

### Provider direction update — 2026-10-25

The user has approved considering Gemini, Groq, and OpenRouter API keys. Keep the local stack as a selectable mode and make each hosted mode explicit in configuration. Never silently fall back from a failed local provider to a hosted one. First evaluate Gemini Live as an optional speech-to-speech path against the current local cascade; the free tier's data-use terms and account quota must be shown before any real microphone test. See [`open-source-adaptations.md`](../research/open-source-adaptations.md).

## Options considered

- **Pipecat:** actively maintained, BSD-2-Clause, designed for streaming/realtime voice agents. Defer until streaming, telephony, or more complex orchestration is required; it adds framework surface to the minimal laptop prototype.
- **Silero VAD:** actively maintained and provides ONNX models. Defer to keep the first implementation dependency surface smaller; the initial energy detector is simpler but more sensitive to noise and microphone gain.
- **faster-whisper vs whisper.cpp/sherpa-onnx:** choose `faster-whisper` for a Python-native path and its CPU int8 support. Compare accuracy/speed on the laptop before locking the model size.
- **Kokoro ONNX vs Piper:** choose Kokoro ONNX for the initial English voice quality candidate. Package metadata currently requires Python `<3.14`, so use Python 3.12. Validate exact voice asset terms before redistribution.
- **Local LLM:** use `llama-cpp-python` and the official Qwen3-0.6B GGUF Q8_0 asset as a conservative small-model baseline. The model is a quality hypothesis, not a proven receptionist model.

## License notes

- Application code: MIT.
- `faster-whisper`: MIT code; Whisper-derived model assets have their own upstream terms.
- `llama-cpp-python`: MIT code; Qwen3 model and GGUF: Apache-2.0.
- `kokoro-onnx`: MIT code; Kokoro model: Apache-2.0. Confirm selected voice data and any downstream asset terms separately.
- `sounddevice`, ONNX Runtime, NumPy, and other transitive dependencies have separate licenses; capture a dependency/license inventory before distribution.

## Evidence and constraints

- Inspected environment: Fedora 44, x86_64, Ryzen 5 PRO 4650U, 7 GiB RAM, Python 3.14.8, 190 GiB disk free. No sound devices are exposed to the current execution environment.
- Kokoro ONNX package metadata declares Python `>=3.10,<3.14`; a separate Python 3.12 environment is required.
- `llama-cpp-python` supports CPU builds and documents GCC/CMake installation. GCC, CMake, and Ninja are present in the inspected environment.
- The selected baseline weights need downloading during setup. Runtime inference is expected to be local after that, but must be verified with outbound networking blocked.
- No model speed, answer quality, audio device access, or full installation result has been measured on the target laptop.

## Revisit when

- The energy detector misses speech or triggers on room noise: benchmark Silero VAD ONNX.
- Whisper tiny accuracy is insufficient or latency too high: compare `base.en`, whisper.cpp, and sherpa-onnx.
- Kokoro latency or voice quality is unacceptable: benchmark an alternative local TTS with separately reviewed model/voice licenses.
- Business integrations or phone-call streaming are selected: reconsider Pipecat or another realtime orchestration layer.
