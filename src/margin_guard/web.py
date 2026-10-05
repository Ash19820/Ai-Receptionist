from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agents import Runner

from margin_guard.agent import agent_session
from margin_guard.db import initialize


STATIC = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)


class ApprovalRequest(BaseModel):
    request_id: str
    approved: bool


def make_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv()
        initialize()
        async with agent_session() as agent:
            app.state.agent = agent
            app.state.pending: dict[str, dict[str, Any]] = {}
            yield

    app = FastAPI(title="Common AI Receptionist", lifespan=lifespan)

    @app.get("/")
    async def home():
        return FileResponse(STATIC / "index.html")

    async def run_turn(input_value: Any) -> dict[str, Any]:
        result = await Runner.run(app.state.agent, input_value)
        approvals = []
        if result.interruptions:
            state = result.to_state()
            request_id = uuid.uuid4().hex
            app.state.pending[request_id] = {"state": state, "interruptions": result.interruptions}
            for interruption in result.interruptions:
                try:
                    args = json.loads(interruption.arguments)
                except (TypeError, ValueError):
                    args = {}
                if interruption.name == "create_caller_request":
                    kinds = {"appointment": "Appointment request / अपॉइंटमेंट", "callback": "Callback request / वापस कॉल", "information": "Information request / जानकारी", "other": "Customer request / ग्राहक की बात"}
                    summary = f"{kinds.get(args.get('request_type'), 'Customer request')} — {args.get('summary', '')}"
                    details = [args.get("caller_name"), args.get("caller_phone"), args.get("service"), args.get("preferred_time")]
                    summary += "\n" + " · ".join(str(value) for value in details if value)
                else:
                    summary = "इस बदलाव को सेव करने से पहले ध्यान से देखें।"
                approvals.append({
                    "summary": summary,
                })
            return {"reply": "कॉलर की जानकारी सेव करने से पहले देखें। / Review before saving caller details.",
                    "approval": {"request_id": request_id, "actions": approvals}}
        return {"reply": str(result.final_output), "approval": None}

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        if not body.message.strip():
            raise HTTPException(400, "Type a question or use speech input first.")
        return await run_turn(body.message.strip())

    @app.post("/api/approval")
    async def approval(body: ApprovalRequest):
        pending = app.state.pending.pop(body.request_id, None)
        if not pending:
            raise HTTPException(404, "This approval expired. Please try again.")
        state = pending["state"]
        for interruption in pending["interruptions"]:
            if body.approved:
                state.approve(interruption)
            else:
                state.reject(interruption)
        return await run_turn(state)

    return app


app = make_app()


def main() -> None:
    import uvicorn

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in .env before starting the AI receptionist.")
    uvicorn.run("margin_guard.web:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
