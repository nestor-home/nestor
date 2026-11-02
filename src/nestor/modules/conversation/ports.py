"""What other modules contribute to the conversation."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from nestor.modules.channels import Address
from nestor.modules.household import Person


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
    address: Address
    said: str | None  # the person's last messages, or what the agent is asked to convey: what to look up


class ContextProvider(ABC):
    """Adds to the agent's instructions: how to use the module (`guidance`, the same on every turn) and what
    it knows now (`context`: running tasks, what is remembered…), each section in its layer, none when it has
    nothing to say. Must be fast: it runs before every answer."""

    def guidance(self) -> str | None:
        """How the agent uses this module: fixed for the instance's life, it opens the instructions."""
        return None

    @abstractmethod
    async def context(self, turn: TurnContext) -> Sections: ...
