# Local AI Receptionist

A local, English, CPU-first voice assistant prototype for Linux, with a Gemini Live speech-to-speech evaluation path. Gemini Live is selected by default on the diagnostics page for current evaluation; the local listen/transcribe/respond/speak path remains available from the engine menu.

This is a browser voice assistant prototype, not a phone receptionist yet. It does not place or answer phone calls or connect to business systems. The diagnostics page currently selects Gemini Live by default; choosing Local keeps inference on this computer and does not use cloud inference. Model files must be downloaded separately before first local-model use. Runtime model loading uses local paths and does not download models automatically.

## Current architecture

The current diagnostics path has explicit local and Gemini Live endpoints. Shared receptionist policy and approved FAQ facts live outside provider adapters. Local model resources are loaded only on the first local request; choosing Gemini does not initialize Whisper, Qwen, Kokoro, or Smart Turn. Keep provider selection explicit so the active engine can change without coupling business rules to a specific model.

```text
Now: browser diagnostics -> FastAPI media adapter -> explicit provider path
  Local: interim/final Whisper -> FAQ or Qwen -> Kokoro -> browser audio
  Gemini: PCM relay -> Gemini Live speech-to-speech -> browser audio

Current scope: browser diagnostics -> FastAPI media adapter -> explicit local or Gemini Live path. Phone/SIP transport is planned separately.
```

The current app remains a diagnostics and development surface. Its local and Gemini providers are explicit and replaceable; phone-call transport will be evaluated as a later step.

The browser mode is the recommended way to run inside Codex: it uses the computer's microphone and speakers, while the Python backend listens only on `127.0.0.1`. The browser uses echo cancellation and a local speech gate to avoid reacting to brief acknowledgements. In Gemini mode, Gemini's automatic speech detection remains enabled as a fallback for room noise; when the browser detects a completed turn, it signals Gemini to finalize promptly. The user can barge in to stop queued audio.

The installed Faster Whisper model is not a native streaming recognizer. During a turn, the app re-decodes snapshots of the growing audio buffer at a bounded interval to show interim captions. At the end of the turn it decodes the complete utterance for the final transcript. For longer utterances it can generate and synthesize one tentative LLM reply during speech; that audio is reused only when final ASR closely agrees. Curated FAQ replies are matched deterministically, can be pre-synthesized while the caller is speaking, and bypass the LLM. The local streaming session keeps the last four completed user/assistant exchanges in memory for follow-up questions; it does not persist conversation audio or text. Smart Turn v3 checks whether a pause sounds like the end of a thought, with the browser's configurable silence timeout as a safety fallback. The Qwen adapter follows Qwen3's recommended non-thinking sampler settings with a modest presence penalty; `/no_think` selects non-thinking response mode, not a disabled model. The microphone remains active during playback, and caller speech stops the queued reply.

The original command-line mode (`ai-receptionist`) still uses PortAudio directly. Use browser mode if the Codex shell cannot see `/dev/snd`.

## Requirements

- Linux x86_64, Python 3.12 (Kokoro ONNX currently excludes Python 3.14), and a browser that can access the local microphone and speakers.
- A C/C++ toolchain and CMake for a CPU build of `llama-cpp-python` if a compatible wheel is unavailable.
- PortAudio runtime libraries. Fedora package name: `portaudio`.
- About 1 GB of model downloads for the suggested English baseline, plus installed Python dependencies. Runtime memory and speed still need measuring on the target laptop.

The project environment is Python 3.12.14. The shell has no direct sound-device access, so microphone and speaker behavior must be checked in the browser by the user.

## Setup on Fedora

Install Python 3.12 and `uv` using their official installation instructions, then create an isolated environment. The project requires Python 3.12 because the current Kokoro ONNX package metadata excludes Python 3.14.

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
CMAKE_ARGS="-DGGML_NATIVE=on" CCACHE_DISABLE=1 uv pip install -e .
```

The `llama-cpp-python` package builds its CPU backend with the installed compiler/CMake when no matching wheel is available. If installation fails, its build output will identify the missing compiler or library. Fedora's PortAudio package is already installed on the inspected machine; on another system, install the equivalent PortAudio runtime package first. The project declares MIT for its own code; third-party libraries, model weights, and voice assets keep their own separate licenses.

## Download models once

Run these commands while internet access is available. Inference after download uses local files only.

```bash
mkdir -p models/faster-whisper-base.en models
hf download Systran/faster-whisper-base.en --local-dir models/faster-whisper-base.en
hf download Qwen/Qwen3-0.6B-GGUF Qwen3-0.6B-Q8_0.gguf --local-dir models
curl -L --fail --output models/smart-turn-v3.2-cpu.onnx \
  https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx
curl -L --fail --output models/kokoro-v1.0.int8.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.int8.onnx
curl -L --fail --output models/voices-v1.0.bin \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin
```

The chosen Kokoro int8 graph is about 114 MB and the English voice collection is about 28 MB in the upstream release. The upstream Qwen GGUF repository publishes a 639 MB Q8_0 file. Review the model and voice terms before redistribution; model files are excluded from Git. Keep this download step separate from the running assistant: once all assets are present, model loading uses local paths and does not fetch model files.

Smart Turn v3 is an upstream Pipecat CPU ONNX model (about 8.7 MB, BSD-2-Clause). Its Whisper-style feature extractor is reused from Pipecat with upstream license notices preserved. If the Smart Turn model is absent, voice calls keep working with the configured silence timeout fallback. See `src/ai_receptionist/_vendor/SMART_TURN_LICENSE.txt` for the model license.

## Run inside Codex

Start the local web service from the project folder in Codex's local terminal, which shares the browser's `127.0.0.1` connection:

```bash
cd /home/ash/projects/ai-receptionidt/ai_receptionist_starter_files
source .venv/bin/activate
ai-receptionist-web
```

Keep that terminal open while using the diagnostics page. If the page says it cannot connect or shows `ERR_CONNECTION_REFUSED`, first check that this command is still running in the local terminal. A service started in a separate isolated command session may not be reachable from the in-app browser, even when its startup message says it is listening. Restart it in the local terminal above, then reload the page. Do not start a second copy if one is already listening on port `8765`.

Open `http://127.0.0.1:8765/diagnostics` in Codex's in-app browser. Select **Start conversation** and allow microphone access when prompted. Live audio is sent over a loopback WebSocket; it is held in memory for interim/final recognition and not saved. Select **End conversation** to stop the session. The microphone remains active during replies so a caller can interrupt. The service binds to loopback by default and checks browser origins on WebSocket connections. This development service has no user authentication; do not expose it to the network or use it for customer calls.

### Gemini Live cloud mode

Gemini mode is an explicit cloud test and is selected by default in diagnostics. It sends microphone audio and any populated business profile facts to Google; the server keeps the API key and does not send it to the browser. Google states that content submitted through the Gemini API free tier may be used to improve its products. Review [Google's data-use and pricing terms](https://ai.google.dev/gemini-api/docs/pricing) before using it. Use synthetic test details, not customer information. The page displays this notice when Gemini is selected. Data is sent only after you start the conversation; choose Local in the engine menu to keep it on this computer.

Install the optional SDK, copy `.env.example` to `.env`, and add your key to `GEMINI_API_KEY`. Keep `.env` private and do not share the key in chat or commit it. Restart the assistant, confirm **Gemini Live** is selected, then start your own microphone test. You do not need to provide the key until you are ready to connect. The model can be changed with `GEMINI_LIVE_MODEL`. If you serve the test UI from another trusted browser origin, add its exact origin to `RECEPTIONIST_ALLOWED_ORIGINS` in `.env`, comma-separated. This origin allowlist is not a substitute for authentication or TLS in a hosted deployment.

```bash
uv pip install -e '.[gemini]'
cp .env.example .env
```

Gemini Live model access, availability, quotas, terms, and free-tier eligibility can change. This route is for synthetic evaluation only; it does not yet use verified business profiles or deterministic receptionist actions.

### Phone calls (planned)

This prototype currently handles browser voice diagnostics. Phone/SIP connectivity will be introduced as a separate, reviewable production-runtime change.

### Add approved business details

Copy `business_profile.example.json` to `business_profile.json` and fill in only verified facts: business name, time zone, weekly hours, address, contact phone/email, and services. The local profile file is ignored by Git. Local replies pick up edits automatically; Gemini reads the profile when a new conversation starts. Missing values stay unknown and are not filled with guesses. When Gemini Live is selected, populated profile facts are sent to Google with the voice session; Local keeps them on this computer. The current profile is one business per running app; multi-business separation is a later milestone.

`BUSINESS_PROFILE_PATH` in `.env` can point to a different profile file. The default is `business_profile.json`.

### Try callback-message capture

In Gemini Live, ask to leave a callback message or speak with a person. The assistant must explain that live transfer and automatic staff notification are not configured, then offer to store a callback request in the local inbox for someone to review. Before collecting details, it states what will be collected, where it will be kept, how long it will remain, and—because Gemini is cloud-hosted—that voice is processed by Google. It waits for a clear yes before asking for details, reads the name/number/message back, and saves only after another clear yes. Short acknowledgements such as “uh-huh” do not count as consent or final confirmation. Saved messages go to a local SQLite inbox, default to seven-day expiry, and can be deleted from the diagnostics page. No email, text, staff alert, or phone transfer is sent automatically.

Retention is configurable with `CALLBACK_MESSAGE_RETENTION_DAYS` (1–90 days); the database path is `CALLBACK_MESSAGE_DB_PATH`. The database is excluded from Git and created with owner-only file permissions. This local prototype has no staff sign-in and is for synthetic test messages only; do not use it with real callers or treat it as a compliance-ready customer system. Review the current [Digital Personal Data Protection Act](https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023.pdf) and [notified Rules](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf) with qualified counsel before a real deployment.

### Add approved FAQ answers

Edit `business_faq.json` in the project root. Each entry has a list of likely caller phrasings and the approved answer to speak. Start from `business_faq.example.json`, replace every example answer with verified business facts, then copy the entries into `business_faq.json`. Leave it empty (`[]`) until accurate information is available. Changes reload automatically. The FAQ matcher uses a conservative text-similarity threshold; if no answer is a strong match, the LLM path is used instead. It never invents business hours or prices from this file.

## Run from a desktop terminal

```bash
source .venv/bin/activate
ai-receptionist
```

The command-line mode listens directly to the system microphone. Speak after the listening prompt. The assistant waits for the configured quiet interval, processes the turn, and speaks its answer. Use `Ctrl+C` to exit.

Optional environment settings:

| Variable | Default | Purpose |
|---|---:|---|
| `VOICE_SPEECH_THRESHOLD` | `0.012` | RMS threshold for detecting speech; tune for the microphone/room. |
| `VOICE_END_SILENCE_SECONDS` | `0.75` | Quiet duration that ends a turn. |
| `VOICE_MAX_UTTERANCE_SECONDS` | `20` | Maximum captured turn duration. |
| `VOICE_PARTIAL_INTERVAL_SECONDS` | `1.25` | Minimum time between interim transcription attempts. |
| `VOICE_PARTIAL_MIN_SECONDS` | `1.0` | Audio duration required before the first interim transcript. |
| `BUSINESS_FAQ_PATH` | `business_faq.json` | Editable JSON file containing approved caller questions and answers. |
| `BUSINESS_PROFILE_PATH` | `business_profile.json` | Editable, locally ignored JSON file with verified name, hours, contact, and service facts. |
| `CALLBACK_MESSAGE_DB_PATH` | `data/callback_messages.sqlite3` | Local SQLite inbox for confirmed callback messages. |
| `CALLBACK_MESSAGE_RETENTION_DAYS` | `7` | Automatically delete saved callback messages after this many days (1–90). |
| `WHISPER_MODEL_PATH` | `models/faster-whisper-base.en` | Local Whisper model directory. Set to `models/faster-whisper-tiny.en` for faster but less accurate transcription. |
| `WHISPER_COMPUTE_TYPE` | `int8` | CPU quantization mode. |
| `WHISPER_CPU_THREADS` | `4` | CPU threads assigned to ASR and LLM. |
| `SMART_TURN_MODEL_PATH` | `models/smart-turn-v3.2-cpu.onnx` | Local Pipecat Smart Turn ONNX model; if absent, use the browser silence timeout. |
| `LLAMA_MODEL_PATH` | `models/Qwen3-0.6B-Q8_0.gguf` | Local GGUF model file. |
| `KOKORO_MODEL_PATH` | `models/kokoro-v1.0.int8.onnx` | Local Kokoro model file. |
| `KOKORO_VOICES_PATH` | `models/voices-v1.0.bin` | Local Kokoro voice data. |
| `KOKORO_VOICE` | `af_heart` | Kokoro English voice identifier. |
| `MAX_ANSWER_TOKENS` | `48` | Bounds response length. |
| `LLM_TIMEOUT_SECONDS` | `20` | Discards a response if generation takes too long. |

## Privacy and limitations

- Gemini Live is an optional, explicit cloud path; it sends microphone audio to Google only when selected. The API key stays in the ignored local `.env` file. There is no silent local-to-cloud fallback.
- Whisper models must exist at the configured local path; startup errors instead of auto-downloading.
- Do not store API keys or customer audio in this repository. The app prints recognized text and generated answers to the local terminal but does not save audio.
- The browser energy detector still starts speech segments and is sensitive to microphone gain, room noise, and speaker echo. Smart Turn improves end-of-turn choices after pauses, but live false-start and false-stop rates still need measuring on the target microphone.
- Interim captions use repeated decoding with a non-streaming Whisper model. This gives live text but costs CPU and may briefly lag; a native streaming ASR adapter such as Moonshine or a streaming Conformer is a future upgrade after benchmarking.
- Barge-in cancels assistant playback and suppresses future chunks, but work already executing in a synchronous local model cannot always be stopped immediately. The pipeline is full-duplex at the microphone/transport level, not an end-to-end simultaneous speech-to-speech model. It waits for turn confirmation before speaking.
- The speculative LLM reply can compete with ASR for CPU. It is validated against the final transcript and discarded on mismatch, but the performance/quality tradeoff still needs live measurement on the ThinkPad.
- The small LLM may make mistakes; it must not be trusted for business actions. Live session context is bounded and held in memory only; there is no persistent conversation store or verified live-microphone latency/quality benchmark yet.
- Message taking, call transfer, appointment booking, and business-data changes are not implemented. The response prompt tells the model to state that limitation instead of promising those actions.

## M1 verification checklist

On the actual laptop, record the Python, model, and hardware versions, then verify:

1. Microphone input and speaker playback both work.
2. Quiet, short, long, and noisy utterances produce sensible turn boundaries.
3. A fixed English utterance set produces usable transcripts; compare `tiny.en` and `base.en` if memory permits.
4. Repeated prompts produce concise responses and timeout fallback behavior.
5. Kokoro output is audible, and the selected voice is acceptable.
6. Over at least 20 turns, record end-of-speech-to-first-audio latency, p50/p95, CPU use, peak RAM, and failures.
7. Run once with external networking blocked after model downloads and confirm the assistant still works.

The CLI prints per-turn ASR, LLM, TTS, and end-of-speech-to-playback-start timings, then reports first-audio p50/p95 and process CPU/peak resident memory on exit. The browser shows its estimated first-audio time and per-stage timings for each turn. These are application-level estimates, not a microphone loopback measurement of physical sound. Performance targets remain unverified until measured on the ThinkPad.
