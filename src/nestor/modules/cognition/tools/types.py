"""A tool: its description for the model, its risk, and the code that runs it."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from nestor.core import NestorError, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.model import ToolSpec

type ToolOutput = str | Mapping[str, object] | list[object]


class Risk(StrEnum):
    READ = "read"  # observes only
    WRITE = "write"  # changes something that can be undone (a light, a note)
    SENSITIVE = "sensitive"  # sends, buys, unlocks: needs confirmation


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolContext:
    """Who asked, and in which conversation: `exchange` is the turn the call belongs to, for the events
    the tool writes."""

    address: Address
    person: PersonId | None = None
    exchange: Exchange | None = None


class ToolFailed(NestorError):
    """A tool could not do what was asked; the message is shown to the model, so it says why."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Tool:
    spec: ToolSpec
    run: Callable[[Mapping[str, object], ToolContext], Awaitable[ToolOutput]]
    risk: Risk = Risk.READ
    timeout_s: float = 10.0

    @property
    def name(self) -> str:
        return self.spec.name
