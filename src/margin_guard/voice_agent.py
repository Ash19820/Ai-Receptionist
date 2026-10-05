"""Optional Pipecat entry point for live voice conversations."""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack

from mcp import StdioServerParameters
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    LLMTextFrame,
    ManuallySwitchServiceFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.service_switcher import ServiceSwitcher
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.mcp_service import MCPClient
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from margin_guard.llm_provider import get_llm_config


SYSTEM_INSTRUCTIONS = """You are a concise, friendly receptionist for one small business.
Use the verified profile and FAQ tools for business facts. Never invent prices,
hours, services, availability, policies, or promises. Reply in the caller's
language where possible, using natural spoken phrasing. Speak English in Latin
script. Speak Hindi and Hindi-English mix in Devanagari, not Latin transliteration.
Keep ordinary replies to one or two short sentences, about 35 words or fewer.
Do not use lists, markdown, emojis, stage directions, or verbal filler. Ask one
short question at a time and collect only details needed for the request.
Before creating a callback or appointment request, read back the caller's name, contact number,
service, and preferred time as applicable, then wait for an explicit yes. Set
caller_confirmed=true only after the caller gives that yes.
Requests are saved for staff review and are not confirmed bookings. Do not claim
a slot is booked. If you are unsure, offer a human handoff using configured
business information; do not claim a handoff happened unless an integration
confirms it. Do not provide professional advice outside the configured services."""


class ResponseLanguageTTSRouter(FrameProcessor):
    """Choose the speech service from the script used by each assistant reply."""

    def __init__(self, hindi_service, english_service):
        super().__init__()
        self._services = {"hindi": hindi_service, "english": english_service}
        self._selected_service = None
        self._pending_text: list[LLMTextFrame] = []

    @staticmethod
    def _response_language(text: str) -> str | None:
        # The system prompt asks for Devanagari for Hindi/Hinglish and Latin
        # script for English, so the first spoken letters provide a quick,
        # stable routing signal without delaying the whole response.
        for char in text:
            if char.isalpha():
                return "english" if char.isascii() else "hindi"
        return None

    async def _select_and_flush(self, service_name: str, direction: FrameDirection) -> None:
        service = self._services[service_name]
        await self.push_frame(ManuallySwitchServiceFrame(service=service), direction)
        for text_frame in self._pending_text:
            await self.push_frame(text_frame, direction)
        self._pending_text.clear()
        self._selected_service = service

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, LLMFullResponseStartFrame):
                self._selected_service = None
                self._pending_text.clear()
            elif isinstance(frame, LLMTextFrame) and self._selected_service is None:
                self._pending_text.append(frame)
                language = self._response_language("".join(item.text for item in self._pending_text))
                if language:
                    await self._select_and_flush(language, direction)
                return
            elif isinstance(frame, LLMFullResponseEndFrame) and self._selected_service is None:
                # Empty or punctuation-only responses are exceptionally rare;
                # use the Hindi voice as the default.
                await self._select_and_flush("hindi", direction)

        await self.push_frame(frame, direction)


def _speech_output(provider: str | None = None):
    provider = (provider or os.getenv("VOICE_TTS_PROVIDER", "auto")).strip().lower()
    if provider == "sarvam":
        from pipecat.services.sarvam.tts import SarvamTTSService
        from pipecat.transcriptions.language import Language

        api_key = os.getenv("SARVAM_API_KEY")
        if not api_key:
            raise RuntimeError("Set SARVAM_API_KEY to use Sarvam speech output.")
        language_map = {
            "bn-IN": Language.BN,
            "en-IN": Language.EN_IN,
            "gu-IN": Language.GU,
            "hi-IN": Language.HI,
            "kn-IN": Language.KN,
            "ml-IN": Language.ML,
            "mr-IN": Language.MR,
            "od-IN": Language.OR,
            "pa-IN": Language.PA,
            "ta-IN": Language.TA,
            "te-IN": Language.TE,
        }
        language_code = os.getenv("SARVAM_TTS_LANGUAGE", "hi-IN")
        if language_code not in language_map:
            raise RuntimeError("SARVAM_TTS_LANGUAGE must be a supported Indian language code such as hi-IN or en-IN.")
        return SarvamTTSService(
            api_key=api_key,
            settings=SarvamTTSService.Settings(
                model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
                voice=os.getenv("SARVAM_TTS_VOICE", "shubh"),
                language=language_map[language_code],
                pace=float(os.getenv("SARVAM_TTS_PACE", "1.0")),
                temperature=float(os.getenv("SARVAM_TTS_TEMPERATURE", "0.8")),
            ),
        )
    if provider == "piper":
        from pipecat.services.piper.tts import PiperTTSService
        from pipecat.transcriptions.language import Language

        return PiperTTSService(
            settings=PiperTTSService.Settings(
                voice=os.getenv("PIPER_HI_VOICE", "hi_IN-priyamvada-medium"),
                language=Language.HI,
            ),
        )
    if provider == "kokoro":
        if sys.version_info >= (3, 14):
            raise RuntimeError(
                "The published kokoro-onnx package does not support Python 3.14 yet. "
                "Use Python 3.13 or older and install the voice-kokoro extra."
            )
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.transcriptions.language import Language

        return KokoroTTSService(
            settings=KokoroTTSService.Settings(
                voice=os.getenv("KOKORO_VOICE", "af_heart"),
                language=Language.EN,
            ),
        )
    if provider == "gemini":
        from pipecat.services.google.tts import GeminiTTSService

        api_key = os.getenv("GEMINI_TTS_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_TTS_API_KEY to use Gemini speech output.")
        return GeminiTTSService(
            api_key=api_key,
            settings=GeminiTTSService.Settings(
                model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts"),
                voice=os.getenv("GEMINI_TTS_VOICE", "Kore"),
                prompt=(
                    "Speak like a warm, attentive local business receptionist. "
                    "Use natural conversational pacing and gentle expression, not a "
                    "formal announcement. Pronounce Hindi and Indian names naturally."
                ),
            ),
        )
    raise RuntimeError(
        "VOICE_TTS_PROVIDER must be 'auto', 'piper', 'kokoro', 'sarvam', or 'gemini'."
    )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    stt_provider = os.getenv("VOICE_STT_PROVIDER", "whisper").strip().lower()
    if stt_provider == "whisper":
        from pipecat.services.whisper.stt import WhisperSTTService

        stt = WhisperSTTService(
            device=os.getenv("WHISPER_DEVICE", "cpu"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            settings=WhisperSTTService.Settings(
                model=os.getenv("WHISPER_MODEL", "base"),
                language=None,
            ),
        )
    elif stt_provider == "sarvam":
        from pipecat.services.sarvam.stt import SarvamSTTService

        sarvam_key = os.getenv("SARVAM_API_KEY")
        if not sarvam_key:
            raise RuntimeError("Set SARVAM_API_KEY to use Sarvam speech recognition.")
        stt = SarvamSTTService(
            api_key=sarvam_key,
            settings=SarvamSTTService.Settings(
                model=os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
            ),
        )
    else:
        raise RuntimeError("VOICE_STT_PROVIDER must be 'whisper' or 'sarvam'.")
    llm_config = get_llm_config()

    db_file = os.path.abspath(os.path.expanduser(os.getenv("RECEPTIONIST_DB", "./data/receptionist.sqlite3")))
    # Tool servers receive only the business data paths, never provider/gateway keys.
    child_env = {
        "RECEPTIONIST_DB": db_file,
        "BUSINESS_PROFILE": os.environ.get("BUSINESS_PROFILE", "./business-profile.json"),
    }

    def server_params(module: str) -> StdioServerParameters:
        return StdioServerParameters(
            command=sys.executable,
            args=["-m", module],
            env=child_env,
        )

    async with AsyncExitStack() as stack:
        business_info = await stack.enter_async_context(
            MCPClient(server_params=server_params("margin_guard.mcp.business_info"))
        )
        request_inbox = await stack.enter_async_context(
            MCPClient(
                server_params=server_params("margin_guard.mcp.request_inbox"),
                tools_filter=["create_caller_request"],
            )
        )
        business_tools = await business_info.tools()
        inbox_tools = await request_inbox.tools()
        tools = [*business_tools, *inbox_tools]

        tts_provider = os.getenv("VOICE_TTS_PROVIDER", "auto").strip().lower()
        tts_router = None
        if tts_provider == "auto":
            hindi_tts = _speech_output("piper")
            kokoro_tts = _speech_output("kokoro")
            tts_router = ResponseLanguageTTSRouter(hindi_tts, kokoro_tts)
            tts = ServiceSwitcher(services=[hindi_tts, kokoro_tts])
        else:
            tts = _speech_output(tts_provider)
        llm_base_url = llm_config.base_url
        if llm_config.provider == "ollama" and llm_base_url:
            llm_base_url = llm_base_url.rstrip("/")
            if not llm_base_url.endswith("/v1"):
                llm_base_url += "/v1"
        llm = OpenAILLMService(
            api_key=llm_config.api_key,
            base_url=llm_base_url,
            settings=OpenAILLMService.Settings(
                model=llm_config.model,
                system_instruction=SYSTEM_INSTRUCTIONS,
                max_completion_tokens=180,
            ),
        )
        context = LLMContext(tools=tools)
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
        )
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_aggregator,
                llm,
                *([tts_router] if tts_router else []),
                tts,
                transport.output(),
                assistant_aggregator,
            ]
        )
        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        )
        runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
        await runner.add_workers(worker)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            from margin_guard.receptionist_profile import load_profile

            profile = load_profile()
            greeting = str(profile.get("greeting", "Hello. How can I help?"))
            context.add_message({"role": "developer", "content": f"Open with this exact greeting: {greeting}"})
            await worker.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            await runner.cancel()

        await runner.run()


async def bot(runner_args: RunnerArguments) -> None:
    transport_params = {
        "exotel": lambda: FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


def main() -> None:
    from dotenv import load_dotenv
    from pipecat.runner.run import main as runner_main

    load_dotenv()
    runner_main()


if __name__ == "__main__":
    main()
