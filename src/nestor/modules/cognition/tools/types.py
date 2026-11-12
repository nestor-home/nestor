"""A tool: its description for the model, its risk, and the code that runs it."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from nestor.core import NestorError, PersonId
from nestor.modules.channels import Address, Attachment, Exchange
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.identity import Speaker

type ToolOutput = str | Mapping[str, object] | list[object]


@dataclass(frozen=True, slots=True)
class Made:
    """What a tool returns when it made files (a picture): `output` goes to the model, `files` go with the answer,
    where the channel can send them."""

    output: ToolOutput
    files: tuple[Attachment, ...]


class Risk(StrEnum):
    READ = "read"  # observes only
    WRITE = "write"  # changes something that can be undone (a light, a note)
    SENSITIVE = "sensitive"  # unlocks, disarms, opens the garage, sends for someone: confirmed by the person first


_NOBODY = Speaker.unknown()


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolContext:
    """Who asked, and in which conversation: `exchange` is the turn the call belongs to, for the events
    the tool writes. `speaker` says how sure anyone is of who asked."""

    address: Address
    speaker: Speaker = _NOBODY
    exchange: Exchange | None = None

    @property
    def person(self) -> PersonId | None:
        return self.speaker.person


@dataclass(frozen=True, slots=True)
class SensitiveWhen:
    """The calls of a tool that are sensitive for what they act on: one of the `arguments`' values appears in the
    call's argument of that name, ignoring case (`garage` in `device_class`, `lock` in `domain`, `porte` in a
    `name`). A rule written by the household for its own devices: a home server's tools cover lights and locks
    alike. `tool` `None`: every tool of the server that acts (a home's rule for its doors, whichever tool opens
    them)."""

    tool: str | None
    arguments: Mapping[str, tuple[str, ...]]

    def applies_to(self, tool: str, risk: Risk) -> bool:
        """Whether it judges this tool's calls: the tool it names, or any with `tool` `None`. A rule never makes a
        tool that only reads sensitive."""
        return risk is not Risk.READ and self.tool in (None, tool)

    def matches(self, arguments: Mapping[str, object]) -> bool:
        """Whether a call it applies to acts on what it names."""
        for name, values in self.arguments.items():
            given = arguments.get(name)
            found = given if isinstance(given, list | tuple) else [given] if given is not None else []
            if any(v.casefold() in str(g).casefold() for g in found for v in values):
                return True
        return False


def bounded(value: object, *, default: int, maximum: int) -> int:
    """A count a model gave as an argument, between 1 and `maximum`; `default` when it gave none or no number."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    try:
        return max(1, min(int(value), maximum))
    except ValueError:
        return default


class ToolFailed(NestorError):
    """A tool could not do what was asked; the message is shown to the model, so it says why."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Tool:
    """`risk` is the tool's; `assess`, when given, decides it call by call from the arguments (turning a light off is
    a write, unlocking the door is sensitive). `owner` is the person whose own data it reads or acts on (their
    mailbox): it serves them only."""

    spec: ToolSpec
    run: Callable[[Mapping[str, object], ToolContext], Awaitable[ToolOutput | Made]]
    risk: Risk = Risk.READ
    assess: Callable[[Mapping[str, object]], Risk] | None = None
    owner: PersonId | None = None
    timeout_s: float = 60.0  # at most: past the turn's wait, it goes on in the background

    @property
    def name(self) -> str:
        return self.spec.name

    def risk_of(self, arguments: Mapping[str, object]) -> Risk:
        return self.assess(arguments) if self.assess is not None else self.risk

    @property
    def may_need_confirming(self) -> bool:
        return self.risk is Risk.SENSITIVE or self.assess is not None
