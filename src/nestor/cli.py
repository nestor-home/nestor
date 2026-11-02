"""`nestor` command line: run the assistant, check a configuration, create accounts, pair satellites, check
one against the standard, and benchmark parts of Nestor.

It sits at the top of the package, above both the runtime and the admin interface it starts.
"""

import argparse
import asyncio
import getpass
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.admin import AdminServer, openapi_text, read_token, token_path
from nestor.bench import Suites
from nestor.bench.cli import add_commands as add_bench_commands
from nestor.bench.cli import main as bench
from nestor.core import Component, NestorError, PersonId
from nestor.core.i18n import Locale, Message
from nestor.init import (
    DEFAULT_MODEL,
    LANGUAGES,
    OPENROUTER,
    VOICE_REQUIREMENT,
    Setup,
    initialise,
    local_timezone,
    slug,
    voice_installed,
)
from nestor.modules.accounts import Role
from nestor.modules.satellites import PairingMethod
from nestor.modules.satellites.wire import SCHEMAS, write_schemas
from nestor.runtime.app import Nestor, open_accounts, run_until_stopped
from nestor.runtime.config import ENV_FILE, SECRET_KEY, NestorConfig, environment, load_config
from nestor.runtime.secrets import ConfigFile, open_secrets, preview

OPENAPI = Path("web") / "openapi.json"
CONFORMANCE_DEADLINE_S = 15.0


def main(argv: list[str] | None = None) -> int:
    words = _Words()
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
    owner = accounts.add_parser("create-owner", help="create an owner account (when `nestor init` did not)")
    owner.add_argument("--login", help="email or username (default: the person's id)")
    owner.add_argument("--person", help="household person id (default: the first person of the configuration)")
    admin = commands.add_parser("admin", help="the admin web interface").add_subparsers(dest="action", required=True)
    openapi = admin.add_parser("openapi", help="write the API's OpenAPI document (the web front's client)")
    openapi.add_argument("--out", type=Path, default=OPENAPI, help=f"file (default: {OPENAPI})")
    satellites = commands.add_parser("satellites", help="pair satellites with the running instance").add_subparsers(
        dest="action", required=True
    )
    add = satellites.add_parser("add", help="make an enrollment code (and its pairing URI) to add a satellite")
    add.add_argument("--room", help="the room to pair it into (default: the one it declares)")
    add.add_argument("--name", help="what the household calls it")
    add.add_argument("--method", default="enrollment.provisioning", choices=ENROLLMENT_METHODS,
                     help="how the device gets the code (default: enrollment.provisioning)")  # fmt: skip
    approve = satellites.add_parser("approve", help="approve the device presenting this 6-digit code")
    approve.add_argument("code")
    approve.add_argument("--only", help="capabilities to grant, comma-separated (default: all it declared)")
    satellites.add_parser("revoke", help="unpair a satellite").add_argument("device_id")
    schemas = satellites.add_parser("schemas", help="write the wire protocol's JSON Schemas")
    schemas.add_argument("--out", type=Path, default=None, help="folder (default: the package's schemas)")
    conformance = satellites.add_parser(
        "conformance",
        usage="%(prog)s [-h] [--deadline SECONDS] -- COMMAND [ARGUMENT ...]",
        help=words("conformance-help"),
        description=words("conformance-description"),
        epilog=words("conformance-epilog"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    conformance.add_argument("--deadline", type=float, default=CONFORMANCE_DEADLINE_S, metavar="SECONDS",
                             help=words("conformance-deadline-help", seconds=CONFORMANCE_DEADLINE_S))  # fmt: skip
    conformance.add_argument("satellite", nargs=argparse.REMAINDER, metavar="-- COMMAND",
                             help=words("conformance-command-help"))  # fmt: skip
    add_bench_commands(commands.add_parser("bench", help=words("bench-help"), description=words("bench-help")), words)
    commands.add_parser("restart", help="restart the running instance (applies the configuration written since)")
    secrets = commands.add_parser("secrets", help="the configuration's secrets, kept in the encrypted vault")
    actions = secrets.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="every secret: set or not, a preview, the configuration fields using it")
    setting = actions.add_parser("set", help="set a secret (asked for without echo; never as an argument)")
    setting.add_argument("name")
    setting.add_argument("--from-stdin", action="store_true", help="read the value from standard input (scripts)")
    deleting = actions.add_parser("delete", help="forget a secret")
    deleting.add_argument("name")
    deleting.add_argument("--force", action="store_true", help="even while the configuration refers to it")
    args = parser.parse_args(argv)

    # their output is the findings
    checking = args.command == "bench" or (args.command == "satellites" and args.action == "conformance")
    level = logging.DEBUG if args.verbose else logging.WARNING if checking else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    environ = environment(args.config)  # the shell's variables, completed by the `.env` next to the configuration
    try:
        if args.command == "admin":
            return _openapi(args.out)
        if args.command == "accounts":
            return _create_owner(load_config(args.config, environ), args.login, args.person)
        if args.command == "init":
            return _init(args.config)
        if args.command == "satellites" and args.action == "conformance":
            return _conformance(args.satellite, args.deadline, words)
        if args.command == "bench":
            suites = Suites.installed()
            words = _Words(("nestor", *suites.packages()))  # with the catalogues of suites from other packages
            return bench(args, suites, words.render, words.localizer, words.locale)
        if args.command == "satellites":
            return _satellites(args, environ)
        if args.command == "secrets":
            return _secrets(args, environ)
        if args.command == "restart":
            _call(load_config(args.config, environ), "POST", "/api/v1/system/restart", {"confirm": True})
            print("restarting: the instance stops cleanly, then starts again")
            return 0
        nestor = Nestor(load_config(args.config, environ), environ=environ, source=args.config)
        extras = _admin_server(nestor)
        if args.command == "check":
            names = ", ".join(c.channel_id for c in nestor.channels)
            admin = f", admin on {nestor.config.admin.host}:{nestor.config.admin.port}" if nestor.config.admin else ""
            print(f"{args.config}: OK — {len(nestor.executors)} executor(s), channels: {names}{admin}")
            return 0
        asyncio.run(run_until_stopped(nestor, extras))
        if nestor.restart.requested:  # asked for by a person: the same command line again
            os.execv(sys.executable, sys.orig_argv)
    except NestorError as error:
        print(f"nestor: {error}", file=sys.stderr)
        if args.command in ("check", "run"):
            _report_empty(args.config, environ, str(error))
        return 2
    return 0


def _report_empty(config: Path, environ: dict[str, str], error: str) -> None:
    """Name the empty variables behind the fields an error names (`token: required, but empty`): a key
    left blank in the `.env`."""
    try:
        empty = ConfigFile(config, environ).empty()
    except NestorError:
        return
    for name, fields in sorted(empty.items()):
        named = [f for f in fields if f"{f.rpartition('.')[2]}:" in error]
        if named:
            where = f"in {config.parent / ENV_FILE} or the environment"
            print(f"nestor: {name} is empty ({where}), used by {', '.join(named)}", file=sys.stderr)


def _admin_server(nestor: Nestor) -> list[Component]:
    if nestor.config.admin is None:
        return []
    return [AdminServer.from_config(nestor)]


def _init(config: Path) -> int:
    if config.exists():
        print(f"{config} already exists: nothing changed")
        return 0
    name = _ask("Name of the assistant", "Nestor")
    person = _ask("Your first name", "Me")
    locale = _ask(f"Language of the household ({', '.join(LANGUAGES)})", "en")
    timezone = _ask("Time zone", local_timezone())
    print(
        "The model: any OpenAI-compatible server. Local ones need no key: Ollama http://localhost:11434/v1,\n"
        "LM Studio http://localhost:1234/v1 (from Docker, http://host.docker.internal:<port>/v1)."
    )
    base_url = _ask("Model server", OPENROUTER)
    model = _ask("Model", DEFAULT_MODEL if base_url == OPENROUTER else "")
    if voice_installed():
        voice = _ask("Talk to it by voice (an ElevenLabs key is needed)? y/n", "y").casefold().startswith("y")
    else:
        voice = False
        print(f"Voice is not installed (pip install '{VOICE_REQUIREMENT}'): a text-only configuration, on Telegram.")
    setup = Setup(
        name=name, person=person, locale=locale, timezone=timezone, base_url=base_url, model=model, voice=voice
    )
    login = _ask("Your login for the admin, an email or a username", slug(person))
    password = _new_password()
    if password is None:
        return 2
    written = initialise(config, setup, login=login, password=password)
    for path in written:
        print(f"wrote {path}")
    print(f"owner account {login!r} created: sign in to the admin with it")
    print(f"next: fill the keys in {config.parent / ENV_FILE} (no need to source it), then `nestor -c {config} check`")
    return 0


def _ask(question: str, default: str) -> str:
    return input(f"{question} [{default}]: " if default else f"{question}: ").strip() or default


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


def _secrets(args: argparse.Namespace, environ: dict[str, str]) -> int:
    """Directly on the vault of the configuration's data folder: no running instance is needed."""
    file = ConfigFile(args.config, environ)
    used = file.used()

    async def run() -> int:
        async with open_secrets(file.data_dir, environ.get(SECRET_KEY)) as secrets:
            if args.action == "list":
                for name in sorted({*await secrets.names(), *used}):
                    value = await secrets.value(name)
                    state = f"set     {preview(value)}" if value else "not set"
                    where = ", ".join(used.get(name, [])) or "unused"
                    print(f"{name}  {state}  ({where})")
                return 0
            if args.action == "set":
                value = sys.stdin.read().rstrip("\n") if args.from_stdin else getpass.getpass(f"{args.name}: ")
                await secrets.set(args.name, value, by="cli")
                print(f"secret {args.name} set (restart Nestor for the configuration to use a new value)")
                return 0
            if used.get(args.name) and not args.force:
                print(
                    f"nestor: {args.name} is still used by {', '.join(used[args.name])}: remove those references, "
                    "or pass --force",
                    file=sys.stderr,
                )
                return 2
            if not await secrets.delete(args.name, by="cli"):
                print(f"nestor: no secret {args.name}", file=sys.stderr)
                return 2
            print(f"secret {args.name} deleted")
            return 0

    return asyncio.run(run())


ENROLLMENT_METHODS = [m.value for m in PairingMethod if m.proof.value == "enrollment_code"]


def _satellites(args: argparse.Namespace, environ: dict[str, str]) -> int:
    if args.action == "schemas":
        for path in write_schemas(args.out or SCHEMAS):
            print(f"wrote {path}")
        return 0
    config = load_config(args.config, environ)
    if args.action == "add":
        asked = {"method": args.method} | {k: v for k in ("room", "name") if (v := getattr(args, k)) is not None}
        started = _call(config, "POST", "/api/v1/satellites/additions", asked)
        print(f"enrollment code {started['code']}, valid until {started['addition']['expires_at']}")
        if started.get("uri"):
            print(f"pairing URI: {started['uri']}  (NESTOR_PAIRING_URI on the device)")
        return 0
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


class _Words:
    """The command's words, in the language of the environment (`LC_ALL`, `LC_MESSAGES`, `LANG`)."""

    def __init__(self, packages: tuple[str, ...] = ("nestor",)) -> None:
        self.localizer = FluentLocalizer(catalogue_dirs(packages))
        wanted = next((v for k in ("LC_ALL", "LC_MESSAGES", "LANG") if (v := os.environ.get(k))), "")
        self.locale = Locale(wanted.split(".")[0].split("@")[0] or "en")

    def __call__(self, message_id: str, **args: str | int | float) -> str:
        return self.render(Message.of(message_id, **args))

    def render(self, message: Message) -> str:
        return self.localizer.format(message, self.locale)


def _conformance(command: list[str], deadline_s: float, words: _Words) -> int:
    """Run the black-box conformance suite on a satellite's command line; 0 when it conforms."""
    command = command[1:] if command[:1] == ["--"] else command
    if not command:
        print(words("conformance-no-command"), file=sys.stderr)
        return 2
    if shutil.which(command[0]) is None:
        print(words("conformance-no-program", program=command[0]), file=sys.stderr)
        return 2
    from nestor.adapters.channels.satellites.conformance import check_satellite  # audio checks need `voice`

    findings = asyncio.run(check_satellite(command, deadline_s=deadline_s))
    for finding in findings.items:
        check = words.render(finding.check)
        if finding.passed:
            print(words("conformance-passed", check=check))
        elif finding.detail is None:
            print(words("conformance-failed", check=check))
        else:
            print(words("conformance-failed-detail", check=check, detail=words.render(finding.detail)))
    failed, total = len(findings.failures()), len(findings.items)
    if failed:
        print(words("conformance-not-conformant", count=failed, total=total))
        return 1
    print(words("conformance-conformant", total=total))
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
