"""The configuration file: what to plug in, for whom, with which persona.

YAML, validated before anything starts. Secrets are never written in it: `${NAME}` is replaced by
the environment variable `NAME`, `${secret:name}` by the secret `name` of the encrypted vault (set
with `nestor secrets set` or from the admin); a missing one is an error that names it.
"""

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from nestor.core import NestorError, PersonId
from nestor.modules.channels import Address
from nestor.modules.conversation import ENDS_AFTER_S
from nestor.modules.household import Account, Person
from nestor.modules.initiative import QuietHours

_VARIABLE = re.compile(r"\$\{(?:(?P<secret>secret):)?(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\}")
SECRET_KEY = "NESTOR_SECRET_KEY"

type SecretLookup = Callable[[str], str | None]  # a secret's value by name, None when it is not set


ADVANCED: dict[str, Any] = {"advanced": True}  # forms fold such a field away by default


def _located[T](parse: Callable[[str], T], value: str) -> T:
    """A domain parser inside a validator: its refusal becomes a `ValueError`, so pydantic says where."""
    try:
        return parse(value)
    except NestorError as error:
        raise ValueError(str(error)) from None


class ConfigError(NestorError):
    """The configuration cannot be used; the message says where and why."""


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonaConfig(Section):
    name: str
    character: str
    locale: str = "fr-FR"  # BCP 47: the household's language, for every fixed phrase and the admin default
    language: str = "French"  # how the model's instructions name the language it must write in
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
            _located(Account.parse, account)
        return value

    def to_person(self) -> Person:
        return Person(
            id=PersonId(self.id),
            name=self.name,
            accounts=tuple(Account.parse(a) for a in self.accounts),
            reach=Address.parse(self.reach) if self.reach else None,
        )


class ConversationConfig(Section):
    # a turn this long after the last one opens a new conversation, without the earlier turns (as Assist)
    ends_after_s: float = Field(default=ENDS_AFTER_S, gt=0)


class InitiativeConfig(Section):
    quiet_hours: str | None = None  # "22:30-07:30", in the persona's timezone: nothing spoken unless urgent
    main_room: str | None = None  # the satellite to speak through when the home only knows someone is home
    # spoken but unanswered → written after this delay
    follow_up_after_s: float = Field(default=180.0, gt=0, json_schema_extra=ADVANCED)

    @field_validator("quiet_hours")
    @classmethod
    def _quiet_hours(cls, value: str | None) -> str | None:
        if value is not None:
            _located(QuietHours.parse, value)
        return value


class AdminConfig(Section):
    """The admin web interface; without this section, Nestor serves none. Who may sign in is not
    configured here: accounts live in the database (`nestor init`, `nestor accounts create-owner`)."""

    @model_validator(mode="before")
    @classmethod
    def _no_password_hash(cls, value: Any) -> Any:
        if isinstance(value, dict) and "password_hash" in value:
            raise ValueError(
                "password_hash is gone: accounts replaced it. Remove the line, then create the first owner with "
                "`nestor accounts create-owner`"
            )
        return value

    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=0, le=65535)
    public_url: str | None = None  # how the household's browsers reach it: "https://nestor.example.org"
    # OAuth redirect when not served over HTTPS
    relay_url: str = Field(default="https://nestor.mathislambert.fr/redirect/oauth", json_schema_extra=ADVANCED)


class AdapterConfig(BaseModel):
    """`kind` picks the plugin; the other keys are its settings, validated by the plugin."""

    model_config = ConfigDict(extra="allow", frozen=True)
    kind: str
    name: str | None = None

    def settings(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class NestorConfig(Section):
    data_dir: Path = Field(default=Path("data"), json_schema_extra=ADVANCED)
    persona: PersonaConfig
    household: tuple[PersonConfig, ...] = Field(min_length=1)
    model: AdapterConfig
    executors: tuple[AdapterConfig, ...] = ()
    channels: tuple[AdapterConfig, ...] = Field(min_length=1)
    triage_model: AdapterConfig | None = None  # small model sorting incoming items; defaults to `model`
    tools: tuple[AdapterConfig, ...] = ()  # tool providers (an MCP server: Home Assistant, Linear…)
    inbound: tuple[AdapterConfig, ...] = ()  # sources watches can watch (a mailbox…)
    presence: AdapterConfig | None = None
    conversation: ConversationConfig = ConversationConfig()
    initiative: InitiativeConfig = InitiativeConfig()
    admin: AdminConfig | None = None
    # services accounts are plugged into from the admin; by default every installed one when the admin is on
    connectors: tuple[AdapterConfig, ...] | None = None


def load_config(
    path: Path | str, environ: dict[str, str] | None = None, *, secrets: SecretLookup | None = None
) -> NestorConfig:
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from None
    environ = environ if environ is not None else dict(os.environ)
    return parse_config(text, environ, origin=str(path), secrets=secrets)


def parse_config(
    text: str, environ: dict[str, str], *, origin: str = "configuration", secrets: SecretLookup | None = None
) -> NestorConfig:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"{origin} is not valid YAML: {error}") from None
    return validate_config(raw, environ, origin=origin, secrets=secrets)


def validate_config(
    raw: Any, environ: dict[str, str], *, origin: str = "configuration", secrets: SecretLookup | None = None
) -> NestorConfig:
    """The configuration of a parsed document, its references resolved (the vault of its `data_dir` by
    default, opened with `NESTOR_SECRET_KEY`)."""
    lookup = secrets or vault_lookup(raw, environ)
    try:
        config = NestorConfig.model_validate(substitute(raw, environ, lookup))
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        raise ConfigError(f"{origin}: {problems}") from None
    except NestorError as error:
        raise ConfigError(f"{origin}: {error}") from None
    return config


def vault_lookup(raw: Any, environ: dict[str, str]) -> SecretLookup:
    """Secrets read from the vault in the document's `data_dir`, only if the document refers to one."""
    if "${secret:" not in str(raw):
        return lambda name: None
    key = environ.get(SECRET_KEY)
    if not key:
        raise ConfigError(f"the configuration refers to secrets, but {SECRET_KEY} is not set to open the vault")
    from nestor.runtime.secrets import vault_reader  # the vault adapter, only when needed

    data_dir = raw.get("data_dir", "data") if isinstance(raw, dict) else "data"
    return vault_reader(Path(str(substitute(data_dir, environ, lambda name: None))), key)


def substitute(value: Any, environ: dict[str, str], secrets: SecretLookup) -> Any:
    """`value` with every `${NAME}` and `${secret:name}` replaced; a missing one is a `ConfigError`."""
    if isinstance(value, str):

        def resolved(match: re.Match[str]) -> str:
            name = match["name"]
            found = secrets(name) if match["secret"] else environ.get(name)
            if found is None:
                if match["secret"]:
                    raise ConfigError(f"secret {name} is not set: `nestor secrets set {name}`")
                raise ConfigError(f"environment variable {name} is not set")
            return found

        return _VARIABLE.sub(resolved, value)
    if isinstance(value, dict):
        return {k: substitute(v, environ, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, environ, secrets) for v in value]
    return value


def references(value: Any, path: tuple[str | int, ...] = ()) -> list[tuple[tuple[str | int, ...], str, bool]]:
    """Every reference in a document: its path, the name it refers to, whether it is a vault secret."""
    if isinstance(value, str):
        return [(path, m["name"], bool(m["secret"])) for m in _VARIABLE.finditer(value)]
    if isinstance(value, dict):
        return [r for k, v in value.items() for r in references(v, (*path, k))]
    if isinstance(value, list):
        return [r for i, v in enumerate(value) for r in references(v, (*path, i))]
    return []
