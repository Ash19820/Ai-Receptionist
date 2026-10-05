from __future__ import annotations

import asyncio
import os

from margin_guard.agent import agent_session, run_agent_turn
from margin_guard.db import db_path, initialize


def load_dotenv() -> None:
    from dotenv import load_dotenv as load

    load()


async def chat_loop() -> None:
    async with agent_session(include_open_requests=True) as agent:
        print("AI Receptionist — business information and caller requests")
        print(f"Local request inbox: {db_path()}")
        print("Ask about services, hours, policies, or leave a callback request. Type 'quit' to exit.\n")
        while True:
            try:
                prompt = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if prompt.lower() in {"quit", "exit"}:
                break
            if not prompt:
                continue
            try:
                response = await run_agent_turn(agent, prompt)
                print(f"\nReceptionist> {response}\n")
            except KeyboardInterrupt:
                print("\nTurn cancelled.\n")
            except Exception as exc:
                print(f"\nTurn failed: {exc}\n")


def main() -> None:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in your environment or .env file, then start the AI receptionist again.")
        raise SystemExit(2)
    initialize()
    try:
        asyncio.run(chat_loop())
    except KeyboardInterrupt:
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
