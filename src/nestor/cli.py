"""`nestor` command line: run the assistant, check a configuration, create accounts, pair satellites.

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

from nestor.admin import AdminServer, openapi_text, read_token, token_path
from nestor.core import Component, NestorError, PersonId
from nestor.init import initialise, slug
from nestor.modules.accounts import Role
from nestor.modules.satellites.wire import SCHEMAS, write_schemas
from nestor.runtime.app import Nestor, open_accounts, run_until_stopped
from nestor.runtime.config import NestorConfig, load_config

OPENAPI = Path("web") / "openapi.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nestor", description="Run a Nestor home assistant.")
    parser.add_argument("-c", "--config", type=Path, default=Path("nestor.yaml"), help="configuration file")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logs")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="serve every configured channel")
    commands.add_parser("check", help="validate the configuration and build the adapters, without starting them")
    commands.add_parser(
        "init", help="write a first configuration, its secrets and the owner account (never overwrites)"
    )
    accounts = commands.add_parser("accounts", help="admin accounts").add_subparsers(dest="action", required=True)
    owner = accounts.add_parser("create-owner", help="create an owner account (an existing install's first one)")
    owner.add_argument("--login", help="email or username (default: the person's id)")
    owner.add_argument("--person", help="household person id (default: the first person of the configuration)")
    admin = commands.add_parser("admin", help="the admin web interface").add_subparsers(dest="action", required=True)
    openapi = admin.add_parser("openapi", help="write the API's OpenAPI document (the web front's client)")
    openapi.add_argument("--out", type=Path, default=OPENAPI, help=f"file (default: {OPENAPI})")
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
        if args.command == "admin":
            return _openapi(args.out)
        if args.command == "accounts":
            return _create_owner(load_config(args.config), args.login, args.person)
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
            if nestor.config.admin and nestor.config.admin.password_hash is not None:
                print("note: admin.password_hash is no longer used; run `nestor accounts create-owner`, then remove it")
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
    login = input(f"Your login for the admin, an email or a username [{slug(person)}]: ").strip() or slug(person)
    password = _new_password()
    if password is None:
        return 2
    written = initialise(config, name=name, person=person, login=login, password=password)
    for path in written:
        print(f"wrote {path}")
    print(f"owner account {login!r} created: sign in to the admin with it")
    print("next: fill the API keys in .env, then `nestor -c <config> check` and `run`")
    return 0


def _new_password() -> str | None:
    password = getpass.getpass("Password (10 characters or more): ")
    if getpass.getpass("Again: ") != password:
        print("nestor: the two passwords differ", file=sys.stderr)
        return None
    return password


def _create_owner(config: NestorConfig, login: str | None, person: str | None) -> int:
    chosen = PersonId(person or config.household[0].id)
    login = login or chosen
    password = _new_password()
    if password is None:
        return 2

    async def create() -> None:
        async with open_accounts(config.data_dir, [p.to_person() for p in config.household]) as accounts:
            await accounts.create(login=login, password=password, role=Role.OWNER, person=chosen)

    asyncio.run(create())
    print(f"owner account {login!r} created for {chosen}: restart Nestor if it is running, then sign in")
    return 0


def _openapi(out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(openapi_text())
    print(f"wrote {out}")
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
        answer = _call(config, "POST", "/api/v1/satellites/approvals", body)
        granted = ", ".join(c["name"] for c in answer["capabilities"]) or "nothing"
        print(f"paired {answer['id']} ({answer['model']}) in {answer['room']}: may use {granted}")
    else:
        _call(config, "DELETE", f"/api/v1/satellites/{args.device_id}")
        print(f"revoked {args.device_id}")
    return 0


def _call(config: NestorConfig, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, Any]:
    """Call the running instance's admin API with the token it wrote at startup."""
    if config.admin is None:
        raise NestorError("the configuration has no `admin` section: satellites are paired through the admin")
    host = "127.0.0.1" if config.admin.host in ("0.0.0.0", "::", "") else config.admin.host
    url = f"http://{host}:{config.admin.port}{path}"
    token = read_token(token_path(config.data_dir))
    try:
        response = httpx.request(method, url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    except httpx.HTTPError:
        raise NestorError(f"Nestor is not running (no admin answering at {host}:{config.admin.port})") from None
    try:
        answer = response.json() if response.content else {}
    except ValueError:
        answer = None
    if response.status_code == 401:
        raise NestorError("the admin refused the token: is this the instance that wrote it? restart it if unsure")
    if response.status_code >= 400 or not isinstance(answer, dict):
        error = answer.get("error") if isinstance(answer, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        raise NestorError(str(message or f"the admin answered HTTP {response.status_code}"))
    return answer
