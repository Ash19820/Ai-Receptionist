"""Optional Pipecat entry point for live voice conversations."""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack

from mcp import StdioServerParameters
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
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


SYSTEM_INSTRUCTIONS = """You are a concise, friendly receptionist for one small business.
Use the verified profile and FAQ tools for business facts. Never invent prices,
hours, services, availability, policies, or promises. Reply in the caller's
language where possible, using natural spoken phrasing. Ask one short question
at a time and collect only details needed for the request. Before creating a
callback or appointment request, read back the caller's name, contact number,
service, and preferred time as applicable, then wait for an explicit yes. Set
caller_confirmed=true only after the caller gives that yes.
Requests are saved for staff review and are not confirmed bookings. Do not claim
a slot is booked. If you are unsure, offer a human handoff using configured
business information; do not claim a handoff happened unless an integration
confirms it. Do not provide professional advice outside the configured services."""


def _speech_output():
    provider = os.getenv("VOICE_TTS_PROVIDER", "sarvam").strip().lower()
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
            ),
        )
    if provider == "kokoro":
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.transcriptions.language import Language

        return KokoroTTSService(
            settings=KokoroTTSService.Settings(
                voice=os.getenv("KOKORO_VOICE", "hf_alpha"),
                language=Language.HI,
            ),
        )
    raise RuntimeError("VOICE_TTS_PROVIDER must be 'sarvam' or 'kokoro'.")


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    from pipecat.services.sarvam.stt import SarvamSTTService

    sarvam_key = os.getenv("SARVAM_API_KEY")
    if not sarvam_key:
        raise RuntimeError("Set SARVAM_API_KEY to use the configured Indian-language speech recognizer.")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY for the receptionist language model.")

    db_file = os.path.abspath(os.path.expanduser(os.getenv("RECEPTIONIST_DB", "./data/receptionist.sqlite3")))
    child_env = {**os.environ, "RECEPTIONIST_DB": db_file}

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

        stt = SarvamSTTService(
            api_key=sarvam_key,
            settings=SarvamSTTService.Settings(
                model=os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
            ),
        )
        tts = _speech_output()
        llm = OpenAILLMService(
            api_key=os.environ["OPENAI_API_KEY"],
            settings=OpenAILLMService.Settings(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                system_instruction=SYSTEM_INSTRUCTIONS,
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
    from pipecat.runner.run import main as runner_main

    runner_main()


if __name__ == "__main__":
    main()
