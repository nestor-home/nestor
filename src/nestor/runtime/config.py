"""The configuration file: what to plug in, for whom, with which persona.

YAML, validated before anything starts. Secrets are never written in it: `${NAME}` is replaced by
the environment variable `NAME`, and a missing variable is an error that names it.
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nestor.core import NestorError, PersonId
from nestor.modules.channels import Address
from nestor.modules.household import Account, Person
from nestor.modules.initiative import QuietHours

_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(NestorError):
    """The configuration cannot be used; the message says where and why."""


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonaConfig(Section):
    name: str
    character: str
    language: str = "French"
    timezone: str = "Europe/Paris"


class PersonConfig(Section):
    id: str
    name: str
    accounts: tuple[str, ...] = ()
    reach: str | None = None

    @field_validator("accounts")
    @classmethod
    def _accounts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for account in value:
            Account.parse(account)
        return value

    def to_person(self) -> Person:
        return Person(
            id=PersonId(self.id),
            name=self.name,
            accounts=tuple(Account.parse(a) for a in self.accounts),
            reach=Address.parse(self.reach) if self.reach else None,
        )


class InitiativeConfig(Section):
    quiet_hours: str | None = None  # "22:30-07:30", in the persona's timezone: nothing spoken unless urgent
    main_room: str | None = None  # the satellite to speak through when the home only knows someone is home
    follow_up_after_s: float = Field(default=180.0, gt=0)  # spoken but unanswered → written after this delay

    @field_validator("quiet_hours")
    @classmethod
    def _quiet_hours(cls, value: str | None) -> str | None:
        if value is not None:
            QuietHours.parse(value)
        return value


class AdminConfig(Section):
    """The admin web interface; without this section, Nestor serves none. Who may sign in is not
    configured here: accounts live in the database (`nestor init`, `nestor accounts create-owner`)."""

    password_hash: str | None = None  # obsolete since accounts: still read so that older files load, then ignored
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=0, le=65535)
    public_url: str | None = None  # how the household's browsers reach it: "https://nestor.example.org"
    relay_url: str = "https://nestor.mathislambert.fr/redirect/oauth"  # OAuth redirect when not served over HTTPS


class AdapterConfig(BaseModel):
    """`kind` picks the plugin; the other keys are its settings, validated by the plugin."""

    model_config = ConfigDict(extra="allow", frozen=True)
    kind: str
    name: str | None = None

    def settings(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class NestorConfig(Section):
    data_dir: Path = Path("data")
    persona: PersonaConfig
    household: tuple[PersonConfig, ...] = Field(min_length=1)
    model: AdapterConfig
    executors: tuple[AdapterConfig, ...] = ()
    channels: tuple[AdapterConfig, ...] = Field(min_length=1)
    triage_model: AdapterConfig | None = None  # small model sorting incoming items; defaults to `model`
    tools: tuple[AdapterConfig, ...] = ()  # tool providers (an MCP server: Home Assistant, Linear…)
    inbound: tuple[AdapterConfig, ...] = ()  # sources watches can watch (a mailbox…)
    presence: AdapterConfig | None = None
    initiative: InitiativeConfig = InitiativeConfig()
    admin: AdminConfig | None = None
    # services accounts are plugged into from the admin; by default every installed one when the admin is on
    connectors: tuple[AdapterConfig, ...] | None = None


def load_config(path: Path | str, environ: dict[str, str] | None = None) -> NestorConfig:
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from None
    return parse_config(text, environ if environ is not None else dict(os.environ), origin=str(path))


def parse_config(text: str, environ: dict[str, str], *, origin: str = "configuration") -> NestorConfig:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"{origin} is not valid YAML: {error}") from None
    try:
        config = NestorConfig.model_validate(_substitute(raw, environ))
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        raise ConfigError(f"{origin}: {problems}") from None
    except NestorError as error:
        raise ConfigError(f"{origin}: {error}") from None
    return config


def _substitute(value: Any, environ: dict[str, str]) -> Any:
    if isinstance(value, str):
        missing = [name for name in _VARIABLE.findall(value) if name not in environ]
        if missing:
            raise ConfigError(f"environment variable {missing[0]} is not set")
        return _VARIABLE.sub(lambda m: environ[m.group(1)], value)
    if isinstance(value, dict):
        return {k: _substitute(v, environ) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, environ) for v in value]
    return value
