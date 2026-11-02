"""What other modules contribute to the conversation."""

from abc import ABC, abstractmethod
from enum import StrEnum

from nestor.modules.channels import Address
from nestor.modules.household import Person


class Layer(StrEnum):
    """Where a module's context goes in the instructions, which run from the most stable to the most
    variable so that a provider's prompt cache keeps the most of them."""

    HOUSEHOLD = "household"  # changes now and then, the same for everyone: what is remembered, the watches
    TURN = "turn"  # changes from a turn to the next, or depends on who speaks: the tasks running


class ContextProvider(ABC):
    """Adds to the agent's instructions: how to use the module (`guidance`, the same on every turn)
    and what it knows now (`context`, in its `layer`: running tasks, what is remembered…), `None`
    when it has nothing to say. Must be fast: it runs before every answer."""

    layer: Layer = Layer.TURN

    def guidance(self) -> str | None:
        """How the agent uses this module: fixed for the instance's life, it opens the instructions."""
        return None

    @abstractmethod
    async def context(self, person: Person | None, address: Address) -> str | None: ...
