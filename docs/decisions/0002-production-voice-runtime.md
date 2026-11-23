# Decision 0002: Production voice runtime

**Status:** Accepted; an optional LiveKit/Gemini agent entrypoint is implemented. A credentialed session and browser test are still pending.

## Context

The current FastAPI WebSocket routes are a useful local evaluation console. They also own audio transport, turn detection, cancellation, transcript updates, and response orchestration. That makes them unsuitable as the long-term phone-call runtime: telephony, reconnects, worker scaling, and call lifecycle would otherwise become more custom code inside one web module.

The product must keep its own receptionist rules and business data while allowing the phone/media layer and voice models to change independently.

## Decision

- Keep the existing FastAPI browser diagnostics and local cascade as development/evaluation tools. Add the LiveKit agent as a separate, optional worker; do not replace the working direct-Gemini path until the new path reaches feature parity.
- Use **LiveKit Agents** as the next production voice runtime. Use its `AgentSession` for conversation/media orchestration, `AgentServer` jobs for call lifecycle and scaling, and SIP trunks/dispatch rules for phone transport. Its Google plugin supports Gemini Live; a phone participant and a browser/WebRTC participant can enter the same room/session model.
- Keep product-owned behavior in this repository: business profiles, approved facts, response policy, deterministic tools, tenant boundaries, consent, and retention rules. Treat LiveKit as the voice runtime and transport, not the receptionist's source of truth.
- Keep provider adapters behind narrow interfaces and choose the provider explicitly. No silent Local-to-cloud fallback.
- Do **not** add Pipecat and LiveKit together. Re-evaluate Pipecat if custom audio-frame processing, its transport/serializer breadth, or a validated India-specific integration makes it a better fit. At present, adding two orchestration frameworks would duplicate call lifecycle and turn handling.
- The first LiveKit slice is `src/ai_receptionist/livekit_agent.py`: one `AgentSession`, Gemini Live, the existing approved profile, and the deterministic callback workflow. Validate it in the LiveKit Agent Console with synthetic details before migrating the diagnostics UI. Add SIP only after this browser session behaves correctly.

## Target shape

```text
Phone/SIP provider ─┐
                    ├─> LiveKit room + one AgentSession per call
Browser/WebRTC ─────┘             │
                                  ├─ receptionist policy + business profile
                                  ├─ verified, permission-checked tools
                                  └─ replaceable voice-model adapter

FastAPI control plane: configuration, business administration, diagnostics,
health, and later authenticated call/business APIs.
```

Each call gets isolated session state. Business records and action results live in application storage with tenant checks; the model receives only the context needed for the current call. Model output alone never confirms an action.

## Trade-offs and constraints

- LiveKit supplies maintained realtime sessions, WebRTC, SIP integration, and agent-worker lifecycle, but a phone carrier/number and a LiveKit server are still required. SIP support does not guarantee a provider can issue or verify an Indian number for this user; validate country coverage, KYC, pricing, and inbound/outbound requirements separately.
- LiveKit Cloud is the simplest operational path but is hosted and usage-priced. Self-hosting gives more control but adds media-server operations and network requirements. Decide after the browser/WebRTC slice, before buying a number.
- Gemini Live's model-controlled turns are the simplest current voice path. LiveKit's adaptive interruption gate cannot simply be layered on top of model-controlled Gemini turns. If acknowledgements/noise remain a problem, evaluate framework-controlled turn detection as a deliberate alternative and compare it on the same voice test set.
- Pipecat remains a credible alternative with a broad pipeline, provider, and transport ecosystem. Do not select it only for a feature list; compare a running call prototype against the same success criteria before changing the runtime decision.

## Required configuration for the first LiveKit slice

For the credentialed browser session, configure `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`, plus the existing `GEMINI_API_KEY`. Install `uv pip install -e '.[livekit]'` and the LiveKit CLI. Keep secrets in the ignored `.env` file or deployment secret store. These credentials are not needed for the current direct-Gemini diagnostics test.

## Sources reviewed

- [LiveKit Agents overview](https://docs.livekit.io/agents/)
- [LiveKit AgentSession](https://docs.livekit.io/agents/logic/sessions/)
- [Gemini Live with LiveKit](https://docs.livekit.io/agents/models/realtime/gemini/)
- [LiveKit SIP trunk setup](https://docs.livekit.io/telephony/start/sip-trunk-setup/)
- [LiveKit turn handling](https://docs.livekit.io/agents/logic/turns/)
- [LiveKit Agent Console](https://docs.livekit.io/testing/agent-console/)
- [LiveKit Agent simulations](https://docs.livekit.io/testing/simulations/)
- [Pipecat framework](https://github.com/pipecat-ai/pipecat)
