"""Optional Pipecat entry point for live voice conversations."""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack

from mcp import StdioServerParameters
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.service_switcher import ServiceSwitcher
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.mcp_service import MCPClient
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from margin_guard.llm_provider import get_llm_config
from margin_guard.speech.config import DEFAULT_TTS_ROUTES, parse_tts_routes
from margin_guard.speech.providers import create_stt_service, create_tts_service
from margin_guard.speech.registry import load_provider_plugins
from margin_guard.speech.routing import ResponseLanguageTTSRouter


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


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    load_provider_plugins()
    stt_provider = os.getenv("VOICE_STT_PROVIDER", "whisper").strip().lower()
    stt = create_stt_service(stt_provider)
    llm_config = get_llm_config()

    db_file = os.path.abspath(
        os.path.expanduser(os.getenv("RECEPTIONIST_DB", "./data/receptionist.sqlite3"))
    )
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
            routes = parse_tts_routes(
                os.getenv("VOICE_TTS_ROUTES", DEFAULT_TTS_ROUTES)
            )
            default_language = os.getenv("VOICE_TTS_FALLBACK_LANGUAGE", "hi").lower()
            if default_language not in routes:
                raise ValueError(
                    "VOICE_TTS_FALLBACK_LANGUAGE must be a language configured in "
                    "VOICE_TTS_ROUTES."
                )
            services_by_language = {}
            service_cache = {}
            for language, provider in routes.items():
                key = (provider, language)
                if key not in service_cache:
                    service_cache[key] = create_tts_service(provider, language)
                services_by_language[language] = service_cache[key]
            tts_router = ResponseLanguageTTSRouter(
                services=services_by_language,
                default_language=default_language,
                latin_language=os.getenv("VOICE_TTS_LATIN_LANGUAGE", "en").lower(),
            )
            unique_services = list(
                {id(service): service for service in service_cache.values()}.values()
            )
            tts = ServiceSwitcher(services=unique_services)
        else:
            default_language = "en" if tts_provider == "kokoro" else "hi"
            legacy_sarvam_language = (
                os.getenv("SARVAM_TTS_LANGUAGE") if tts_provider == "sarvam" else None
            )
            tts_language = (
                os.getenv("VOICE_TTS_LANGUAGE")
                or legacy_sarvam_language
                or default_language
            ).lower()
            tts = create_tts_service(tts_provider, tts_language)
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
            context.add_message(
                {"role": "developer", "content": f"Open with this exact greeting: {greeting}"}
            )
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
