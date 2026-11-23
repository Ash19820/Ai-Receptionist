# AI Receptionist Roadmap

Status labels: `Not started`, `In progress`, `Blocked`, `Done`.

## Product target

Build and own a GitHub-ready AI receptionist that can be deployed for real businesses and eventually sold. The current browser diagnostics app is our development and evaluation console, not the final deliverable. We will own the business profiles, receptionist rules, safe tools, customer workflow, and product configuration. We will integrate maintained open-source voice/telephony components and hosted/local model providers behind replaceable interfaces instead of rebuilding commodity infrastructure or replacing our whole project with another vendor's app.

### Voice implementation direction

- Evaluate Gemini Live as the first native speech-to-speech engine in our own diagnostics app, since the user already has a Gemini API key. Compare its naturalness, task success, turn completion, interruptions, and timing against the existing local STT → LLM → Kokoro path.
- Add it as an explicit server-side voice-session provider. Keep API keys off the browser, disclose the selected provider and data path, use synthetic test details until cloud data terms have been reviewed, and never fall back from local to cloud automatically.
- Preserve the local cascade as an explicit offline/development option. It is a fallback mode with a different quality/latency profile, not something we should claim is identical to full-duplex Live.
- Connect browser and phone transports to the same business workflows through the selected maintained realtime framework before adding more custom transport logic. SIP/PSTN, codec handling, call recording, and provider-specific telephony remain transport/deployment adapters.

## Roadmap sequencing review — 2026-11-15

The destination was right, but the old ordering kept too much custom audio/WebSocket work ahead of the already-selected production voice framework. LiveKit Agents currently documents a Gemini Live integration, session orchestration, SIP telephony, and end-to-end agent simulations. Move the small LiveKit migration ahead of adding more custom voice transport features; preserve the current direct Gemini page as a working comparison until the new path reaches feature parity.

1. **Finish a focused current-path baseline.** Keep Gemini Live selected; record user checks and enough timing/error data to compare paths. Do not block framework work on a large latency study, but keep real-call quality and reliability measurements as a pre-pilot gate. Complete the pending callback voice check with synthetic details.
2. **Keep receptionist behavior project-owned and provider-neutral.** Retain the business profile, FAQ, consent/confirmation workflow, and storage rules outside the media framework. The local callback inbox is only a manual review queue; do not claim staff contact, notification, or transfer.
3. **Migrate the session/media runtime to LiveKit Agents with the Google Gemini plugin.** The optional worker entrypoint and existing callback tools are now in the project. Next, configure credentials and reproduce a browser conversation with current Gemini speech-to-speech behavior. Keep the direct Gemini path available during comparison; do not rebuild model functions or business actions in the transport layer. Google's current LiveKit integration docs list Gemini Live support; LiveKit's `AgentSession` owns voice-session orchestration.
4. **Add repeatable conversation evaluation, then the browser call demo.** Test greeting, FAQ, consent, declined save, interruptions/backchannels, disconnects, and session restart using deterministic tool/state checks and audio simulations where available. Treat simulations as regression coverage, not proof of human naturalness.
5. **Check India phone-number/SIP eligibility and provider terms before committing, then run one controlled inbound phone call over LiveKit SIP.** A browser demo alone does not prove PSTN codecs, call routing, hang-up handling, or local provider eligibility.
6. **Add Hindi/Hinglish and model comparisons for the actual target business before a customer pilot.** Keep the selected model/provider configurable; measure each language separately.
7. **Before any real-customer pilot, finish access controls, business isolation, retention/deletion, secret handling, monitoring, recovery, costs, and data-flow review.** Keep synthetic data for framework and SIP tests until that gate is met.

Sources reviewed for this order: LiveKit's [Gemini Live integration](https://docs.livekit.io/agents/models/realtime/gemini/), [AgentSession overview](https://docs.livekit.io/agents/logic/sessions/), [SIP setup](https://docs.livekit.io/telephony/start/sip-trunk-setup/), and [agent simulations](https://docs.livekit.io/testing/simulations/). This is an implementation plan, not a claim that LiveKit or the current app is production-ready.

## M0: Repository and hardware reconnaissance
**Status:** Done

- [x] Inspect the existing repository and report its structure and current behavior.
- [x] Confirm OS, CPU, RAM, disk space, Python/runtime versions, and audio devices.
- [x] Identify existing project conventions and tests.
- [x] Research only the decisions needed for the first prototype.
- [x] Present a short recommendation with trade-offs before committing to a stack.

**Exit criteria:** A concise architecture decision record, setup plan, and measurable first-milestone scope.

## M1: Minimal English voice loop
**Status:** In progress

- [ ] Microphone capture works.
- [ ] Voice activity / end-of-turn detection works acceptably.
- [ ] Speech is transcribed.
- [ ] A concise answer is generated.
- [ ] Answer is spoken through local audio output.
- [ ] Configuration clearly selects the local mode or an explicitly opted-in hosted mode.
- [ ] Local-only mode makes no network calls.
- [ ] Hosted mode documents provider, transmitted audio/text, quota limits, and data-use terms; no silent provider fallback.
- [ ] Setup instructions are tested on the target machine.
- [ ] Latency and CPU/RAM measurements are recorded.

**Exit criteria:** Repeatable end-to-end voice interaction with documented limitations and measurements.

### M1 checkpoint — 2026-10-24

- The local backend loaded the Faster Whisper base.en, Qwen3-0.6B Q8_0, and Kokoro int8 models successfully. It was stopped at the user's request after testing.
- Three end-to-end `/api/turn` smoke runs used the same synthetic eSpeak prompt: “What time do you open today?” ASR returned the exact prompt each time, and the LLM gave a safe response about unknown business hours.
- Exploratory mean stage timings: ASR 1.10s, LLM 1.58s, TTS 3.51s, total 6.20s. Total time ranged from 4.91s to 6.96s across three runs. This is too small and synthetic a sample for p50/p95 claims.
- Kokoro produced 24 kHz mono speech, 3.48s long for the first reply. Naturalness, pronunciation, and pacing still need a human listening check.
- All 9 unit tests and Python compilation passed. No live microphone turn or physical audio-device check was completed; the shell has no `/dev/snd` device.
- The browser diagnostic page is served by the app at `/diagnostics`. Its end-to-end test records a short prompt, displays transcript and answer, reports ASR/LLM/TTS timing, and plays the generated response.
- Python 3.12.15 was restored under `/tmp/ai-receptionist-python` to satisfy the existing virtual environment link. Recheck that path before resuming because temporary files may not persist.

### Resume M1

1. Confirm the Python 3.12 runtime and model files are still present, then start `.venv/bin/ai-receptionist-web`.
2. Open `/diagnostics`, record several live microphone prompts, and review transcript accuracy and stage timings.
3. Listen to Kokoro output and note naturalness, pronunciation, and pacing.
4. Complete at least 20 live turns; record end-of-utterance-to-first-audio p50/p95, CPU/RAM, turn-boundary failures, and noisy/short-turn behavior.
5. Verify local-only behavior with outbound networking blocked after model downloads; separately test any explicitly selected cloud mode with synthetic phrases first.

### M1 diagnostics update — 2026-10-25

- Reworked `/diagnostics` around a call-style session using the existing local streaming endpoint. One click starts a persistent microphone session; the browser ends turns after a configurable 0.5–1.5 seconds of silence (0.50 seconds by default), plays replies automatically, and allows barge-in while the assistant is replying.
- The page shows live/interim transcripts, each completed user/assistant turn, microphone activity, and backend time-to-first-audio, alongside browser, speaker, and service checks.
- The updated page loaded in the browser and its WebSocket service check succeeded. The call flow itself still needs live microphone use and human review; this update has not yet been measured across a 20-turn sample.
- The project environment was reconnected to the persistent Codex Python 3.12.14 runtime because the earlier `/tmp` Python 3.12.15 path had disappeared. Model-library imports succeeded and the local web server started.

### M1 open-source integration update — 2026-10-25

- Researched Pipecat's open-source Smart Turn v3 endpointing strategy and adapted its BSD-2 licensed CPU ONNX model plus upstream Whisper-style feature extraction. The adapter keeps an eight-second audio window and runs locally through ONNX Runtime; the browser silence timeout remains the fallback. Source and license details are in `docs/THIRD_PARTY_NOTICES.md` and `docs/research/open-source-adaptations.md`.
- Removed the prompt's fixed unknown-hours example that was anchoring repeated replies. The local Qwen chat call now receives up to four recent user/assistant exchanges, drops invalid roles, bounds message size, and selects Qwen3 non-thinking mode with the upstream recommended sampler settings plus a modest presence penalty.
- Added a guard against promising message taking, call transfers, booking, or data changes before those deterministic features exist. One local Qwen follow-up smoke check used conversation history and correctly said it could not take messages; this is one generated example, not a broad quality evaluation.
- All 15 focused unit tests pass, including audio-window behavior and a smoke inference through the downloaded Smart Turn model. Python compilation and browser JavaScript syntax checks pass. A synthetic eSpeak utterance measured Smart Turn inference at about 140–160 ms and crossed the completion threshold after roughly 0.5 seconds of trailing silence; that synthetic result is exploratory only.
- The updated backend is running at `http://127.0.0.1:8765`, and `/diagnostics` is open with its local assistant connection check passing. No microphone permission was accepted; live call behavior and human TTS review remain yours to test.

### Gemini Live evaluation path — 2026-10-25

- Added a clearly labeled Gemini Live choice to the diagnostics page; local remains the default and uses its existing local-only endpoint.
- Added a server-side Gemini WebSocket relay using the Google GenAI SDK, with the API key read from a local ignored `.env` file and never exposed to the browser. Gemini audio chunks use the Live API's 16 kHz input and 24 kHz PCM output path.
- Added an on-page notice explaining that Gemini sends microphone audio to Google and that Google may use free-tier content to improve its products. Audio is only sent after the user selects Gemini and starts the session.
- The optional SDK and local `.env` key were subsequently configured. The user ran live microphone turns: input transcription and generated replies worked, but spoken replies cut off before finishing.
- Diagnosed the initial cutoff: the GenAI SDK receive iterator ends after a model turn, while the relay treated its end as the end of the whole WebSocket session. The relay now reopens the receive iterator for later turns and guards against an empty iterator. Two focused regression tests cover multi-turn receives and empty receives.
- All 18 unit tests and Python compilation pass. These checks do not establish live audio completion, voice quality, or latency.
- The open diagnostics page still showed `Connection closed` after its old-server turns. The server was restarted with the fix loaded. Next: the user should refresh and make another self-run microphone test; if speech still cuts off, record whether the page says `Interrupted · listening` or `Connection closed` to distinguish barge-in from a connection failure.
- Follow-up to the user's report that replies stop on "uh-huh" or "okay": Gemini's server-side VAD cancels generation whenever it detects speech, regardless of the browser's noise threshold. Gemini mode now disables automatic VAD and uses browser-side activity signals, buffers short candidate utterances, ignores candidate gaps up to 120 ms, and requires 550 ms of sustained voice before interrupting playback (80 ms while idle). The local path uses 300 ms while the assistant is speaking. This should reduce acknowledgement-triggered cutoffs while preserving buffered speech at the start of intentional interruptions; the user needs to verify behavior live. Tradeoff: barge-in now takes longer to trigger, and simple energy detection still cannot reliably classify every spoken acknowledgement or noise.
- Language drift follow-up — 2026-10-31: added `ASSISTANT_ALLOWED_LANGUAGES` (default `English`) and a Gemini instruction that restricts replies to the configured list, treats brief acknowledgements/fillers as non-language-selection evidence, and requires substantive speech or an explicit request before switching among allowed languages. This is prompt-level steering, not a hard guarantee; verify live with acknowledgements and unsupported-language input. Gemini native-audio models otherwise adapt languages automatically; see [Gemini Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities) and [best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices).
- Follow-up to first-turn silence — 2026-10-31: browser audio output is now created and resumed directly from the Start button gesture, before waiting for the WebSocket or microphone permission. Playback also resumes the audio context when the first chunk arrives. This addresses an autoplay-policy timing race; the user still needs to verify the first reply with their microphone and speakers.
- The user confirmed the first reply is still silent after that change. Added visible per-turn audio counters (received, queued, and finished chunks) plus playback errors to the diagnostics page so the next user-run test can distinguish missing Gemini audio from browser playback failure. This is still unresolved pending those counters and a targeted fix.
- Latency experiment — 2026-10-31: added per-turn first-audio arrival time, estimated browser output start using the Web Audio output timestamp, and session-only p50/p95 summaries grouped by silence-wait setting. The silence wait is configurable from 500–1500 ms and now defaults to 500 ms (previously 600 ms), reducing the browser's post-speech endpoint delay by 100 ms. Compare 500 ms with 600 or 850 ms if the shorter wait cuts off natural pauses. These are estimates from user-run calls, not yet measured or validated on a microphone; model and network response time remain additional latency.
- Barge-in latency adjustment — 2026-10-31: reduced sustained-speech confirmation before stopping assistant playback (Gemini 550→350 ms; local 300→250 ms). After an interruption, the browser now ends the user's turn after up to 400 ms of silence, while normal turns keep the configured wait. This should shorten barge-in reply delay by about 300 ms in the browser; user should confirm it still ignores short acknowledgements and background noise.
- Standards review — 2026-10-31: confirmed the configured `gemini-3.8-live` model is Google's current default recommendation for low-latency voice, and the browser emits 20 ms audio chunks as recommended. Added exact-origin checks to both voice WebSockets to reduce cross-site use of the local assistant. Unit, compile, dependency-consistency, and browser-script syntax checks pass. Still required before production: auth/TLS, HTTP abuse controls, Gemini session recovery/compression, real microphone latency/quality measurements, and telephony integration.
- Architecture foundation — 2026-10-31: moved receptionist response policy and FAQ matching out of model-adapter code, and made the local ASR/LLM/TTS stack lazy so Gemini-only sessions do not load unused local models. Added lifecycle tests. Selected LiveKit Agents as the future session/SIP runtime after researching its Gemini plugin, AgentSession, worker lifecycle, and SIP support; kept Pipecat as the alternative if a measured need favors its transport/frame pipeline. Decision and trade-offs are in `docs/decisions/0002-production-voice-runtime.md`. The current diagnostics backend remains the browser test path; LiveKit integration waits for M1 voice measurements and LiveKit server credentials.
- Framework decision note — 2026-10-31: current LiveKit docs describe adaptive interruption handling for backchannels, but specifically say the realtime client-side gate is not compatible with Gemini Live's model-controlled turn signaling. Avoid adopting it as a drop-in. A LiveKit audio turn detector can replace Gemini's automatic activity detection, while adaptive gating needs a supported setup/provider; evaluate that integration separately before production.
- Framework research update — 2026-10-31: LiveKit Agents supports Gemini Live and can use its own turn detector when Gemini's automatic VAD is disabled. LiveKit's adaptive interruption filter is intended to reject backchannels/noise and its false-interruption handling can resume speech after silence, but its current docs also warn that models using their own turn signals, including Gemini Live, are not compatible with the adaptive client-side gate. Treat that combination as unverified until a small integration proves it. With direct Gemini VAD, genuine interruption cancels the response; continuing afterward must be implemented by generating a continuation. See the official [Gemini Live integration](https://docs.livekit.io/agents/models/realtime/gemini/), [adaptive interruption documentation](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/), and [Gemini VAD guidance](https://ai.google.dev/gemini-api/docs/live-api/capabilities).
- Hybrid endpointing and first-audio guard — 2026-10-31: user-reported reply delay raised a possible false-silence issue. The browser's energy gate can keep a turn open when background sound remains above threshold. Gemini now retains its automatic VAD as a fallback, and the browser sends the documented `audio_stream_end` signal when its own 500 ms endpoint fires. A code review also found that the browser did not mark Gemini as busy until response text arrived; room noise could start a phantom second turn and reset the first reply's playback counters while audio was still pending. It now marks the request pending at turn end and waits for audio playback before treating background energy as an interruption. Candidate audio is bounded to five seconds. The diagnostics page identifies text-without-audio and playback stages. This follows Google's hybrid VAD guidance; the user must recheck latency, background noise, backchannels, interruptions, and first-reply playback before marking M1/M2 validated. The reported 8-second turn showed zero audio chunks, so VAD delay may not be the only issue.

### Local server connection incident — 2026-11-15

- **Symptom:** The in-app browser showed `ERR_CONNECTION_REFUSED` for `http://127.0.0.1:8765/`, even though the assistant process had printed that it was listening.
- **Cause:** The server was launched from an isolated command session that did not share the in-app browser's loopback connection. This was a runtime/terminal-context mismatch, not a Python syntax error or a missing dependency.
- **Resolution:** Start `ai-receptionist-web` in Codex's local terminal from the project folder, keep that terminal open, and reload `/diagnostics`. The user confirmed the page worked after the server was run in that terminal.
- **Prevention:** README startup instructions now name the local terminal and give the recovery steps. Check for an already-running server before starting another copy. If this returns, verify the terminal context and process before changing application code.
- **Roadmap impact:** Server reachability is restored. M1 remains in progress until live microphone turns, playback quality, latency, and resource measurements meet its exit criteria.

### Live voice check-in and engine choice — 2026-11-15

- The user confirms live microphone and timing checks are working well. This validates that the diagnostic path and timing display are usable; no numeric latency, CPU, or memory results were supplied, so M1 remains in progress until those measurements are recorded.
- Follow-up live check — 2026-11-15: the user reports the assistant continues speaking when they say a short “uh-huh” backchannel. Record this as a pass for that specific scenario; other noise and deliberate-interruption cases remain unverified.
- Gemini Live is now preselected for new diagnostics sessions, as requested. The local path remains explicitly selectable. Both paths stay behind separate provider endpoints and share project-owned response policy, allowing the active voice engine to change without rewriting receptionist behavior.
- Next M2 work: validate short acknowledgements, background noise, a deliberate interruption, a brief user turn, and normal turn completion. Record whether each event interrupts playback, transcript accuracy, first-audio delay, and any stuck or missing audio. Keep the server-side Gemini turn handling for now: current LiveKit guidance says its adaptive interruption gate is incompatible with Gemini Live's own turn signals, so do not bolt it onto the current path. Revisit that gate with a supported client-side turn detector during the LiveKit migration.
- Code-review finding — the diagnostics browser currently treats sound above its speech threshold for 350 ms as an interruption, stops queued playback, and relies on Gemini to handle the resulting turn. There is no transcript-aware false-interruption recovery that resumes the original reply. Avoid an unmeasured threshold or replay change: a short genuine correction could otherwise be delayed or spoken over. Use the controlled tests above to establish whether noise/backchannels still cause unwanted stops before selecting a recovery design.
- Source review: [LiveKit adaptive interruption handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/) and [Gemini Live best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices).

### Rapid conversation restart incident — 2026-11-15

- **Symptom:** A new call-style conversation could fail when started soon after ending the previous one.
- **Cause:** The previous WebSocket's delayed `close` event used shared global session state. If it arrived after a new microphone stream had started, it could stop that new conversation. Delayed audio callbacks and an audio-wait timer could also update the new session's status or counters.
- **Fix:** Each conversation now has a generation ID. WebSocket messages, close/error callbacks, queued playback, and playback completion callbacks are ignored once they belong to an older generation. Session shutdown clears its pending timer and microphone candidate state; a new session resets first-reply counters and turn state.
- **Verification:** All 25 Python tests pass, and the diagnostics page's inline JavaScript passes `node --check`. A quick stop/start test in the browser is still needed to confirm the user-visible recovery.

### Structured business profile slice — 2026-11-15

- Added a blank, operator-owned JSON profile for business name, timezone, weekly hours, address, phone, email, and services. The example contains no invented business information; the live profile is ignored by Git.
- Runtime validation rejects unknown fields and excessive input, preserves the last valid profile on malformed edits, and reloads changes without restarting the server. Missing values stay absent.
- The same bounded approved facts are provided to both the local responder and Gemini Live. The diagnostics notice and README now disclose that Gemini sends populated profile facts to Google; the existing FAQ fast path remains separate.
- Validation uses explicit field/type/size constraints in the standard library rather than adding a validator dependency; the data shape follows the purpose described in the [JSON Schema 2020-12 guide](https://json-schema.org/learn/getting-started-step-by-step).
- All 32 Python tests, Python compilation, profile JSON parsing, and diagnostics browser-script checks pass.
- Remaining M3 work: fill the profile with verified facts when available, evaluate FAQ match accuracy, and build message/handoff workflows. Multi-business separation is not implemented.

### Provider direction update — 2026-10-25

- The user clarified that hosted inference is acceptable and has free Gemini, OpenRouter, and Groq API keys. Keep local mode as an explicit option and add any cloud provider as a separate explicit mode; never silently route local failures to a cloud service.
- Reviewed the user's three receptionist repositories and documented their actual stacks, license and fit in `docs/research/open-source-adaptations.md`. None had been cloned or run. Helix is the closest architectural fit for a future PBX/handoff milestone; AIReceptionist and Aiva depend on different hosted services.
- Proposed next experiment: compare current local cascade against Gemini Live audio-to-audio for turn-taking and naturalness, beginning with synthetic prompts. Gemini's free tier indicates audio data may be used to improve Google products; live microphone testing should wait for the user to review that data path. Exact model quota is account-specific.
- Gemini's key remains local in the ignored `.env` file; it was verified as present without displaying its value. Do not request or store API keys in chat.

### Product ownership clarification — 2026-10-25

- The end goal is our own deployable receptionist project for GitHub and a later real-customer pilot, not just a Gemini demo or a third-party receptionist fork. Keep our repository and product identity as the home for the work.
- Treat other repositories as sources for proven components and implementation patterns. Before adapting code, inspect its license and dependency/asset licenses; do not combine incompatible copyleft code into our project by accident.
- Keep the current browser diagnostics console and local assistant as evaluation tools. Add a Gemini Live path inside this project behind an explicit provider boundary, then build business profiles, deterministic actions, human handoff, persistence, phone transport, and deployment/security controls in stages.
- Real customer deployment and sale are later exit criteria. They require measured call quality, secure tenant/data separation, reliable business-action confirmation, retention controls, operational monitoring, stable hosting, and a supported phone route; a successful model demo alone is not launch readiness.

## M2: Responsiveness and interruptions
**Status:** In progress — implementation exists; validation waits for M1 live review

- [x] Stream microphone PCM to the local backend and show interim transcripts during speech.
- [x] Prepare one speculative LLM response and speech audio during longer turns; validate it against final ASR before use.
- [x] Send Kokoro output in sentence chunks and cancel queued playback on barge-in.
- [x] Add a local FAQ bypass and pre-synthesize likely answers while the caller is speaking.
- [ ] Measure time to first response audio and p50/p95 latency on live microphone turns.
- [ ] Tune false barge-ins, noisy speech, short turns, and final transcript accuracy on the target laptop.

**Exit criteria:** Repeatable tests demonstrate acceptable turn-taking and no stuck playback.

## M3: Business profile and FAQ fast path
**Status:** In progress

- [x] Add editable FAQ JSON, deterministic matching, confidence/ambiguity checks, and an LLM fallback.
- [x] Add a bounded cache for pre-synthesized curated replies.
- [ ] Fill in verified business details and measure FAQ match accuracy with real phrasing.
- [x] Expand the editable profile to include structured business name, hours, contact details, and services.

**Exit criteria:** FAQ responses are measurably faster without unsafe guessing.

## M4: Caller messages and human handoff
**Status:** In progress — safe local callback queue implemented; live voice check and staff notification/transfer remain

- [x] Capture a caller message only after explicit consent, read it back, and require a separate clear confirmation before saving.
- [x] When a caller asks for a person, explain that live transfer/automatic notification is unavailable and offer the consent-based local callback inbox.
- [ ] Add an actual operator notification or call-transfer path after a destination and provider are selected.
- [x] Store only caller name, callback number, and a short message in local SQLite.
- [x] Add configurable 1–90 day automatic retention (7 days by default), local deletion controls, and privacy notes.
- [x] Test declined/missing consent, missing final confirmation, invalid details, expiry, and duplicate submissions.
- [ ] Run a user-led Gemini voice check with synthetic details: permission declined, ambiguous “uh-huh,” clear consent, corrected read-back, declined save, and confirmed save; check that the saved item appears and can be deleted from the page.
- Architecture follow-up: the model may offer a callback, but it must not say a person was contacted. The response now distinguishes “saved in the local inbox” from staff notification or transfer, which is not configured. Keep a real destination/provider decision in the later telephony milestone.

**Exit criteria:** The live voice workflow respects consent and confirmation, messages are stored reliably and can be deleted/expire, and the assistant never falsely claims delivery. Staff notification/transfer stays a separate step.

- Architecture basis: Gemini Live function calls are executed by application code and answered with tool responses, so the server owns consent checks and persistence instead of trusting the model's claim. See Google's [Live API tools guide](https://ai.google.dev/gemini-api/docs/live-api/tools).
- Privacy basis: collect a narrow set of caller details, state the purpose and retention before collection, and keep this prototype limited to synthetic testing. Review the [DPDP Act](https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023.pdf) and [notified Rules](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf) before any real deployment; this prototype makes no compliance claim.

### LiveKit runtime migration — 2026-11-15

- Added an optional `livekit-agents[google]` dependency and a separate worker entrypoint at `src/ai_receptionist/livekit_agent.py`. The existing FastAPI diagnostics, direct Gemini route, and local option remain in place for comparison.
- The worker uses LiveKit `AgentSession`, Gemini 3.8 Live, project-owned business instructions/profile, and the same deterministic callback state machine. Consent and final save are still checked against final caller transcripts before local SQLite persistence.
- Added environment validation for the LiveKit URL/key/secret plus Gemini key, bounded model/voice selection, and one shared language-name allow-list for both Gemini paths. Updated the Gemini SDK range to match the current LiveKit Google plugin dependency. LiveKit Agent framework/plugin source uses Apache-2.0; service terms remain separate.
- Installed `livekit-agents` 1.8.12 and its Google plugin in the project virtual environment. Verified the agent's three callback tools register, constructed the Gemini realtime model and `AgentSession` without making a network call, and confirmed the LiveKit CLI resolves the worker's `server` entrypoint.
- Automated verification: 49 Python tests, Python compilation, dependency check, direct Gemini config parsing with google-genai 3.3.0, CLI entrypoint discovery, SDK model/session construction without a network call, and concurrent SQLite initialization.
- **Not yet verified:** a LiveKit Cloud connection or browser conversation. The current `.env` has the Gemini key configured, but no `LIVEKIT_URL`, `LIVEKIT_API_KEY`, or `LIVEKIT_API_SECRET`; the LiveKit CLI also still needs to be installed. Keep using the current diagnostics path until the worker's Agent Console session has been tested with synthetic prompts.

## M5: Hindi/Hinglish language profile
**Status:** Not started

- [ ] Define a language-profile interface.
- [ ] Evaluate suitable ASR and TTS options on real test phrases.
- [ ] Add normalization, pronunciation, and response-style tests.
- [ ] Measure quality and latency independently for each language.

**Exit criteria:** Language can be selected explicitly and quality limitations are documented.

## M6: Telephony integration
**Status:** Not started

- [ ] Choose SIP/PSTN provider based on cost, availability, and local requirements.
- [ ] Validate audio codec and sample-rate conversion.
- [ ] Handle connection failures, silence, hang-up, and interruptions.
- [ ] Make cloud/network dependencies explicit.
- [ ] Test with a controlled number before any public rollout.

**Exit criteria:** A controlled end-to-end phone call works, with documented operational costs and failure handling.

## M7: Deployable customer pilot
**Status:** Not started

- [ ] Complete business-specific profiles and deterministic receptionist tools.
- [ ] Add authentication, workspace/tenant isolation, credential management, and least-privilege provider configuration.
- [ ] Add persistent call outcomes and operational logs with explicit recording/retention controls; do not store raw audio by default.
- [ ] Document secure single-server deployment, updates, backups, monitoring, recovery, provider costs, and data flows.
- [ ] Review dependency/model/voice licenses and customer-data terms for every enabled provider.
- [ ] Run controlled pilot calls and verify failure handling before inviting real customers.

**Exit criteria:** A fresh install can be deployed securely, configured for one business, observed, updated, and recovered by its operator; the controlled pilot meets measured quality and reliability requirements.

## Decision log

Record each major decision with:
- Decision and date.
- Options considered.
- Evidence or benchmark.
- Trade-offs and license implications.
- Conditions that would trigger revisiting the decision.

## Current rule
Keep the active voice-quality work focused and measurable. The product milestones are the intended destination, not a claim that later capabilities already work. Use the roadmap to sequence delivery; only mark a milestone done when its exit criteria are met and evidence is recorded.
