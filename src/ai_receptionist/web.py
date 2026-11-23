from __future__ import annotations

import asyncio
from base64 import b64encode
from contextlib import asynccontextmanager
from dataclasses import asdict
from difflib import SequenceMatcher
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse
from dotenv import load_dotenv
import numpy as np
import soundfile as sf
import uvicorn

from ai_receptionist.config import Settings
from ai_receptionist.interfaces import (
    EndOfTurnDetector,
    Responder,
    SpeechRecognizer,
    SpeechSynthesizer,
)
from ai_receptionist.business import BusinessFaq, BusinessProfile
from ai_receptionist.callback_inbox import CallbackInbox, CallbackMessageWorkflow
from ai_receptionist.providers import LocalKokoro, LocalLlamaResponder, LocalWhisper
from ai_receptionist.policy import parse_allowed_languages
from ai_receptionist.stream_buffer import append_pcm16_bounded
from ai_receptionist.turn_detection import LocalSmartTurnDetector

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 16 * 1024 * 1024
MAX_LIVE_TURN_SECONDS = 25
MAX_LIVE_AUDIO_BYTES = int(MAX_LIVE_TURN_SECONDS * 16_000 * 2)
MAX_CONTROL_MESSAGE_CHARS = 1024
MAX_DIALOGUE_MESSAGES = 8
WEB_DIR = Path(__file__).parent / "static"


def _allowed_websocket_origins() -> set[str]:
    """Return exact browser origins allowed to use the local WebSocket APIs."""
    configured = os.getenv("RECEPTIONIST_ALLOWED_ORIGINS")
    if configured is not None:
        return {origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()}
    port = os.getenv("RECEPTIONIST_WEB_PORT", "8765")
    return {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    }


async def _require_trusted_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "").rstrip("/")
    if origin and origin in _allowed_websocket_origins():
        return True
    await websocket.close(code=1008, reason="Untrusted browser origin")
    return False


def _get_callback_inbox() -> CallbackInbox:
    inbox = getattr(app.state, "callback_inbox", None)
    if inbox is not None:
        return inbox
    lock = getattr(app.state, "callback_inbox_lock", None)
    if lock is None:
        lock = threading.Lock()
        app.state.callback_inbox_lock = lock
    with lock:
        inbox = getattr(app.state, "callback_inbox", None)
        if inbox is None:
            settings = Settings.from_environment()
            inbox = CallbackInbox(
                settings.callback_message_db_path,
                settings.callback_message_retention_days,
            )
            app.state.callback_inbox = inbox
    return inbox


def _trusted_http_origin(request: Request) -> bool:
    origin = request.headers.get("origin", "").rstrip("/")
    if origin:
        return origin in _allowed_websocket_origins()
    return request.headers.get("sec-fetch-site") == "same-origin"


async def _receive_live_responses(session):
    """Keep reading a Live session when the SDK iterator ends after each turn."""
    while True:
        received_response = False
        async for response in session.receive():
            received_response = True
            yield response
        if not received_response:
            raise RuntimeError("Gemini Live receive iterator ended without a response")


def _gemini_allowed_languages() -> list[str]:
    """Read a small, safe language allow-list for the Gemini session prompt."""
    return list(parse_allowed_languages(os.getenv("ASSISTANT_ALLOWED_LANGUAGES", "English")))


def _gemini_language_instruction(allowed: list[str]) -> str:
    language_list = ", ".join(allowed)
    default_language = allowed[0]
    if len(allowed) == 1:
        return (
            f"Understand the caller's audio, but speak every reply only in {default_language}. "
            f"RESPOND UNMISTAKABLY ONLY IN {default_language.upper()}. "
            f"Do not mirror or code-switch into any other language, even for greetings or acknowledgements. "
            f"The only allowed conversation language is {language_list}. "
            "Never switch languages based on a brief acknowledgement, filler, "
            "name, borrowed word, background sound, or uncertain audio. If the "
            f"caller speaks another language, continue in {default_language} and "
            f"briefly explain that you can help in {default_language}."
        )
    return (
        f"Use only these allowed conversation languages: {language_list}. "
        f"Start in {default_language}. Change to another allowed language only "
        "when the caller clearly speaks a substantive request in that language "
        "or explicitly asks to switch. Never switch because of a brief "
        "acknowledgement, filler, name, borrowed word, background sound, or "
        f"uncertain audio. If speech is outside the allowed list, answer in {default_language}."
    )


def _callback_message_tools() -> list[dict[str, object]]:
    return [{
        "function_declarations": [
            {
                "name": "request_callback_message_consent",
                "description": "Before collecting a caller's name, phone number, or message, request explicit consent and wait for a clear affirmative reply.",
                "parameters": {"type": "OBJECT", "properties": {}, "required": []},
            },
            {
                "name": "prepare_callback_message",
                "description": "Prepare a callback message only after explicit consent. This does not save it. Read back the returned details and ask for a clear final confirmation.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "caller_name": {"type": "STRING", "description": "Caller-provided name."},
                        "callback_number": {"type": "STRING", "description": "Caller-provided phone number for the callback."},
                        "message": {"type": "STRING", "description": "Short message for the business."},
                    },
                    "required": ["caller_name", "callback_number", "message"],
                },
            },
            {
                "name": "save_confirmed_callback_message",
                "description": "Save the prepared callback message only after the caller clearly confirms the exact read-back. Never call this based only on inferred consent.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "draft_id": {"type": "STRING", "description": "The draft ID returned by prepare_callback_message."},
                    },
                    "required": ["draft_id"],
                },
            },
        ]
    }]


def _gemini_live_config(business_context: str = "") -> dict[str, object]:
    """Build the voice config with Gemini VAD available as an endpointing fallback."""
    allowed_languages = _gemini_allowed_languages()
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": (
            "You are a concise, friendly AI receptionist. "
            + _gemini_language_instruction(allowed_languages)
            + " Do not invent business details or claim to book, transfer, or save anything."
            + " If information or an action is unavailable, say so plainly."
            + (f"\n{business_context[:1200]}" if business_context.strip() else "")
            + " If the caller asks for a person, do not claim to transfer the call or alert staff. Explain that live transfer and automatic staff notification are not configured, and offer to leave a callback message for someone to review in this computer's inbox. Start the message workflow only if the caller accepts. Message-taking workflow: first call request_callback_message_consent and speak the returned notice. Do not ask for personal details until the caller clearly says yes. Then collect the caller's name, callback number, and short message; call prepare_callback_message, read back its returned details, and ask for a clear yes or no. Only after a clear yes call save_confirmed_callback_message. The server independently checks consent and confirmation. If the caller says no, do not save. Claim the message was saved only when the tool response says stored=true; otherwise plainly say it was not saved. After saving, say it is in the local inbox and no one was automatically notified. Treat 'uh-huh' and background noise as neither consent nor confirmation."
        ),
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "tools": _callback_message_tools(),
    }


async def _finalize_gemini_audio_turn(session) -> None:
    """Finalize client-detected speech while retaining server-side VAD fallback."""
    await session.send_realtime_input(audio_stream_end=True)


class LocalVoicePipeline:
    def __init__(
        self,
        settings: Settings,
        asr: SpeechRecognizer | None = None,
        responder: Responder | None = None,
        tts: SpeechSynthesizer | None = None,
        turn_detector: EndOfTurnDetector | None = None,
    ) -> None:
        self.settings = settings
        self.asr = asr if asr is not None else LocalWhisper(settings)
        self.responder = responder if responder is not None else LocalLlamaResponder(settings)
        self.tts = tts if tts is not None else LocalKokoro(settings)
        self.turn_detector = turn_detector
        if self.turn_detector is None and settings.smart_turn_model_path.is_file():
            self.turn_detector = LocalSmartTurnDetector(
                settings.smart_turn_model_path, settings.whisper_cpu_threads
            )
        elif self.turn_detector is None:
            logger.warning(
                "Smart Turn model is unavailable at %s; using the browser silence timeout.",
                settings.smart_turn_model_path,
            )
        self.faq = BusinessFaq(settings.faq_path)
        self.profile = BusinessProfile(settings.business_profile_path)
        self._speech_cache_lock = threading.Lock()

    def close(self) -> None:
        self.tts.close()

    @staticmethod
    def pcm_to_float(pcm: bytes) -> np.ndarray:
        return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0

    @staticmethod
    def sentences(text: str) -> list[str]:
        pieces = re.split(r"(?<=[.!?])\s+", text.strip())
        return [piece.strip() for piece in pieces if piece.strip()] or [text.strip()]

    def _speech_for_answer(self, answer: str, cache: bool = False) -> tuple[np.ndarray, int]:
        with self._speech_cache_lock:
            cached = self.faq.cached_speech(answer)
            if cached is not None:
                return cached
            speech, sample_rate = self.tts.synthesize(answer)
            if cache:
                self.faq.store_speech(answer, speech, sample_rate)
            return speech, sample_rate

    def process(self, audio_bytes: bytes, suffix: str) -> dict[str, object]:
        """Compatibility path for the original one-recording endpoint."""
        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=suffix) as audio_file:
            audio_file.write(audio_bytes)
            audio_file.flush()
            stage = time.perf_counter()
            transcript = self.asr.transcribe(audio_file.name)
        asr_seconds = time.perf_counter() - stage
        stage = time.perf_counter()
        match = self.faq.match(transcript)
        answer = match[0] if match else self.responder.respond(
            transcript, business_context=self.profile.prompt_context()
        )
        llm_seconds = 0.0 if match else time.perf_counter() - stage
        stage = time.perf_counter()
        speech, sample_rate = self._speech_for_answer(answer)
        tts_seconds = time.perf_counter() - stage
        wav = BytesIO()
        sf.write(wav, speech, sample_rate, format="WAV", subtype="PCM_16")
        return {
            "transcript": transcript,
            "answer": answer,
            "audio_wav": wav.getvalue(),
            "timings": {
                "asr_seconds": asr_seconds,
                "llm_seconds": llm_seconds,
                "tts_seconds": tts_seconds,
                "processing_seconds": time.perf_counter() - started,
            },
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app.state.pipeline = None
    app.state.pipeline_lock = asyncio.Lock()
    app.state.callback_inbox = None
    app.state.callback_inbox_lock = threading.Lock()
    retention_task = asyncio.create_task(_callback_retention_loop())
    try:
        yield
    finally:
        retention_task.cancel()
        await asyncio.gather(retention_task, return_exceptions=True)
        pipeline = app.state.pipeline
        if pipeline is not None:
            pipeline.close()


async def _callback_retention_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        inbox = getattr(app.state, "callback_inbox", None)
        if inbox is not None:
            try:
                await run_in_threadpool(inbox.prune_expired)
            except Exception:
                logger.exception("Callback-message retention cleanup failed")


app = FastAPI(title="Local AI Receptionist", docs_url=None, redoc_url=None, lifespan=lifespan)


async def get_local_pipeline() -> LocalVoicePipeline:
    """Create the local model stack only when the local provider is selected."""
    pipeline = app.state.pipeline
    if pipeline is not None:
        return pipeline
    async with app.state.pipeline_lock:
        pipeline = app.state.pipeline
        if pipeline is None:
            logger.info("Loading local models on first local-provider request.")
            pipeline = LocalVoicePipeline(Settings.from_environment())
            app.state.pipeline = pipeline
    return pipeline


@app.get("/")
async def index() -> RedirectResponse:
    """Keep the root URL on the maintained diagnostics conversation UI."""
    return RedirectResponse("/diagnostics", status_code=307)


@app.get("/diagnostics")
async def diagnostics() -> FileResponse:
    return FileResponse(WEB_DIR / "diagnostics.html")


@app.get("/static/mic-processor.js")
async def mic_processor() -> FileResponse:
    return FileResponse(WEB_DIR / "mic-processor.js", media_type="text/javascript")


@app.get("/api/callback-messages")
async def callback_messages(request: Request) -> list[dict[str, str]]:
    """Return recent locally stored messages to the same-origin diagnostics page."""
    if not _trusted_http_origin(request):
        raise HTTPException(status_code=403, detail="Untrusted browser origin")
    messages = await run_in_threadpool(_get_callback_inbox().list_recent)
    return [asdict(message) for message in messages]


@app.delete("/api/callback-messages/{message_id}")
async def delete_callback_message(message_id: str, request: Request) -> dict[str, bool]:
    if not _trusted_http_origin(request):
        raise HTTPException(status_code=403, detail="Untrusted browser origin")
    deleted = await run_in_threadpool(_get_callback_inbox().delete, message_id)
    return {"deleted": deleted}


@app.post("/api/turn")
async def turn(audio: UploadFile = File(...)) -> dict[str, object]:
    body = await audio.read(MAX_UPLOAD_BYTES + 1)
    if not body:
        raise HTTPException(status_code=400, detail="No audio was recorded.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too large; keep turns under 25 seconds.")
    suffix = Path(audio.filename or "turn.webm").suffix or ".webm"
    try:
        pipeline = await get_local_pipeline()
        result = await run_in_threadpool(pipeline.process, body, suffix)
    except Exception as exc:
        logger.exception("Local audio turn failed")
        raise HTTPException(status_code=500, detail=f"Local processing failed: {exc}") from exc
    return {
        "transcript": result["transcript"],
        "answer": result["answer"],
        "audio_base64": b64encode(result["audio_wav"]).decode("ascii"),
        "timings": result["timings"],
    }


@app.websocket("/api/stream")
async def live_audio(websocket: WebSocket) -> None:
    """Persistent browser audio session with interim ASR and cancellable output.

    Audio arrives as little-endian 16 kHz mono PCM16. The recognizer is not a
    native streaming model, so interim captions are produced by decoding the
    growing audio buffer at a bounded interval; the final turn is decoded once
    more after endpointing.
    """
    if not await _require_trusted_websocket_origin(websocket):
        return
    await websocket.accept()
    try:
        pipeline = await get_local_pipeline()
    except Exception:
        logger.exception("Local voice stack could not start")
        await websocket.send_json({
            "type": "error",
            "message": "The local voice engine could not start. Check local model files and configuration.",
        })
        await websocket.close(code=1011)
        return
    send_lock = asyncio.Lock()
    current_audio = bytearray()
    active = False
    limit_notified = False
    turn_id = 0
    last_partial_at = 0.0
    partial_task: asyncio.Task | None = None
    response_task: asyncio.Task | None = None
    speculative_task: asyncio.Task | None = None
    warm_tasks: dict[str, asyncio.Task] = {}
    dialogue_history: list[dict[str, str]] = []
    turn_check_generation = 0
    turn_check_pending = False
    turn_check_tasks: set[asyncio.Task] = set()
    session_started = time.perf_counter()

    async def send(event: dict[str, object]) -> None:
        async with send_lock:
            await websocket.send_json(event)

    async def warm_answer(answer: str, for_turn: int) -> None:
        try:
            await run_in_threadpool(pipeline._speech_for_answer, answer, True)
            if for_turn == turn_id and active:
                await send({"type": "faq_ready", "answer": answer})
        except Exception:
            logger.exception("Could not pre-synthesize curated FAQ reply")

    def schedule_warm_answer(answer: str, for_turn: int) -> None:
        task = warm_tasks.get(answer)
        if task is not None and not task.done():
            return
        if pipeline.faq.cached_speech(answer) is not None:
            return
        warm_tasks[answer] = asyncio.create_task(warm_answer(answer, for_turn))

    async def speculative_reply(
        snapshot: str, this_turn: int, history: tuple[dict[str, str], ...]
    ) -> tuple[str, str, np.ndarray, int]:
        answer = await run_in_threadpool(
            pipeline.responder.respond,
            snapshot,
            history,
            pipeline.profile.prompt_context(),
        )
        speech, sample_rate = await run_in_threadpool(pipeline.tts.synthesize, answer)
        if this_turn == turn_id and active:
            await send({"type": "speculative_ready", "audio_prepared": True})
        return snapshot, answer, speech, sample_rate

    async def emit_response(
        audio: bytes,
        this_turn: int,
        candidate_task: asyncio.Task | None,
        history: tuple[dict[str, str], ...],
    ) -> None:
        started = time.perf_counter()
        try:
            transcript = await run_in_threadpool(pipeline.asr.transcribe, pipeline.pcm_to_float(audio))
            asr_seconds = time.perf_counter() - started
            if not transcript:
                await send({"type": "error", "message": "I didn't catch that. Please try again."})
                return
            if this_turn != turn_id:
                return
            await send({"type": "transcript", "text": transcript})
            await send({"type": "stage", "stage": "lookup"})

            stage = time.perf_counter()
            match = pipeline.faq.match(transcript)
            source = "faq" if match else "llm"
            prepared_audio: tuple[np.ndarray, int] | None = None
            if match:
                answer = match[0]
                llm_seconds = 0.0
                warm_task = warm_tasks.get(answer)
                if warm_task is not None:
                    await send({"type": "stage", "stage": "prepare_faq"})
                    await warm_task
                prepared_audio = pipeline.faq.cached_speech(answer)
            else:
                answer = ""
                if candidate_task is not None:
                    try:
                        await send({"type": "stage", "stage": "checking_draft"})
                        partial_text, candidate, candidate_audio, candidate_rate = await candidate_task
                        similarity = SequenceMatcher(
                            None,
                            pipeline.faq.normalize(transcript),
                            pipeline.faq.normalize(partial_text),
                        ).ratio()
                        if similarity >= 0.84:
                            answer = candidate
                            prepared_audio = (candidate_audio, candidate_rate)
                            source = "speculative_llm"
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        logger.exception("Speculative answer failed; generating from final transcript")
                if not answer:
                    await send({"type": "stage", "stage": "generate"})
                    answer = await run_in_threadpool(
                        pipeline.responder.respond,
                        transcript,
                        history,
                        pipeline.profile.prompt_context(),
                    )
                llm_seconds = time.perf_counter() - stage

            if this_turn != turn_id:
                return
            await send({"type": "answer", "text": answer, "source": source})
            first_audio = None
            tts_seconds = 0.0
            pre_synthesized = prepared_audio is not None
            answer_chunks = (
                [answer]
                if source == "faq" or prepared_audio is not None
                else pipeline.sentences(answer)
            )
            for sentence in answer_chunks:
                if this_turn != turn_id:
                    return
                tts_stage = time.perf_counter()
                if prepared_audio is not None:
                    speech, sample_rate = prepared_audio
                    prepared_audio = None
                else:
                    speech, sample_rate = await run_in_threadpool(
                        pipeline._speech_for_answer, sentence, source == "faq"
                    )
                tts_seconds += time.perf_counter() - tts_stage
                if this_turn != turn_id:
                    return
                if first_audio is None:
                    first_audio = time.perf_counter()
                await send({
                    "type": "audio_chunk",
                    "audio_base64": b64encode(np.asarray(speech, dtype="<f4").tobytes()).decode("ascii"),
                    "sample_rate": sample_rate,
                    "format": "f32le",
                })
            if this_turn != turn_id:
                return
            dialogue_history.extend([
                {"role": "user", "content": transcript},
                {"role": "assistant", "content": answer},
            ])
            del dialogue_history[:-MAX_DIALOGUE_MESSAGES]
            await send({
                "type": "assistant_done",
                "source": source,
                "timings": {
                    "asr_seconds": asr_seconds,
                    "llm_seconds": llm_seconds,
                    "tts_seconds": tts_seconds,
                    "end_to_first_audio_seconds": (
                        first_audio - started if first_audio is not None else None
                    ),
                    "speech_prepared_before_turn_end": pre_synthesized,
                    "session_uptime_seconds": time.perf_counter() - session_started,
                },
            })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Live local audio turn failed")
            if this_turn == turn_id:
                await send({"type": "error", "message": f"Local processing failed: {exc}"})

    async def partial_transcription(audio_snapshot: bytes, this_turn: int) -> None:
        nonlocal speculative_task
        try:
            transcript = await run_in_threadpool(
                pipeline.asr.transcribe_partial,
                pipeline.pcm_to_float(audio_snapshot),
            )
            if this_turn != turn_id or not active or not transcript:
                return
            await send({"type": "partial_transcript", "text": transcript})
            faq_match = pipeline.faq.match(transcript)
            if faq_match:
                schedule_warm_answer(faq_match[0], this_turn)
            elif speculative_task is None and len(transcript.split()) >= 5:
                # Start one tentative LLM response during a longer utterance.
                # It is only reused if final ASR agrees; otherwise it is discarded.
                speculative_task = asyncio.create_task(
                    speculative_reply(transcript, this_turn, tuple(dialogue_history))
                )
        except Exception:
            logger.exception("Interim transcription failed; final transcription remains available")

    async def check_turn_completion(
        audio_snapshot: bytes, this_turn: int, generation: int, check_id: int
    ) -> None:
        nonlocal turn_check_pending
        try:
            if pipeline.turn_detector is None or len(audio_snapshot) < 16_000:
                await send({
                    "type": "turn_decision",
                    "check_id": check_id,
                    "available": False,
                })
                return
            probability = await run_in_threadpool(
                pipeline.turn_detector.completion_probability,
                pipeline.pcm_to_float(audio_snapshot),
            )
            if active and this_turn == turn_id and generation == turn_check_generation:
                await send({
                    "type": "turn_decision",
                    "check_id": check_id,
                    "available": True,
                    "complete": probability >= 0.5,
                    "probability": probability,
                })
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Smart Turn analysis failed; browser silence timeout remains available")
            if active and this_turn == turn_id and generation == turn_check_generation:
                await send({
                    "type": "turn_decision",
                    "check_id": check_id,
                    "available": False,
                })
        finally:
            if generation == turn_check_generation:
                turn_check_pending = False

    try:
        await send({
            "type": "ready",
            "sample_rate": 16000,
            "smart_turn_available": pipeline.turn_detector is not None,
        })
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                if active:
                    try:
                        hit_limit = append_pcm16_bounded(
                            current_audio, message["bytes"], MAX_LIVE_AUDIO_BYTES
                        )
                    except ValueError:
                        await send({"type": "error", "message": "Invalid PCM audio frame."})
                        active = False
                        current_audio.clear()
                        continue
                    now = time.monotonic()
                    duration = len(current_audio) / (16000 * 2)
                    if hit_limit and not limit_notified:
                        await send({"type": "turn_limit"})
                        limit_notified = True
                    elif (
                        duration >= pipeline.settings.partial_transcription_min_seconds
                        and now - last_partial_at >= pipeline.settings.partial_transcription_interval
                        and (partial_task is None or partial_task.done())
                    ):
                        last_partial_at = now
                        partial_task = asyncio.create_task(
                            partial_transcription(bytes(current_audio), turn_id)
                        )
                continue

            raw_text = message.get("text")
            if raw_text is None:
                continue
            if len(raw_text) > MAX_CONTROL_MESSAGE_CHARS:
                await send({"type": "error", "message": "Control message is too large."})
                continue
            try:
                event = json.loads(raw_text)
            except json.JSONDecodeError:
                await send({"type": "error", "message": "Invalid control message."})
                continue
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                await send({"type": "error", "message": "Invalid control message."})
                continue
            kind = event.get("type")
            if kind == "speech_start":
                turn_check_generation += 1
                turn_check_pending = False
                limit_notified = False
                turn_id += 1
                active = True
                current_audio.clear()
                last_partial_at = 0.0
                if response_task and not response_task.done():
                    response_task.cancel()
                if speculative_task and not speculative_task.done():
                    speculative_task.cancel()
                speculative_task = None
                await send({"type": "listening", "turn_id": turn_id})
            elif kind == "turn_end" and active:
                turn_check_generation += 1
                turn_check_pending = False
                active = False
                if len(current_audio) < 16000 * 2 * 0.18:
                    await send({"type": "error", "message": "That was too short to recognize. Try again."})
                    continue
                candidate = speculative_task
                response_task = asyncio.create_task(
                    emit_response(
                        bytes(current_audio), turn_id, candidate, tuple(dialogue_history)
                    )
                )
                await send({"type": "processing", "turn_id": turn_id})
            elif kind == "turn_check" and active and not turn_check_pending:
                turn_check_pending = True
                check_id = event.get("check_id")
                if not isinstance(check_id, int):
                    turn_check_pending = False
                    await send({"type": "error", "message": "Invalid turn-check id."})
                    continue
                generation = turn_check_generation
                task = asyncio.create_task(
                    check_turn_completion(bytes(current_audio), turn_id, generation, check_id)
                )
                turn_check_tasks.add(task)
                task.add_done_callback(turn_check_tasks.discard)
            elif kind == "turn_resume":
                turn_check_generation += 1
                turn_check_pending = False
            elif kind == "interrupt":
                if response_task and not response_task.done():
                    response_task.cancel()
                await send({"type": "interrupted", "turn_id": turn_id})
            elif kind == "stop":
                if response_task and not response_task.done():
                    response_task.cancel()
                if speculative_task and not speculative_task.done():
                    speculative_task.cancel()
                break
    except WebSocketDisconnect:
        pass
    finally:
        active = False
        for task in (partial_task, response_task, speculative_task, *turn_check_tasks):
            if task and not task.done():
                task.cancel()


@app.websocket("/api/gemini-stream")
async def gemini_live_audio(websocket: WebSocket) -> None:
    """Relay browser PCM to an explicitly selected Gemini Live session.

    The API key stays on the server. Audio is sent to Google only after this
    provider-specific WebSocket is opened by the user from the diagnostics UI.
    """
    if not await _require_trusted_websocket_origin(websocket):
        return
    await websocket.accept()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        await websocket.send_json({
            "type": "error",
            "message": "Gemini is not configured yet. Add GEMINI_API_KEY to your local .env file, then restart the assistant.",
        })
        await websocket.close(code=1008)
        return

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        await websocket.send_json({
            "type": "error",
            "message": "Gemini support is not installed. Install the optional Gemini dependencies, then restart the assistant.",
        })
        await websocket.close(code=1011)
        return

    model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
    client = genai.Client(api_key=api_key)
    settings = Settings.from_environment()
    business_context = BusinessProfile(settings.business_profile_path).prompt_context()
    config = _gemini_live_config(business_context)
    callback_workflow = CallbackMessageWorkflow(_get_callback_inbox())
    send_lock = asyncio.Lock()
    turn_ended_at: float | None = None
    first_audio_at: float | None = None
    answer_text = ""
    turn_audio_bytes = 0

    async def send(event: dict[str, object]) -> None:
        async with send_lock:
            await websocket.send_json(event)

    async def client_to_gemini(session) -> None:
        nonlocal turn_ended_at, first_audio_at, turn_audio_bytes
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                audio = message["bytes"]
                if not audio or len(audio) > 8192 or len(audio) % 2:
                    await send({"type": "error", "message": "Invalid Gemini audio frame."})
                    continue
                if turn_audio_bytes + len(audio) > MAX_LIVE_AUDIO_BYTES:
                    await send({"type": "turn_limit"})
                    continue
                turn_audio_bytes += len(audio)
                await session.send_realtime_input(
                    audio=types.Blob(data=audio, mime_type="audio/pcm;rate=16000")
                )
                continue
            raw = message.get("text")
            if not raw or len(raw) > MAX_CONTROL_MESSAGE_CHARS:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "turn_end":
                turn_ended_at = time.perf_counter()
                first_audio_at = None
                turn_audio_bytes = 0
                # Keep Gemini's automatic speech detector enabled as a fallback
                # for room noise, while the browser sends this client-side end
                # signal for a quick response when its silence detector fires.
                await _finalize_gemini_audio_turn(session)
            elif kind == "interrupt":
                # Gemini's native VAD receives the caller's audio continuously
                # and handles barge-in. The browser has already stopped playback.
                pass
            elif kind == "stop":
                return

    async def handle_callback_tool_call(session, tool_call) -> None:
        function_responses = []
        for function_call in getattr(tool_call, "function_calls", ()):
            name = getattr(function_call, "name", "")
            call_id = getattr(function_call, "id", "")
            args = getattr(function_call, "args", {}) or {}
            if not isinstance(args, dict):
                args = {}
            try:
                if name == "request_callback_message_consent":
                    notice = callback_workflow.request_consent()
                    result = {"ok": True, "speak_to_caller": notice}
                    await send({"type": "callback_status", "message": "Waiting for your permission before collecting callback details."})
                elif name == "prepare_callback_message":
                    prepared = callback_workflow.prepare(
                        args.get("caller_name"),
                        args.get("callback_number"),
                        args.get("message"),
                    )
                    result = {"ok": True, **prepared}
                    await send({"type": "callback_status", "message": "Read back the details and ask before saving."})
                elif name == "save_confirmed_callback_message":
                    saved = await run_in_threadpool(
                        callback_workflow.save, str(args.get("draft_id", ""))
                    )
                    result = {
                        "stored": True,
                        "expires_at": saved.expires_at,
                        "instruction": "Tell the caller the message is in this computer's local callback inbox; no one was automatically notified or connected.",
                    }
                    await send({"type": "callback_status", "message": "Saved in the local inbox; staff were not automatically notified."})
                    await send({"type": "callback_saved"})
                else:
                    result = {"ok": False, "error": "Unknown callback-message action."}
            except ValueError as exc:
                result = {"ok": False, "stored": False, "error": str(exc)}
                await send({"type": "callback_status", "message": "Message not saved; caller confirmation or details are missing."})
            except (OSError, sqlite3.Error, RuntimeError):
                logger.exception("Callback message could not be saved")
                result = {"ok": False, "stored": False, "error": "Local message storage is unavailable."}
                await send({"type": "callback_status", "message": "Message was not saved because local storage is unavailable."})
            if not call_id or not name:
                continue
            function_responses.append(types.FunctionResponse(
                id=call_id,
                name=name,
                response=result,
            ))
        if function_responses:
            await session.send_tool_response(function_responses=function_responses)

    async def gemini_to_client(session) -> None:
        nonlocal first_audio_at, answer_text
        await send({"type": "ready", "provider": "gemini", "model": model})
        # The GenAI SDK receive iterator ends after each model turn. Reopen it
        # for the next turn while keeping the Live session and browser
        # WebSocket alive so queued speech audio can finish playing.
        async for response in _receive_live_responses(session):
            content = getattr(response, "server_content", None)
            input_transcription = getattr(content, "input_transcription", None) if content else None
            if input_transcription and getattr(input_transcription, "text", None):
                user_text = input_transcription.text
                await send({"type": "transcript", "text": user_text})
                transition = callback_workflow.observe_user_transcript(user_text)
                if transition == "consent_given":
                    await send({"type": "callback_status", "message": "Permission received. The assistant can ask for the callback details."})
                elif transition == "consent_declined":
                    await send({"type": "callback_status", "message": "No details collected; nothing was saved."})
                elif transition == "message_confirmed":
                    await send({"type": "callback_status", "message": "Confirmation received. Waiting for the save action."})
                elif transition == "message_declined":
                    await send({"type": "callback_status", "message": "Message declined; nothing was saved."})

            tool_call = getattr(response, "tool_call", None)
            if tool_call is not None:
                await handle_callback_tool_call(session, tool_call)
            if content is None:
                continue

            output_transcription = getattr(content, "output_transcription", None)
            if output_transcription and getattr(output_transcription, "text", None):
                answer_text += output_transcription.text
                await send({"type": "answer", "text": answer_text, "source": "gemini_live"})

            model_turn = getattr(content, "model_turn", None)
            for part in getattr(model_turn, "parts", ()) if model_turn else ():
                inline = getattr(part, "inline_data", None)
                if inline is None:
                    continue
                chunk = inline.data
                if isinstance(chunk, str):
                    chunk = chunk.encode("latin1")
                if not isinstance(chunk, bytes) or not chunk:
                    continue
                if first_audio_at is None:
                    first_audio_at = time.perf_counter()
                mime_type = getattr(inline, "mime_type", "") or "audio/pcm;rate=24000"
                rate_match = re.search(r"rate=(\d+)", mime_type)
                sample_rate = int(rate_match.group(1)) if rate_match else 24_000
                await send({
                    "type": "audio_chunk",
                    "audio_base64": b64encode(chunk).decode("ascii"),
                    "sample_rate": sample_rate,
                    "format": "s16le",
                })

            if getattr(content, "interrupted", False):
                answer_text = ""
                first_audio_at = None
                await send({"type": "interrupted"})
            if getattr(content, "turn_complete", False):
                await send({
                    "type": "assistant_done",
                    "source": "gemini_live",
                    "timings": {
                        "end_to_first_audio_seconds": (
                            first_audio_at - turn_ended_at
                            if first_audio_at is not None and turn_ended_at is not None
                            else None
                        )
                    },
                })
                answer_text = ""
                first_audio_at = None
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            send_task = asyncio.create_task(client_to_gemini(session))
            receive_task = asyncio.create_task(gemini_to_client(session))
            done, pending = await asyncio.wait(
                {send_task, receive_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                exception = task.exception()
                if exception:
                    raise exception
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Gemini Live session failed")
        try:
            await send({"type": "error", "message": "Gemini Live connection failed. Check the local key, model access, and network, then try again."})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/{path:path}")
async def unknown_page(path: str) -> RedirectResponse:
    # Some browser address bars preserve a copied /** suffix. Keep that
    # accidental URL on the app instead of showing a confusing 404 page.
    if path == "**":
        return RedirectResponse("/", status_code=307)
    raise HTTPException(status_code=404, detail="Not Found")


def run() -> None:
    host = os.getenv("RECEPTIONIST_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("RECEPTIONIST_WEB_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info")
