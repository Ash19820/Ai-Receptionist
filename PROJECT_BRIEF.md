# AI Receptionist: Project Brief

## Goal
Build and own a GitHub-ready AI receptionist product that can be deployed for real businesses and eventually sold. It must answer inbound phone calls naturally, support business-specific profiles and safe actions, and keep voice/model providers replaceable. The current local microphone-and-speaker app is our diagnostics and development surface, not the final product. Use proven open-source frameworks and services for the voice/telephony infrastructure where they help; keep the product behavior, configuration, workflows, and deployment under our project.

## User and constraints
- Primary language for the first prototype: English.
- Hardware target: Lenovo ThinkPad T14 Gen 1 AMD, CPU-only, no CUDA. Verify actual RAM and available disk space before selecting models.
- Cost: local inference should work without recurring inference charges. Optional API providers may include Gemini, Groq, OpenRouter, or Hugging Face, but check current free-tier limits and terms before relying on them.
- Prefer existing, actively maintained projects over writing infrastructure from scratch.
- Prefer permissive licenses (MIT, Apache-2.0, BSD) for core dependencies where practical. Verify licenses separately for code, model weights, voice assets, and dependencies.
- Keep components replaceable: speech recognition, language model/provider, speech synthesis, and business logic should not be tightly coupled.
- Start simple. Do not introduce distributed infrastructure unless measured needs justify it.

## Development path
Start with the smallest working slice and expand it into the product in stages. The first milestone remains a local voice loop:
1. Capture microphone audio.
2. Detect when the user has finished speaking.
3. Transcribe speech.
4. Generate a concise answer.
5. Speak the answer aloud.
6. Allow interruption where practical and cancel queued speech on barge-in.
7. Measure latency, CPU/RAM use, and basic reliability.

The local prototype is an evaluation console, not the final product. After it is reliable, add one explicitly selected live speech-to-speech provider, receptionist workflows, and telephony. Do not treat a standalone provider demo as the deliverable.

## Design principles
- Local-only mode must never contact cloud services.
- Cloud providers are opt-in and clearly configured. Never silently fall back to cloud.
- Use streaming between stages when the chosen components support it.
- For curated FAQs, try deterministic matching and cached/pre-generated answers before invoking an LLM and TTS.
- Keep answers short by default to reduce latency.
- Validate business actions in deterministic code. The model may propose an action, but must not claim it succeeded until the application confirms success.
- Use bounded retries, timeouts, and safe fallback messages.
- Avoid logging secrets or raw audio by default.
- Store only what is needed. SQLite is sufficient for an initial prototype.

## Candidate technologies to evaluate, not assume
- Native real-time speech-to-speech: Gemini Live is the first provider to evaluate because the user has a Gemini API key; compare against OpenAI Realtime if an API account is available. Keep the session behind a provider interface and document current preview/free-tier/data-use constraints.
- Real-time orchestration and phone media: evaluate LiveKit Agents and Pipecat as existing components; do not rebuild media transport, codecs, turn handling, or SIP primitives from scratch without a demonstrated need.
- Speech recognition: faster-whisper, whisper.cpp, or sherpa-onnx.
- Local speech synthesis: Kokoro-82M and Kyutai Pocket TTS, benchmarked on the actual laptop.
- Local LLM: a quantized instruction model through llama.cpp.
- Optional hosted LLMs: Gemini, Groq, OpenRouter, or Hugging Face, subject to current free-tier and privacy constraints.

Do not select a component based only on benchmark claims. Verify current maintenance, supported platforms, model requirements, licenses, and actual end-to-end performance.

## Quality measurements
Record at least:
- Time from end-of-utterance to first audible response.
- Time to first transcript and first generated token/audio chunk where available.
- p50 and p95 latency over repeatable test sets.
- CPU and peak RAM use.
- Speech recognition quality on a small, documented set of test utterances.
- FAQ matching accuracy and cache hit rate.
- Interruption success rate and recovery behavior.

Treat performance targets as hypotheses until measured on the target hardware. Do not report targets as achieved without test results.

## Product milestones after the first prototype
1. Compare local cascade and native Gemini Live in the diagnostics console; measure response timing, turn-taking, interruption, task completion, and failure recovery.
2. Add a provider-neutral voice-session boundary so realtime speech-to-speech and the local STT/LLM/TTS fallback share the same business rules. Keep mode selection explicit; never silently send local audio to a cloud provider.
3. Build our own receptionist product layer: editable business profiles, verified knowledge, safe deterministic tools, caller-message capture, and human handoff.
4. Add persistence, access control, tenant/workspace isolation, privacy and retention controls, call logs, monitoring, and secure deployment configuration before exposing real customer data.
5. Add a browser call simulator and SIP/PSTN transport using a maintained upstream media/telephony framework, then validate with a controlled test line.
6. Add Hindi/Hinglish and additional business profiles using the same provider-neutral evaluation scenarios.
7. Prepare the GitHub release and a small customer pilot only after installation, security, reliability, data handling, costs, and supported telephony are reviewed.

## Out of scope for the first milestone
- Production telephony.
- Kubernetes, microservices, Redis, or a vector database without demonstrated need.
- Training a speech or language model from scratch.
- A full multi-tenant SaaS platform; this remains a later product milestone and must have explicit isolation/security review before launch.
- Promising human-level naturalness or hard latency guarantees before testing.

## Definition of done for milestone 1
- A user can speak into the microphone and hear a spoken response.
- Setup and run instructions work on the target Linux machine.
- The selected components and their licenses are documented.
- Local-only mode can be verified to make no network calls.
- Errors and missing dependencies produce actionable messages.
- A repeatable test procedure reports latency and resource use.
- Known limitations are documented honestly.
