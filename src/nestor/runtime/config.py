"""The configuration file: what to plug in, for whom, with which persona.

YAML, validated before anything starts. Secrets are never written in it: `${NAME}` is replaced by
the environment variable `NAME`, `${secret:name}` by the secret `name` of the encrypted vault (set
with `nestor secrets set` or from the admin); a missing one is an error that names it. The variables
are the process environment's, completed by the `.env` next to the file (`environment`).
"""

import os
import re
from collections.abc import Callable, Collection, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from nestor.core import ModelType, NestorError, PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.tools.results import RESULT_CHARS
from nestor.modules.conversation import AgentSettings
from nestor.modules.household import Account, Person
from nestor.modules.identity import VoiceSettings
from nestor.modules.initiative import QuietHours
from nestor.modules.memory.recall import RecallSettings, Strategy

_MODEL_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_VARIABLE = re.compile(r"\$\{(?:(?P<secret>secret):)?(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\}")
SECRET_KEY = "NESTOR_SECRET_KEY"
ENV_FILE = ".env"  # next to the configuration: what `nestor init` writes
# Clear of the ports local model servers and dev tools use (llama.cpp's 8080, Gradio's 7860, Ollama's 11434…);
# the satellites channel serves them on the next one.
ADMIN_PORT = 8470

type SecretLookup = Callable[[str], str | None]  # a secret's value by name, None when it is not set


ADVANCED: dict[str, Any] = {"advanced": True}  # forms fold such a field away by default
# a key of `models`, of the type of model the field takes: forms offer only those
LANGUAGE_MODEL: dict[str, Any] = {"reference": "models", "model_type": ModelType.LANGUAGE.value}
EMBEDDING_MODEL: dict[str, Any] = {"reference": "models", "model_type": ModelType.EMBEDDING.value}
SPEAKER_MODEL: dict[str, Any] = {"reference": "models", "model_type": ModelType.SPEAKER.value}
TRANSCRIPTION_MODEL: dict[str, Any] = {"reference": "models", "model_type": ModelType.TRANSCRIPTION.value}
SPEECH_MODEL: dict[str, Any] = {"reference": "models", "model_type": ModelType.SPEECH.value}
IMAGE_MODEL: dict[str, Any] = {"reference": "models", "model_type": ModelType.IMAGE.value}


def _located[T](parse: Callable[[str], T], value: str) -> T:
    """A domain parser inside a validator: its refusal becomes a `ValueError`, so pydantic says where."""
    try:
        return parse(value)
    except NestorError as error:
        raise ValueError(str(error)) from None


class ProblemCode(StrEnum):
    """What is wrong in a configuration; each names its message, `config-error-<code>`."""

    MISSING = "missing"
    EXTRA = "extra"
    INVALID = "invalid"
    UNKNOWN_KIND = "unknown_kind"  # no plugin of that kind is installed
    REFERENCE = "reference"  # an environment variable that is not set
    SECRET = "secret"  # a secret that is not set
    NO_ANSWERING_MODEL = "no_answering_model"
    NOT_ANSWERING = "not_answering"
    NOT_EMBEDDING = "not_embedding"
    NOT_SPEAKER = "not_speaker"
    NOT_TRANSCRIBING = "not_transcribing"
    NOT_SPEAKING = "not_speaking"
    UNKNOWN_MODEL = "unknown_model"  # an adapter's settings name a model `models` does not have
    SHARED_ACCOUNT = "shared_account"


class ConfigError(NestorError):
    """The configuration cannot be used; the message says where and why. For the admin, which says it in the
    reader's language, `path` locates it in the document and `code` names its message (`config-error-<code>`,
    with `detail`)."""

    def __init__(
        self,
        message: str,
        *,
        path: tuple[str | int, ...] = (),
        code: ProblemCode = ProblemCode.INVALID,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.path, self.code = path, code
        self.detail = message if detail is None else detail


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonaConfig(Section):
    name: str
    character: str
    locale: str = "en"  # BCP 47: the household's language, for every fixed phrase and the admin default
    language: str = "English"  # how the model's instructions name the language it must write in
    timezone: str = "UTC"  # IANA name ("Europe/Paris"): the household's clock


class PersonConfig(Section):
    id: str
    name: str
    accounts: tuple[str, ...] = ()
    reach: str | None = None
    may_message: tuple[str, ...] = (
        "*",
    )  # whom else they may have the agent write to: person ids, or "*" (themselves always)

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
            may_message=self.may_message,
        )


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

    host: str = "127.0.0.1"
    port: int = Field(default=ADMIN_PORT, ge=0, le=65535)
    public_url: str | None = None  # how the household's browsers reach it: "https://nestor.example.org"
    # OAuth redirect when not served over HTTPS
    relay_url: str = Field(default="https://nestorhome.dev/redirect/oauth", json_schema_extra=ADVANCED)


class UpdatesConfig(Section):
    """Whether Nestor reads its release feed to tell the admin about newer releases. It installs one only
    when a person asks in the admin, and only where it runs from its own Python environment."""

    check: bool = True
    feed: str = Field(default="https://github.com/nestor-home/nestor/releases/latest/download/releases.json",
                      json_schema_extra=ADVANCED)  # fmt: skip


class ComponentConfig(BaseModel):
    """`kind` picks the plugin; the other keys are its settings, validated by the plugin."""

    model_config = ConfigDict(extra="allow", frozen=True)
    kind: str

    @property
    def plugin(self) -> str:
        """The id of the plugin it picks (`Plugin.id`)."""
        return self.kind

    def settings(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class ModelConfig(BaseModel):
    """A model of `models`: its `type` and its `provider` pick the plugin; `fallback` names the language model of
    `models` that answers when this one fails before answering, for every role it holds; the other keys are its
    settings."""

    model_config = ConfigDict(extra="allow", frozen=True)
    type: ModelType
    provider: str
    fallback: str | None = None

    @property
    def plugin(self) -> str:
        return f"{self.provider}-{self.type}"

    def settings(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class AdapterConfig(ComponentConfig):
    """A component in a list or on its own: `name` tells it apart, its kind by default. A model needs
    none: its key in `models` is its name."""

    name: str | None = None


_AGENT = AgentSettings()


class AgentConfig(Section):
    """Which model of `models` answers in each medium. One left out takes the other's; with a single
    model, neither needs saying. `transcription` hears the voice messages people send and `speech` records the
    answers to them, `images` draws the pictures asked for; each defaults to the only model of its type, and without
    one, voice messages go unheard, answers stay written and no picture is drawn."""

    spoken: str | None = Field(default=None, json_schema_extra=LANGUAGE_MODEL)  # the voice: first words fast
    written: str | None = Field(default=None, json_schema_extra=LANGUAGE_MODEL)  # writing allows a few seconds
    titles: str | None = Field(default=None, json_schema_extra=LANGUAGE_MODEL)  # titles conversations: a small one
    transcription: str | None = Field(default=None, json_schema_extra=TRANSCRIPTION_MODEL)
    speech: str | None = Field(default=None, json_schema_extra=SPEECH_MODEL)
    images: str | None = Field(default=None, json_schema_extra=IMAGE_MODEL)
    # how long a turn waits for a tool before it goes on in the background and its result comes back by itself
    spoken_tool_wait_s: float = Field(default=_AGENT.spoken_tool_wait_s, gt=0, le=60)
    written_tool_wait_s: float = Field(default=_AGENT.written_tool_wait_s, gt=0, le=600)
    # past this, a tool's result goes to the blob store and the turn keeps its start and end
    tool_result_chars: int = Field(default=RESULT_CHARS, ge=1000, le=200_000)


class WatchesConfig(Section):
    """The model that sorts incoming items for the watches: the agent's written one by default."""

    model: str | None = Field(default=None, json_schema_extra=LANGUAGE_MODEL)


_RECALL = RecallSettings()


class MemoryConfig(Section):
    """Which memories each turn's instructions carry (`memory-recall` bench): the latest up to `recent`, cached
    with the household, then those the person's last messages find among the others."""

    strategy: Strategy = _RECALL.strategy
    recent: int = Field(default=_RECALL.recent, ge=0, le=1000)
    found: int = Field(default=_RECALL.found, ge=0, le=50)
    recent_episodes: int = Field(default=_RECALL.recent_episodes, ge=0, le=20)  # whoever speaks: latest conversations
    found_episodes: int = Field(default=_RECALL.found_episodes, ge=0, le=20)  # and older ones their words find
    # the model that summarizes each conversation once it is over: the written one by default
    consolidation: str | None = Field(default=None, json_schema_extra=LANGUAGE_MODEL)
    # an embedding model of `models`: memories are then found by meaning as well as by words
    embedder: str | None = Field(default=None, json_schema_extra=EMBEDDING_MODEL)
    # how long a turn waits for the question's vector before searching by words only
    query_timeout_s: float = Field(default=1.0, gt=0, json_schema_extra=ADVANCED)

    def recall(self) -> RecallSettings:
        return RecallSettings(
            strategy=self.strategy,
            recent=self.recent,
            found=self.found,
            recent_episodes=self.recent_episodes,
            found_episodes=self.found_episodes,
        )


_VOICES = VoiceSettings()


class VoicesConfig(Section):
    """Who speaks on a shared device (a satellite), from their voice: a speaker model of `models` turns speech into
    voiceprints, compared on this machine. Without it, whoever speaks there is someone of the household, nobody
    in particular, and the agent asks who when it matters."""

    embedder: str | None = Field(default=None, json_schema_extra=SPEAKER_MODEL)
    # the similarity from which a voice is someone's: the model's own, calibrated on the `speaker-id` bench
    threshold: float | None = Field(default=None, gt=0, lt=1, json_schema_extra=ADVANCED)
    # how long a turn waits for its voiceprint (computed while the speech is transcribed)
    wait_s: float = Field(default=0.5, gt=0, json_schema_extra=ADVANCED)
    keep: int = Field(default=_VOICES.keep, ge=0, le=500, json_schema_extra=ADVANCED)  # learned voiceprints a person
    per_room: int = Field(default=_VOICES.per_room, ge=0, le=500, json_schema_extra=ADVANCED)  # of them from one room
    anchor_weight: float = Field(default=_VOICES.anchor_weight, ge=0, le=1, json_schema_extra=ADVANCED)
    learn_margin: float = Field(default=_VOICES.learn_margin, ge=0, lt=1, json_schema_extra=ADVANCED)
    learn_lead: float = Field(default=_VOICES.learn_lead, ge=0, lt=1, json_schema_extra=ADVANCED)

    def settings(self) -> VoiceSettings:
        return VoiceSettings(
            threshold=self.threshold,
            keep=self.keep,
            per_room=self.per_room,
            anchor_weight=self.anchor_weight,
            learn_margin=self.learn_margin,
            learn_lead=self.learn_lead,
        )


class NestorConfig(Section):
    data_dir: Path = Field(default=Path("data"), json_schema_extra=ADVANCED)
    persona: PersonaConfig
    household: tuple[PersonConfig, ...] = Field(min_length=1)
    # the models it may use, under names the household chooses; the roles below refer to them by name, and each
    # role checks the model's type
    models: dict[str, ModelConfig] = Field(min_length=1)
    agent: AgentConfig = Field(default=AgentConfig(), validate_default=True)
    watches: WatchesConfig = WatchesConfig()
    memory: MemoryConfig = MemoryConfig()
    voices: VoicesConfig = VoicesConfig()
    executors: tuple[AdapterConfig, ...] = ()
    channels: tuple[AdapterConfig, ...] = Field(min_length=1)
    tools: tuple[AdapterConfig, ...] = ()  # tool providers (an MCP server: Home Assistant, Linear…)
    inbound: tuple[AdapterConfig, ...] = ()  # sources watches can watch (a mailbox…)
    home: ComponentConfig | None = None  # the home system (Home Assistant): presence and actions
    initiative: InitiativeConfig = InitiativeConfig()
    admin: AdminConfig | None = None
    updates: UpdatesConfig = UpdatesConfig()
    # services accounts are plugged into from the admin; by default every installed one when the admin is on
    connectors: tuple[AdapterConfig, ...] | None = None

    @field_validator("models")
    @classmethod
    def _model_keys(cls, value: dict[str, ModelConfig]) -> dict[str, ModelConfig]:
        for key, model in value.items():
            if not _MODEL_KEY.fullmatch(key):
                raise ValueError(f"{key!r} cannot name a model: letters, digits, `_`, `.` and `-`, starting with one")
            if model.fallback is None:
                continue
            fallback = value.get(model.fallback)
            if fallback is None:
                raise ValueError(f"{key}.fallback: no model named {model.fallback!r} in models ({', '.join(value)})")
            if model.type is not ModelType.LANGUAGE or fallback.type is not ModelType.LANGUAGE:
                raise ValueError(f"{key}.fallback: only a language model falls back, on another language model")
        for key in value:
            _chain(value, key)  # no model falls back on itself, through others or not
        return value

    @field_validator("agent")
    @classmethod
    def _agent(cls, value: AgentConfig, info: ValidationInfo) -> AgentConfig:
        _known(
            info,
            {
                "spoken": value.spoken,
                "written": value.written,
                "titles": value.titles,
                "transcription": value.transcription,
                "speech": value.speech,
                "images": value.images,
            },
        )
        return value

    @field_validator("watches")
    @classmethod
    def _watches(cls, value: WatchesConfig, info: ValidationInfo) -> WatchesConfig:
        _known(info, {"model": value.model})
        return value

    @field_validator("memory")
    @classmethod
    def _memory(cls, value: MemoryConfig, info: ValidationInfo) -> MemoryConfig:
        _known(info, {"embedder": value.embedder, "consolidation": value.consolidation})
        return value

    @field_validator("voices")
    @classmethod
    def _voices(cls, value: VoicesConfig, info: ValidationInfo) -> VoicesConfig:
        _known(info, {"embedder": value.embedder})
        return value

    def roles(self, answering: Collection[str]) -> dict[str, str]:
        """The key of the model each role uses, defaults applied: `spoken`, `written`, `titles`, `watches`,
        `consolidation`.
        `answering` are the models that answer (not those that embed): with a single one, every role takes it. A model
        that is only some model's fallback does not count: it answers when that one fails."""
        fallbacks = {m.fallback for m in self.models.values()}
        answering = [key for key in answering if key not in fallbacks]
        sole = answering[0] if len(answering) == 1 else None
        written = self.agent.written or self.agent.spoken or sole
        if written is None:
            among = ", ".join(answering) or "-"
            raise ConfigError(
                f"agent: several models can answer ({among}); say which in `spoken`, `written` or both",
                path=("agent",),
                code=ProblemCode.NO_ANSWERING_MODEL,
                detail=among,
            )
        return {
            "spoken": self.agent.spoken or written,
            "written": written,
            "titles": self.agent.titles or written,
            "watches": self.watches.model or written,
            "consolidation": self.memory.consolidation or written,
        }

    def chain(self, key: str) -> tuple[str, ...]:
        """The model `key` and those that answer in turn when the previous one fails (`fallback`)."""
        return _chain(self.models, key)

    def voice_messages(self) -> tuple[str | None, str | None]:
        """The models that hear voice messages and record the answers to them: those `agent` names, else the only
        model of each type; `None` without one."""
        return (
            self.agent.transcription or _sole(self.models, ModelType.TRANSCRIPTION),
            self.agent.speech or _sole(self.models, ModelType.SPEECH),
        )

    def images(self) -> str | None:
        """The model that draws pictures: the one `agent` names, else the only image model; `None` without one."""
        return self.agent.images or _sole(self.models, ModelType.IMAGE)


def _chain(models: Mapping[str, "ModelConfig"], key: str) -> tuple[str, ...]:
    chain = [key]
    while (fallback := models[chain[-1]].fallback) is not None:
        if fallback in chain:
            raise ValueError(f"{key}.fallback: {' → '.join([*chain, fallback])} falls back in a circle")
        chain.append(fallback)
    return tuple(chain)


def _sole(models: Mapping[str, "ModelConfig"], kind: ModelType) -> str | None:
    of_kind = [key for key, model in models.items() if model.type is kind]
    return of_kind[0] if len(of_kind) == 1 else None


def _known(info: ValidationInfo, references: Mapping[str, str | None]) -> Mapping[str, ModelConfig]:
    """The models declared before, once each reference is checked to name one of them."""
    models: Mapping[str, ModelConfig] = info.data.get("models") or {}
    for field, key in references.items():
        if key is not None and models and key not in models:
            raise ValueError(f"{field}: no model named {key!r} in models ({', '.join(models)})")
    return models


def environment(config: Path | str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The variables a configuration sees: `environ` (the process environment by default), completed by
    the `.env` next to the file when there is one. A variable already set always wins: the shell, a
    service manager or Docker keep the last word, and the file only fills what is missing.

    Standard dotenv syntax (comments, `export`, quotes, empty values); values are taken literally,
    without `${...}` expansion, so a key holding a `$` stays intact. A line that cannot be parsed is
    skipped with a warning naming its line.
    """
    environ = os.environ if environ is None else environ
    path = Path(config).parent / ENV_FILE
    found = dotenv_values(path, interpolate=False, encoding="utf-8") if path.is_file() else {}
    return {**{k: v for k, v in found.items() if v is not None}, **environ}


def load_config(
    path: Path | str, environ: dict[str, str] | None = None, *, secrets: SecretLookup | None = None
) -> NestorConfig:
    """The configuration in `path`, resolved with `environ` (by default, its `environment`)."""
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from None
    environ = environ if environ is not None else environment(path)
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
        raise ConfigError(
            f"the configuration refers to secrets, but {SECRET_KEY} is not set to open the vault "
            f"(in the environment or the {ENV_FILE} next to the configuration)"
        )
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
                raise ConfigError(
                    f"environment variable {name} is not set (in the environment or the {ENV_FILE} next to the "
                    "configuration)"
                )
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
