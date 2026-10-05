from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


READ_ONLY = {
    "get_business_profile",
    "list_business_services",
    "search_business_faq",
    "get_open_requests",
}
WRITE_TOOLS = {
    "create_caller_request",
}


def make_agent(business_info_server: MCPServerStdio, request_inbox_server: MCPServerStdio) -> Agent:
    return Agent(
        name="Common AI Receptionist",
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=(
            "You are a configurable, multilingual AI receptionist for a small business. The verified "
            "business profile, services, hours, service area, and FAQs are available through tools. "
            "Use short, natural spoken language; reply in the caller's language where possible. "
            "Answer only from the profile and FAQ tools. Do not invent prices, hours, availability, "
            "policies, or promises. Gather only the details needed for the caller's request. Before "
            "creating a callback or appointment request, read back the name, contact number, service, "
            "and preferred time and get an explicit yes. Set caller_confirmed=true only after that yes. "
            "Such requests are pending staff review, not "
            "confirmed appointments. Never claim a slot is booked unless a scheduling integration "
            "confirms it. If unsure, ask one concise question or offer a human handoff. Don't provide "
            "professional advice outside the configured services. Never make payments, send messages, "
            "or promise a callback until the relevant tool or integration confirms the action."
        ),
        mcp_servers=[business_info_server, request_inbox_server],
    )


def approval_policy() -> dict:
    return {
        "always": {"tool_names": sorted(WRITE_TOOLS)},
        "never": {"tool_names": sorted(READ_ONLY)},
    }


@asynccontextmanager
async def agent_session(*, include_open_requests: bool = False) -> AsyncIterator[Agent]:
    db_file = str(Path(os.environ.get("RECEPTIONIST_DB", "./data/receptionist.sqlite3")).expanduser().resolve())
    env = {**os.environ, "RECEPTIONIST_DB": db_file}
    common = {"command": sys.executable, "env": env}
    async with (
        MCPServerStdio(
            name="Business facts",
            params={**common, "args": ["-m", "margin_guard.mcp.business_info"]},
            require_approval=approval_policy(),
        ) as business_info,
        MCPServerStdio(
            name="Caller request inbox",
            params={**common, "args": ["-m", "margin_guard.mcp.request_inbox"]},
            tool_filter=None if include_open_requests else {"blocked_tool_names": ["get_open_requests"]},
            require_approval=approval_policy(),
        ) as request_inbox,
    ):
        yield make_agent(business_info, request_inbox)


async def run_agent_turn(agent: Agent, prompt: str) -> str:
    result = await Runner.run(agent, prompt)
    while result.interruptions:
        state = result.to_state()
        for interruption in result.interruptions:
            print("\nApproval required")
            print(f"Tool: {interruption.name}")
            print(f"Arguments: {interruption.arguments}")
            try:
                decision = input("Run this change? [y/N] ").strip().lower()
            except EOFError:
                decision = "n"
            if decision in {"y", "yes"}:
                state.approve(interruption)
            else:
                state.reject(interruption)
        result = await Runner.run(agent, state)
    return str(result.final_output)
