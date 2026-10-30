"""`nestor` command line: run the assistant, check a configuration, hash the admin password.

It sits at the top of the package, above both the runtime and the admin interface it starts.
"""

import argparse
import asyncio
import getpass
import logging
import sys
from pathlib import Path

from nestor.admin import AdminServer, hash_password
from nestor.core import Component, NestorError
from nestor.init import initialise
from nestor.runtime.app import Nestor, run_until_stopped
from nestor.runtime.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nestor", description="Run a Nestor home assistant.")
    parser.add_argument("-c", "--config", type=Path, default=Path("nestor.yaml"), help="configuration file")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logs")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="serve every configured channel")
    commands.add_parser("check", help="validate the configuration and build the adapters, without starting them")
    commands.add_parser("admin-password", help="hash an admin password for the `admin.password_hash` setting")
    commands.add_parser("init", help="write a first configuration and its secrets (never overwrites)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        if args.command == "admin-password":
            return _admin_password()
        if args.command == "init":
            return _init(args.config)
        nestor = Nestor(load_config(args.config))
        extras = _admin_server(nestor)
        if args.command == "check":
            names = ", ".join(c.channel_id for c in nestor.channels)
            admin = f", admin on {nestor.config.admin.host}:{nestor.config.admin.port}" if nestor.config.admin else ""
            print(f"{args.config}: OK — {len(nestor.executors)} executor(s), channels: {names}{admin}")
            return 0
        asyncio.run(run_until_stopped(nestor, extras))
    except NestorError as error:
        print(f"nestor: {error}", file=sys.stderr)
        return 2
    return 0


def _admin_server(nestor: Nestor) -> list[Component]:
    if nestor.config.admin is None:
        return []
    return [AdminServer.from_config(nestor)]


def _init(config: Path) -> int:
    if config.exists():
        print(f"{config} already exists: nothing changed")
        return 0
    name = input("Name of the assistant [Nestor]: ").strip() or "Nestor"
    person = input("Your first name: ").strip() or "Moi"
    password = _new_password()
    if password is None:
        return 2
    written = initialise(config, name=name, person=person, password=password)
    for path in written:
        print(f"wrote {path}")
    print("next: fill the API keys in .env, then `nestor -c <config> check` and `run`")
    return 0


def _new_password() -> str | None:
    password = getpass.getpass("Admin password (10 characters or more): ")
    if getpass.getpass("Again: ") != password:
        print("nestor: the two passwords differ", file=sys.stderr)
        return None
    return password


def _admin_password() -> int:
    password = _new_password()
    if password is None:
        return 2
    print(hash_password(password))
    return 0
