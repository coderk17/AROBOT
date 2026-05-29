"""Entry point for the WeCom intelligent customer service bot."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

from arobot.agent.service_agent import CustomerServiceAgent
from arobot.channels.wecom import WeComChannel
from arobot.config import settings


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def run_bot() -> None:
    load_dotenv()
    _setup_logging()

    agent = CustomerServiceAgent()
    await agent.setup()

    channel = WeComChannel(agent)
    try:
        await channel.start()
    finally:
        await agent.aclose()


async def run_console() -> None:
    """Local REPL for testing without WeCom."""
    load_dotenv()
    _setup_logging()
    print("ARobot console mode. Type 'quit' to exit.\n")

    agent = CustomerServiceAgent()
    await agent.setup()
    try:
        while True:
            try:
                user_input = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_input or user_input.lower() in {"quit", "exit", "q"}:
                break
            if user_input.startswith("/file "):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 2:
                    print("Usage: /file <path> [question]")
                    continue
                path = parts[1]
                question = parts[2] if len(parts) > 2 else "请分析这份报表"
                reply = await agent.ainvoke(question, file_path=path)
            else:
                reply = await agent.ainvoke(user_input)
            print(f"\nBot> {reply}\n")
    finally:
        await agent.aclose()


def cli() -> None:
    parser = argparse.ArgumentParser(description="ARobot intelligent customer service")
    parser.add_argument(
        "mode",
        nargs="?",
        default="bot",
        choices=["bot", "console"],
        help="bot: WeCom channel | console: local test",
    )
    args = parser.parse_args()

    if args.mode == "console":
        asyncio.run(run_console())
    else:
        asyncio.run(run_bot())


if __name__ == "__main__":
    cli()
    sys.exit(0)
