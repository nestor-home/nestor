"""`nestor init`: a first configuration and its secrets, never overwriting what exists."""

import secrets
from pathlib import Path

from nestor.admin import hash_password

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

admin:
  host: 0.0.0.0
  port: 8080
  password_hash: "{password_hash}"
"""

ENV = """# Secrets for Nestor. Never commit this file.
NESTOR_SECRET_KEY={secret_key}
OPENROUTER_API_KEY=
ELEVENLABS_API_KEY=
"""


def slug(text: str) -> str:
    kept = "".join(c if c.isalnum() else "-" for c in text.casefold()).strip("-")
    return kept or "me"


def initialise(config: Path, *, name: str, person: str, password: str) -> list[Path]:
    """Write the configuration and its `.env` when absent; returns what was written."""
    password_hash = hash_password(password)  # refuse a weak password before writing anything
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
                password_hash=password_hash,
            )
        )
        written.append(config)
    return written
