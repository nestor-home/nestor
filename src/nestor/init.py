"""`nestor init`: a first configuration, its secrets and its owner account, never overwriting what exists."""

import asyncio
import secrets
from pathlib import Path

from nestor.core import ContractError, PersonId
from nestor.modules.accounts import MIN_LENGTH, Role, normalise_login
from nestor.modules.household import Person
from nestor.runtime.app import database_path, open_accounts

TEMPLATE = """# Nestor configuration — every ${{NAME}} comes from the environment (.env next to this file).
data_dir: {data_dir}

persona:
  name: {name}
  language: French
  timezone: Europe/Paris
  character: |
    Tu es {name}, l'assistant de la maison : chaleureux, direct, avec de l'humour.

household:
  - id: {person_id}
    name: {person}
    accounts: ["voice:*"]          # add "telegram:<your chat id>" once the bot knows you

model:
  kind: openai-compatible
  base_url: https://openrouter.ai/api/v1
  api_key: ${{OPENROUTER_API_KEY}}
  model: anthropic/claude-haiku-5.5

channels:
  - kind: voice
    room: salon
    host: 0.0.0.0
    speech:
      api_key: ${{ELEVENLABS_API_KEY}}
      voice_id: GPAQQPp9dazaB2bl4zg9
  # - kind: telegram
  #   token: ${{TELEGRAM_BOT_TOKEN}}

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
  port: 8080
"""

ENV = """# Secrets for Nestor. Never commit this file.
NESTOR_SECRET_KEY={secret_key}
OPENROUTER_API_KEY=
ELEVENLABS_API_KEY=
"""


def slug(text: str) -> str:
    kept = "".join(c if c.isalnum() else "-" for c in text.casefold()).strip("-")
    return kept or "me"


def initialise(config: Path, *, name: str, person: str, login: str, password: str) -> list[Path]:
    """Write the configuration, its `.env` and the owner account when absent; returns what was written."""
    if len(password) < MIN_LENGTH:  # refuse a weak password or login before writing anything
        raise ContractError(f"choose a password of at least {MIN_LENGTH} characters")
    normalise_login(login)
    written: list[Path] = []
    config.parent.mkdir(parents=True, exist_ok=True)
    env = config.parent / ".env"
    if not env.exists():
        env.write_text(ENV.format(secret_key=secrets.token_urlsafe(48)))
        env.chmod(0o600)
        written.append(env)
    if not config.exists():
        config.write_text(
            TEMPLATE.format(
                data_dir=config.parent.resolve() / "state",
                name=name,
                person=person,
                person_id=slug(person),
            )
        )
        written.append(config)
        asyncio.run(_owner(config.parent.resolve() / "state", person, login, password))
        written.append(database_path(config.parent.resolve() / "state"))
    return written


async def _owner(data_dir: Path, person: str, login: str, password: str) -> None:
    first = Person(id=PersonId(slug(person)), name=person)
    async with open_accounts(data_dir, [first]) as accounts:
        await accounts.create(login=login, password=password, role=Role.OWNER, person=first.id)
