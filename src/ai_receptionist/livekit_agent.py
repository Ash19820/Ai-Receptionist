"""Optional LiveKit Agents entrypoint; the FastAPI diagnostics path stays separate."""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

from ai_receptionist.business import BusinessProfile
from ai_receptionist.callback_inbox import CallbackInbox, CallbackMessageWorkflow
from ai_receptionist.config import Settings
from ai_receptionist.policy import parse_allowed_languages
from ai_receptionist.livekit_runtime import (
    LiveKitRuntimeConfig,
    build_livekit_instructions,
)

logger = logging.getLogger(__name__)


def _build_agent(workflow: CallbackMessageWorkflow, instructions: str):
    """Create the LiveKit adapter only after the optional package is installed."""
    try:
        from livekit.agents import Agent, RunContext, function_tool
    except ImportError as exc:
        raise RuntimeError(
            "LiveKit support is optional. Install it with `uv pip install -e '.[livekit]'`."
        ) from exc

    class ReceptionistAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=instructions)

        @function_tool()
        async def request_callback_message_consent(
            self, context: RunContext
        ) -> dict[str, object]:
            """Give the caller the callback-message notice and request permission."""
            del context
            return {
                "consent_notice": workflow.request_consent(),
                "instruction": "Speak this notice, then wait for a clear yes before collecting details.",
            }

        @function_tool()
        async def prepare_callback_message(
            self,
            context: RunContext,
            caller_name: str,
            callback_number: str,
            message: str,
        ) -> dict[str, object]:
            """Prepare and read back a caller-approved callback message without saving."""
            del context
            try:
                return workflow.prepare(caller_name, callback_number, message)
            except ValueError as exc:
                return {"prepared": False, "error": str(exc)}

        @function_tool()
        async def save_confirmed_callback_message(
            self, context: RunContext, draft_id: str
        ) -> dict[str, object]:
            """Persist a message only after the server observed a clear final yes."""
            del context
            try:
                saved = await asyncio.to_thread(workflow.save, draft_id)
            except ValueError as exc:
                return {"stored": False, "error": str(exc)}
            except (OSError, RuntimeError):
                logger.exception("LiveKit callback message could not be saved")
                return {"stored": False, "error": "Local callback storage is unavailable."}
            return {
                "stored": True,
                "expires_at": saved.expires_at,
                "instruction": (
                    "Tell the caller the message is in this computer's local inbox. "
                    "No person was automatically notified or connected."
                ),
            }

    return ReceptionistAgent()


load_dotenv()

try:
    from livekit import agents
    from livekit.agents import AgentServer, AgentSession
    from livekit.plugins import google
except ImportError:
    # The base app and its direct Gemini/Local test paths do not require LiveKit.
    server = None
else:
    server = AgentServer()

    @server.rtc_session(agent_name="ai-receptionist")
    async def receptionist_session(ctx: agents.JobContext) -> None:
        try:
            config = LiveKitRuntimeConfig.from_environment()
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

        settings = Settings.from_environment()
        business_context = BusinessProfile(settings.business_profile_path).prompt_context()
        languages = parse_allowed_languages(
            os.getenv("ASSISTANT_ALLOWED_LANGUAGES", "English")
        )
        instructions = build_livekit_instructions(business_context, languages)
        inbox = CallbackInbox(
            settings.callback_message_db_path,
            settings.callback_message_retention_days,
        )
        workflow = CallbackMessageWorkflow(inbox)
        session = AgentSession(
            llm=google.realtime.RealtimeModel(
                model=config.model,
                voice=config.voice,
                api_key=config.gemini_api_key,
            )
        )

        @session.on("user_input_transcribed")
        def observe_final_transcript(event) -> None:
            # Consent and save confirmation are based on final caller audio
            # transcription observed by the application, not model inference.
            if getattr(event, "is_final", False):
                workflow.observe_user_transcript(str(getattr(event, "transcript", "")))

        await session.start(
            room=ctx.room,
            agent=_build_agent(workflow, instructions),
        )
        await session.generate_reply(
            instructions=f"Greet the caller briefly in {languages[0]} and ask how you can help."
        )
