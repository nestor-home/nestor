"""`nestor init`: a first configuration, its secrets and its owner account, never overwriting what exists.

Satellites are always there, in writing; their voice needs the `voice` extra. Without it (missing, or
declined), the configuration also talks on Telegram, so a household can write to it before it has a
device.
"""

import asyncio
import importlib.util
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nestor.adapters.channels.satellites.plugin import VOICE_REQUIREMENT
from nestor.core import ContractError, PersonId
from nestor.modules.accounts import MIN_LENGTH, Role, normalise_login
from nestor.modules.household import Person
from nestor.runtime.app import database_path, open_accounts
from nestor.runtime.config import ADMIN_PORT

# The languages Nestor ships catalogues for, as the model's instructions name them.
LANGUAGES = {"en": "English", "fr": "French"}
OPENROUTER = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"

HEADER = """# Nestor configuration — every ${{NAME}} comes from the environment (.env next to this file).
data_dir: {data_dir}

persona:
  name: {name}
  locale: {locale}
  language: {language}
  timezone: {timezone}
  character: |
    You are {name}, the household's assistant: warm, direct, with a sense of humour.

household:
  - id: {person_id}
    name: {person}
    accounts: {accounts}

model:
  kind: openai-compatible
  base_url: {base_url}
  api_key: ${{MODEL_API_KEY}}        # may stay empty for a local server that needs no key
  model: {model}

channels:
"""

VOICE = """  - kind: satellites               # devices people type on or talk to: `nestor satellites add`
    host: 0.0.0.0
    voice:
      speech:
        api_key: ${{ELEVENLABS_API_KEY}}
        voice_id: GPAQQPp9dazaB2bl4zg9
        language: {locale}
  # - kind: telegram
  #   token: ${{TELEGRAM_BOT_TOKEN}}
"""

TEXT_ONLY = """  - kind: satellites               # devices people type on: `nestor satellites add`
    host: 0.0.0.0
    # Their voice needs `pip install '{requirement}'`, then:
    # voice:
    #   speech:
    #     api_key: ${{ELEVENLABS_API_KEY}}
    #     voice_id: GPAQQPp9dazaB2bl4zg9
    #     language: {locale}
  - kind: telegram
    token: ${{TELEGRAM_BOT_TOKEN}}   # from @BotFather
"""

FOOTER = """
# presence:
#   kind: home-assistant
#   url: ${{HOME_ASSISTANT_URL}}
#   token: ${{HOME_ASSISTANT_TOKEN}}
#   people: {{{person_id}: person.{person_id}}}
# tools:
#   - kind: mcp
#     name: home
#     url: ${{HOME_ASSISTANT_MCP_URL}}
#     token: ${{HOME_ASSISTANT_TOKEN}}

admin:                             # who signs in is in the database: `nestor accounts create-owner`
  host: 0.0.0.0
  port: {admin_port}
"""

ENV = """# Secrets for Nestor. Never commit this file.
# nestor reads it next to its configuration at every start; a variable already set in the environment wins.
NESTOR_SECRET_KEY={secret_key}
MODEL_API_KEY=
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class Setup:
    """What `nestor init` asks for, the owner's credentials aside."""

    name: str = "Nestor"
    person: str = "Me"
    locale: str = "en"  # one of `LANGUAGES`
    timezone: str = "UTC"
    base_url: str = OPENROUTER
    model: str = DEFAULT_MODEL
    voice: bool = False  # the satellites' voice, which needs the `voice` extra; else Telegram too

    def __post_init__(self) -> None:
        if self.locale not in LANGUAGES:
            raise ContractError(f"choose a language among {', '.join(LANGUAGES)}")
        if not self.model:
            raise ContractError("name the model the server serves")
        if not known_timezone(self.timezone):
            raise ContractError(f"unknown time zone {self.timezone!r}: an IANA name such as Europe/Paris")


def voice_installed() -> bool:
    """Whether the satellites' voice can be built here (the `voice` extra is installed)."""
    return importlib.util.find_spec("pipecat") is not None


def known_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def local_timezone(localtime: Path = Path("/etc/localtime")) -> str:
    """This machine's IANA time zone (`TZ`, else what `/etc/localtime` links to), `UTC` when unknown."""
    candidates = [os.environ.get("TZ", "").removeprefix(":")]
    if localtime.is_symlink():
        candidates.append(str(localtime.resolve()).rpartition("/zoneinfo/")[2])
    return next((name for name in candidates if name and known_timezone(name)), "UTC")


def slug(text: str) -> str:
    kept = "".join(c if c.isalnum() else "-" for c in text.casefold()).strip("-")
    return kept or "me"


def configuration(setup: Setup, data_dir: Path) -> str:
    """The YAML of a first configuration."""
    person_id = slug(setup.person)
    channels = VOICE if setup.voice else TEXT_ONLY
    text = HEADER + channels + FOOTER
    return text.format(
        data_dir=data_dir,
        name=setup.name,
        locale=setup.locale,
        language=LANGUAGES[setup.locale],
        timezone=setup.timezone,
        person=setup.person,
        person_id=person_id,
        accounts='["satellites:*"]' + ("" if setup.voice else '     # add "telegram:<your chat id>"'),
        base_url=setup.base_url,
        model=setup.model,
        requirement=VOICE_REQUIREMENT,
        admin_port=ADMIN_PORT,
    )


def environment_file(setup: Setup) -> str:
    """The `.env` of a first configuration: the instance key, and an empty line for each key to fill."""
    keys = ["ELEVENLABS_API_KEY="] if setup.voice else ["TELEGRAM_BOT_TOKEN="]
    return ENV.format(secret_key=secrets.token_urlsafe(48)) + "".join(f"{key}\n" for key in keys)


def initialise(config: Path, setup: Setup, *, login: str, password: str) -> list[Path]:
    """Write the configuration, its `.env` and the owner account when absent; returns what was written."""
    if len(password) < MIN_LENGTH:  # refuse a weak password or login before writing anything
        raise ContractError(f"choose a password of at least {MIN_LENGTH} characters")
    normalise_login(login)
    written: list[Path] = []
    config.parent.mkdir(parents=True, exist_ok=True)
    env = config.parent / ".env"
    if not env.exists():
        env.write_text(environment_file(setup))
        env.chmod(0o600)
        written.append(env)
    if not config.exists():
        data_dir = config.parent.resolve() / "state"
        config.write_text(configuration(setup, data_dir))
        written.append(config)
        asyncio.run(_owner(data_dir, setup.person, login, password))
        written.append(database_path(data_dir))
    return written


async def _owner(data_dir: Path, person: str, login: str, password: str) -> None:
    first = Person(id=PersonId(slug(person)), name=person)
    async with open_accounts(data_dir, [first]) as accounts:
        await accounts.create(login=login, password=password, role=Role.OWNER, person=first.id)
