"""What other modules contribute to the conversation."""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from nestor.modules.channels import Address
from nestor.modules.conversation.types import Mentioned
from nestor.modules.household import Person
from nestor.modules.identity import Speaker


class Layer(StrEnum):
    """Where a section goes in the instructions, which run from the most stable to the most variable so that a
    provider's prompt cache keeps the most of them."""

    HOUSEHOLD = "household"  # changes now and then, the same for everyone: what is remembered, the watches
    TURN = "turn"  # changes from a turn to the next, or depends on who speaks: the tasks running


type Sections = Mapping[Layer, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnContext:
    """What a turn is about, for the modules that add to its instructions."""

    person: Person | None  # who speaks, when known
    speaker: Speaker  # how it is known: give what belongs to them only when `speaker.private`
    address: Address
    said: str | None  # the person's last messages, or what the agent is asked to convey: what to look up
    mentions: tuple[Mentioned, ...] = ()  # what the person's message names with `@`


class ContextProvider(ABC):
    """Adds to the agent's instructions: how to use the module (`guidance`, the same on every turn) and what
    it knows now (`context`: running tasks, what is remembered…), each section in its layer, none when it has
    nothing to say. Must be fast: it runs before every answer."""

    def guidance(self) -> str | None:
        """How the agent uses this module: fixed for the instance's life, it opens the instructions."""
        return None

    @abstractmethod
    async def context(self, turn: TurnContext) -> Sections: ...


class MentionSource(ABC):
    """A module whose things a message can name with `@` (its people, rooms, executors, accounts), and what naming
    one asks of the agent. Contract: `mentionable` is cheap and never raises (it runs as people type); each handle it
    proposes is `[a-z0-9_-]+`; it offers only what `person` may use (`None`: someone at home, unknown)."""

    @abstractmethod
    def mentionable(self, person: Person | None) -> Iterable[Mentioned]: ...

    @abstractmethod
    def instruction(self, mentioned: Mentioned) -> str:
        """For the model, in English: what it is and what naming it asks for."""


class DocumentReader(ABC):
    """The text of a document someone sent (a PDF, a text file), for the model to read.

    Contract: `reads` says which media types it knows; `read` returns the text, empty when the document has none (a
    scanned page), and `None` when it cannot be read (damaged, encrypted). It never raises for a document's content."""

    @abstractmethod
    def reads(self, media_type: str) -> bool: ...

    @abstractmethod
    async def read(self, data: bytes, media_type: str) -> str | None: ...
