"""`nestor init`: a first configuration, its secrets and its owner account, never overwriting what exists.

The admin's chat and satellites are always there, in writing; the satellites' voice needs the `voice` extra. A
messaging channel (Telegram) is written only when the person asks for it.
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

models:                            # any names: the roles refer to them
  main:
    type: language
    provider: openai-compatible
    base_url: {base_url}
    api_key: ${{MODEL_API_KEY}}      # may stay empty for a local server that needs no key
    model: {model}
{speech_models}# With several models, say which answers aloud and which in writing:
# agent:
#   spoken: main
#   written: main

channels:
"""

SPEECH_MODELS = """  ears:                            # hears people speak to a satellite
    type: transcription
    provider: elevenlabs
    api_key: ${{ELEVENLABS_API_KEY}}
    language: {locale}
  voice:                           # the assistant's voice
    type: speech
    provider: elevenlabs
    api_key: ${{ELEVENLABS_API_KEY}}
    voice_id: GPAQQPp9dazaB2bl4zg9
"""

VOICE = """  - kind: satellites               # devices people type on or talk to: `nestor satellites add`
    host: 0.0.0.0
    voice: {{transcription: ears, speech: voice}}
"""

TEXT_ONLY = """  - kind: satellites               # devices people type on: `nestor satellites add`
    host: 0.0.0.0
    # Their voice needs `pip install '{requirement}'`, a transcription and a speech model under models
    # (e.g. ElevenLabs: {{type: transcription, provider: elevenlabs}}, {{type: speech, provider: elevenlabs}}), then:
    # voice: {{transcription: ears, speech: voice}}
"""

WEB = """  - kind: web                      # the admin's chat: write to the assistant from the admin
"""

TELEGRAM = """  - kind: telegram
    token: ${{TELEGRAM_BOT_TOKEN}}   # from @BotFather
"""

FOOTER = """
# home:                             # Home Assistant: who is home, and its actions (Assist's MCP server)
#   kind: home-assistant
#   url: ${{HOME_ASSISTANT_URL}}
#   token: ${{HOME_ASSISTANT_TOKEN}}
#   people: {{{person_id}: person.{person_id}}}
#   # confirmed by the person first, by default: locks, the alarm, garage, gate and doors
#   # sensitive: {{domains: [lock, alarm_control_panel], device_classes: [garage, gate, door], names: [porte]}}

# voices:                           # who speaks to a satellite, from their voice: pip install 'nestor-home[voice-id]'
#   embedder: voices               # under models: {{type: speaker, provider: sherpa-onnx, model: titanet-small}}

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
    voice: bool = False  # the satellites' voice, which needs the `voice` extra
    telegram: bool = False  # a Telegram bot, whose token goes in `.env`

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
    channels = WEB + (VOICE if setup.voice else TEXT_ONLY) + (TELEGRAM if setup.telegram else "")
    text = HEADER + channels + FOOTER
    speech = SPEECH_MODELS.format(locale=setup.locale) if setup.voice else ""
    return text.format(
        speech_models=speech,
        data_dir=data_dir,
        name=setup.name,
        locale=setup.locale,
        language=LANGUAGES[setup.locale],
        timezone=setup.timezone,
        person=setup.person,
        person_id=person_id,
        accounts='[]                   # add "telegram:<your user id>"' if setup.telegram else "[]",
        base_url=setup.base_url,
        model=setup.model,
        requirement=VOICE_REQUIREMENT,
        admin_port=ADMIN_PORT,
    )


def environment_file(setup: Setup) -> str:
    """The `.env` of a first configuration: the instance key, and an empty line for each key to fill."""
    keys = [
        key for key, wanted in (("ELEVENLABS_API_KEY=", setup.voice), ("TELEGRAM_BOT_TOKEN=", setup.telegram)) if wanted
    ]
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
