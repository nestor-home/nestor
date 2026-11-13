"""Adapter plugins: a kind name, a validated configuration and a factory.

Built-in and third-party adapters declare themselves the same way, in their package metadata:

    [project.entry-points."nestor.adapters"]
    telegram = "nestor.adapters.channels.telegram:plugin"
    elevenlabs-transcription = "nestor.adapters.models.elevenlabs:transcription"

A model plugin serves one type of model for a provider: its kind is the provider, `serves` the type's base class
(`TranscriptionModel`), and the configuration names it by both (`type: transcription`, `provider: elevenlabs`).

Discovering plugins loads every entry point, so a plugin module imports only what its settings need.
An adapter relying on optional dependencies imports them when it is built and names, in `requires`,
the requirement that installs them: a configuration using it without them fails with that requirement.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import entry_points
from pathlib import Path
from typing import Annotated, Any, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_core import PydanticCustomError

from nestor.core import Component, ContractError, Model, ModelType
from nestor.core.i18n import Locale, Localizer
from nestor.modules.connectors import Connector

ENTRY_POINTS = "nestor.adapters"


class Family(StrEnum):
    MODEL = "model"  # builds a `Model` of the type it serves, for a provider
    EXECUTOR = "executor"
    CHANNEL = "channel"
    HOME = "home"  # builds a `Home`: the home system, its presence and its actions
    TOOLS = "tools"
    INBOUND = "inbound"
    CONNECTOR = "connector"  # builds a `Connector`: a service the household plugs accounts into from the admin


def _filled(value: SecretStr) -> SecretStr:
    if not value.get_secret_value():
        raise PydanticCustomError("empty_secret", "required, but empty")
    return value


# A key or token the adapter cannot work without: an empty one (a blank line of the `.env`) is refused.
RequiredSecret = Annotated[SecretStr, AfterValidator(_filled)]


class AdapterSettings(BaseModel):
    """Base of every adapter's configuration: unknown keys are errors, not silently ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ChannelSettings(AdapterSettings):
    """Base of a channel's configuration: what every channel lets a household adjust."""

    # silence after which the next turn opens a new conversation; None: the default of the channel's medium
    conversation_ends_after_s: float | None = Field(default=None, gt=0, json_schema_extra={"advanced": True})


def _no_models(key: str, wanted: type[Model], path: tuple[str | int, ...]) -> Model:
    raise ContractError(f"{'.'.join(map(str, path))}: no model named {key!r} here (models are not built yet)")


@dataclass(frozen=True, slots=True)
class Services:
    """What the runtime lends to adapter factories."""

    data_dir: Path
    localizer: Localizer  # renders what adapters say to people (a channel's apology, a setup guide…)
    locale: Locale  # the household's language (the persona's locale)
    # finds a model of `models` by key (see `model`); the runtime lends it once models are built
    models: Callable[[str, type[Model], tuple[str | int, ...]], Model] = field(default=_no_models)

    def model[M: Model](self, key: str, wanted: type[M], path: tuple[str | int, ...]) -> M:
        """The model of `models` an adapter's settings name by `key`, at `path` in those settings: the runtime
        refuses an unknown key or a model of another type than `wanted`."""
        return cast(M, self.models(key, wanted, path))


@dataclass(frozen=True, slots=True)
class Plugin[S: AdapterSettings]:
    family: Family
    kind: str
    settings: type[S]
    build: Callable[[S, str, Services], Component | Connector]  # settings, the instance name, services
    requires: str | None = None  # the optional dependencies `build` imports, as a pip requirement ("pkg[extra]")
    serves: type[Model] | None = None  # the type of model a plugin of the model family builds: it must say

    def __post_init__(self) -> None:
        if (self.family is Family.MODEL) != (self.serves is not None):
            raise ContractError(
                f"plugin {self.kind!r}: a model plugin says the type it serves, and only a model plugin"
            )

    @property
    def model_type(self) -> ModelType | None:
        return self.serves.type if self.serves is not None else None

    @property
    def id(self) -> str:
        """What tells it apart in its family: its kind, and for a model, its provider and type (`elevenlabs-speech`)."""
        return f"{self.kind}-{self.serves.type}" if self.serves is not None else self.kind

    def create(self, raw: Mapping[str, Any], name: str, services: Services) -> Any:
        """The built adapter (a `Connector` for the connector family, a `Component` otherwise); the
        runtime checks it is what the family expects."""
        try:
            settings = self.settings.model_validate(raw)
        except ValidationError as error:
            raise ContractError(f"{self.family} {name!r} ({self.id}): {_explain(error)}") from None
        try:
            return self.build(settings, name, services)
        except ModuleNotFoundError as missing:
            if self.requires is None:
                raise
            raise ContractError(
                f"{self.family} {name!r} ({self.id}) needs {self.requires}, which is not installed "
                f"(no module {(missing.name or '').partition('.')[0]!r}): pip install '{self.requires}'"
            ) from None


BUILT_IN = "nestor-home"  # the distribution of Nestor's own plugins


@dataclass(frozen=True, slots=True)
class Distribution:
    """The installed package a plugin comes from (`nestor-home` for the built-in ones)."""

    name: str
    version: str


@dataclass(frozen=True, slots=True)
class Plugged:
    """One configured adapter as the runtime built it: what the admin's system page lists."""

    family: Family
    id: str  # the plugin's (`Plugin.id`)
    name: str
    component: Component | Connector
    origin: Distribution | None


class Registry:
    def __init__(self, plugins: Iterable[Plugin[Any]] = ()) -> None:
        self._plugins: dict[tuple[Family, str], Plugin[Any]] = {}
        self._origins: dict[tuple[Family, str], Distribution] = {}
        for plugin in plugins:
            self.register(plugin)

    @classmethod
    def installed(cls, *, distribution: str | None = None) -> "Registry":
        """Every plugin declared by an installed package, or only by `distribution` (`nestor-home`: the built-in
        ones, whatever else is installed)."""
        registry = cls()
        for entry in entry_points(group=ENTRY_POINTS):
            if distribution is not None and (entry.dist is None or entry.dist.name != distribution):
                continue
            plugin = entry.load()
            if not isinstance(plugin, Plugin):
                raise ContractError(f"entry point {entry.name!r} ({entry.value}) is not a nestor Plugin")
            dist = entry.dist
            registry.register(plugin, Distribution(dist.name, dist.version) if dist is not None else None)
        return registry

    def packages(self) -> tuple[str, ...]:
        """Top-level packages providing plugins: where their `locales/` catalogues are looked for."""
        return tuple(dict.fromkeys(p.build.__module__.partition(".")[0] for p in self._plugins.values()))

    def register(self, plugin: Plugin[Any], origin: Distribution | None = None) -> None:
        key = (plugin.family, plugin.id)
        if key in self._plugins:
            raise ContractError(f"two plugins provide the {plugin.family} {plugin.id!r}")
        self._plugins[key] = plugin
        if origin is not None:
            self._origins[key] = origin

    def origin(self, family: Family, id: str) -> Distribution | None:
        """Where an installed plugin comes from; `None` for one registered by code (tests)."""
        return self._origins.get((family, id))

    def ids(self, family: Family) -> list[str]:
        """The ids of the plugins installed for a family (`Plugin.id`), sorted."""
        return sorted(i for f, i in self._plugins if f is family)

    def get(self, family: Family, id: str) -> Plugin[Any]:
        try:
            return self._plugins[(family, id)]
        except KeyError:
            known = ", ".join(self.ids(family)) or "none installed"
            raise ContractError(f"no {family} plugin {id!r} is installed (available: {known})") from None


def _explain(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'}: {e['msg']}" for e in error.errors())
