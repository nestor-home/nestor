"""Adapter plugins: a kind name, a validated configuration and a factory.

Built-in and third-party adapters declare themselves the same way, in their package metadata:

    [project.entry-points."nestor.adapters"]
    telegram = "nestor.adapters.channels.telegram:plugin"
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from nestor.core import Component, ContractError

ENTRY_POINTS = "nestor.adapters"


class Family(StrEnum):
    MODEL = "model"
    EXECUTOR = "executor"
    CHANNEL = "channel"
    PRESENCE = "presence"
    TOOLS = "tools"
    INBOUND = "inbound"


class AdapterSettings(BaseModel):
    """Base of every adapter's configuration: unknown keys are errors, not silently ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class Services:
    """What the runtime lends to adapter factories."""

    data_dir: Path


@dataclass(frozen=True, slots=True)
class Plugin[S: AdapterSettings]:
    family: Family
    kind: str
    settings: type[S]
    build: Callable[[S, str, Services], Component]  # settings, the instance name, services

    def create(self, raw: Mapping[str, Any], name: str, services: Services) -> Component:
        try:
            settings = self.settings.model_validate(raw)
        except ValidationError as error:
            raise ContractError(f"{self.family} {name!r} ({self.kind}): {_explain(error)}") from None
        return self.build(settings, name, services)


class Registry:
    def __init__(self, plugins: Iterable[Plugin[Any]] = ()) -> None:
        self._plugins: dict[tuple[Family, str], Plugin[Any]] = {}
        for plugin in plugins:
            self.register(plugin)

    @classmethod
    def installed(cls) -> "Registry":
        """Every plugin declared by an installed package."""
        registry = cls()
        for entry in entry_points(group=ENTRY_POINTS):
            plugin = entry.load()
            if not isinstance(plugin, Plugin):
                raise ContractError(f"entry point {entry.name!r} ({entry.value}) is not a nestor Plugin")
            registry.register(plugin)
        return registry

    def register(self, plugin: Plugin[Any]) -> None:
        key = (plugin.family, plugin.kind)
        if key in self._plugins:
            raise ContractError(f"two plugins provide the {plugin.family} kind {plugin.kind!r}")
        self._plugins[key] = plugin

    def get(self, family: Family, kind: str) -> Plugin[Any]:
        try:
            return self._plugins[(family, kind)]
        except KeyError:
            known = ", ".join(sorted(k for f, k in self._plugins if f is family)) or "none installed"
            raise ContractError(f"unknown {family} kind {kind!r} (available: {known})") from None


def _explain(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'}: {e['msg']}" for e in error.errors())
