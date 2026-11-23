# Product Requirements and Roadmap

## What we are building

Our own open-source AI receptionist that can answer business phone calls. The current browser page is a place to test the assistant, not the finished product. We will keep our product and business features in this project and use maintained voice and phone components where they save us from rebuilding basic infrastructure.

The chosen production direction is LiveKit Agents for call/session lifecycle and SIP/WebRTC transport, with our business policy, profiles, and validated actions remaining project-owned. The local FastAPI browser console remains the current evaluation path. See [`docs/decisions/0002-production-voice-runtime.md`](docs/decisions/0002-production-voice-runtime.md) for the comparison, trade-offs, and migration gate.

## Requirements we have agreed

- Make conversations feel natural, with quick replies and the ability to interrupt the assistant.
- Use hosted voice models for quality and keep a local option for private, offline testing.
- Keep voice providers replaceable so a better model can be tried without rebuilding the receptionist.
- Start with English. Add Hindi and Hinglish after the first voice path works well.
- Design for businesses in India, then allow business-specific languages, information, and behavior.
- Run the first version from the user's Linux laptop; prepare for a reliable hosted server before a customer pilot.
- Keep business answers grounded in information the business has approved. Confirm actions in application code before saying they succeeded.
- Do not expose API keys, silently switch from local to cloud, or save call audio by default.
- Use synthetic examples during development. Add access controls, privacy settings, and recovery before handling real customer calls.

## What we need from the user

**Gemini Live is the current diagnostics default:** the local ignored `.env` file and optional Gemini SDK are configured. Review the on-page notice first; Gemini streams microphone audio to Google, while choosing Local keeps audio on this computer. The user confirms live microphone and timing checks work well. Record actual latency percentiles and CPU/RAM separately before treating the voice milestone as measured. Gemini keeps server-side speech detection enabled as a fallback, while the browser buffers short speech candidates and signals turn completion to reduce false interruptions and endpoint delay. Assistant interruptions require 350 ms of sustained speech, and post-interruption silence wait is capped at 400 ms; normal turns use the adjustable 0.50-second default. Both voice WebSockets validate the page's exact origin; by default they allow localhost on the configured port. The response language defaults to English; set `ASSISTANT_ALLOWED_LANGUAGES=English,Hindi` in `.env` to allow only English and Hindi. Language restriction for native audio remains prompt-level, not a hard guarantee. Timing shows first-chunk arrival, estimated browser output start, and per-setting p50/p95 after enough turns; these are browser estimates, not physical speaker-loopback measurements.

**Before placing real phone calls:** choose an India-supported phone/SIP provider and complete any required account verification. This is a later decision; no phone number is connected yet.

## Roadmap

| Stage | Work | Status |
|---|---|---|
| 1. Voice baseline | Keep the working Gemini Live and local paths available; record real timing and behavior to compare future changes. | Live use is confirmed; timing and edge-case measurements are incomplete. |
| 2. Receptionist behavior | Maintain approved business facts, FAQs, and safe callback capture independently of the voice framework. | Profile/FAQ and local confirmed-message inbox exist; verified facts and live callback workflow check remain. |
| 3. Production voice runtime | Move audio/session handling to LiveKit Agents with its Gemini Live integration while preserving our own receptionist logic and the current path for comparison. | Optional agent entrypoint and callback tools are implemented; needs LiveKit Cloud URL/API credentials and a real session test. |
| 4. Browser demo and repeatable evaluation | Run the same receptionist behavior through the new runtime and test realistic conversation scenarios. | Not started. |
| 5. India phone-call proof | Check provider eligibility/terms, then connect one controlled inbound number using SIP and test call failures and hang-ups. | Not started; no phone provider or number chosen. |
| 6. India languages and model comparisons | Test Hindi/Hinglish and verify that voice models can be changed without rewriting receptionist behavior. | Not started; do this before a pilot if the target business needs these languages. |
| 7. Safe pilot and release | Add sign-in, business separation, secrets, retention, monitoring, recovery, cost controls, and complete privacy/license review before real customer calls. | Not started. |

## What already works

- A local browser conversation can listen, detect pauses, answer, and play speech.
- The local path uses speech recognition, a small language model, and Kokoro speech output.
- It can show turns and timing, interrupt queued speech, and use approved FAQ answers when they match.
- The roadmap and open-source research are recorded in [ROADMAP.md](ROADMAP.md) and [docs/research/open-source-adaptations.md](docs/research/open-source-adaptations.md).

The local path has not yet been measured on enough real microphone turns to claim production quality. Phone calling, message delivery, appointments, and customer deployment do not exist yet.
