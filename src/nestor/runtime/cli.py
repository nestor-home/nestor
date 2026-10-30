"""`nestor` command line: run the assistant, or check a configuration."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from nestor.core import NestorError
from nestor.runtime.app import Nestor, run_until_stopped
from nestor.runtime.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nestor", description="Run a Nestor home assistant.")
    parser.add_argument("-c", "--config", type=Path, default=Path("nestor.yaml"), help="configuration file")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logs")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="serve every configured channel")
    commands.add_parser("check", help="validate the configuration and build the adapters, without starting them")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        nestor = Nestor(load_config(args.config))
        if args.command == "check":
            names = ", ".join(c.channel_id for c in nestor.channels)
            print(f"{args.config}: OK — {len(nestor.executors)} executor(s), channels: {names}")
            return 0
        asyncio.run(run_until_stopped(nestor))
    except NestorError as error:
        print(f"nestor: {error}", file=sys.stderr)
        return 2
    return 0
