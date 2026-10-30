"""`nestor` command line: run the assistant, check a configuration, hash the admin password, pair satellites.

It sits at the top of the package, above both the runtime and the admin interface it starts.
"""

import argparse
import asyncio
import getpass
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

from nestor.admin import AdminServer, hash_password, read_token, token_path
from nestor.core import Component, NestorError
from nestor.init import initialise
from nestor.modules.satellites.wire import SCHEMAS, write_schemas
from nestor.runtime.app import Nestor, run_until_stopped
from nestor.runtime.config import NestorConfig, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nestor", description="Run a Nestor home assistant.")
    parser.add_argument("-c", "--config", type=Path, default=Path("nestor.yaml"), help="configuration file")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logs")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="serve every configured channel")
    commands.add_parser("check", help="validate the configuration and build the adapters, without starting them")
    commands.add_parser("admin-password", help="hash an admin password for the `admin.password_hash` setting")
    commands.add_parser("init", help="write a first configuration and its secrets (never overwrites)")
    satellites = commands.add_parser("satellites", help="pair satellites with the running instance").add_subparsers(
        dest="action", required=True
    )
    approve = satellites.add_parser("approve", help="approve the device showing this 6-digit code")
    approve.add_argument("code")
    approve.add_argument("--only", help="capabilities to grant, comma-separated (default: all it declared)")
    satellites.add_parser("revoke", help="unpair a satellite").add_argument("device_id")
    schemas = satellites.add_parser("schemas", help="write the wire protocol's JSON Schemas")
    schemas.add_argument("--out", type=Path, default=None, help="folder (default: the package's schemas)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        if args.command == "admin-password":
            return _admin_password()
        if args.command == "init":
            return _init(args.config)
        if args.command == "satellites":
            return _satellites(args)
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


def _satellites(args: argparse.Namespace) -> int:
    if args.action == "schemas":
        for path in write_schemas(args.out or SCHEMAS):
            print(f"wrote {path}")
        return 0
    config = load_config(args.config)
    if args.action == "approve":
        body: dict[str, object] = {"code": args.code}
        if args.only is not None:
            body["capabilities"] = [c.strip() for c in args.only.split(",") if c.strip()]
        answer = _call(config, "/api/satellites/approve", body)
        granted = ", ".join(answer["capabilities"]) or "nothing"
        print(f"paired {answer['device']} ({answer['model']}) in {answer['room']}: may use {granted}")
    else:
        _call(config, f"/api/satellites/{args.device_id}/revoke", {})
        print(f"revoked {args.device_id}")
    return 0


def _call(config: NestorConfig, path: str, body: dict[str, object]) -> dict[str, Any]:
    """POST to the running instance's admin API with the token it wrote at startup."""
    if config.admin is None:
        raise NestorError("the configuration has no `admin` section: satellites are paired through the admin")
    host = "127.0.0.1" if config.admin.host in ("0.0.0.0", "::", "") else config.admin.host
    url = f"http://{host}:{config.admin.port}{path}"
    token = read_token(token_path(config.data_dir))
    try:
        response = httpx.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    except httpx.HTTPError:
        raise NestorError(f"Nestor is not running (no admin answering at {host}:{config.admin.port})") from None
    try:
        answer = response.json()
    except ValueError:
        answer = {}
    if response.status_code == 401:
        raise NestorError("the admin refused the token: is this the instance that wrote it? restart it if unsure")
    if response.status_code >= 400 or not isinstance(answer, dict):
        error = answer.get("error") if isinstance(answer, dict) else None
        raise NestorError(str(error or f"the admin answered HTTP {response.status_code}"))
    return answer
