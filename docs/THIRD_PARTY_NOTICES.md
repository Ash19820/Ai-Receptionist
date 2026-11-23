# Third-party notices

## LiveKit Agents and Google Gemini plugin (optional)

- Python packages: `livekit-agents[google]` and its Google LiveKit plugin, installed only for the optional LiveKit runtime.
- Framework/plugin source license: Apache-2.0; see the [upstream license](https://github.com/livekit/agents/blob/main/LICENSE).
- The optional package does not include a LiveKit-hosted service license or Google's Gemini API terms; those services have separate account and data-use terms. The project uses Google's hosted Gemini Live model, not LiveKit's separately licensed turn-detection model.

## Pipecat Smart Turn v3

- Model: `pipecat-ai/smart-turn-v3.2-cpu.onnx`, from the [official Pipecat Smart Turn model repository](https://huggingface.co/pipecat-ai/smart-turn-v3).
- Model license: BSD 2-Clause; see [`SMART_TURN_LICENSE.txt`](../src/ai_receptionist/_vendor/SMART_TURN_LICENSE.txt).
- Model SHA-256: `2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f`.
- Whisper-style log-mel feature extraction in [`smart_turn_features.py`](../src/ai_receptionist/_vendor/smart_turn_features.py) is vendored from [Pipecat](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/audio/turn/smart_turn/_whisper_features.py), Copyright 2024–2026 Daily, BSD 2-Clause. Parts are derived from Hugging Face Transformers, Apache License 2.0; see [`APACHE-2.0.txt`](../src/ai_receptionist/_vendor/APACHE-2.0.txt) and the source file's attribution header.
- The local inference adapter is project-specific glue and uses ONNX Runtime's CPU execution provider. Model downloads are manual; runtime inference does not access the network.
