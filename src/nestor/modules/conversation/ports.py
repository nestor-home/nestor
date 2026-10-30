"""What other modules contribute to the conversation."""

from abc import ABC, abstractmethod

from nestor.modules.channels import Address
from nestor.modules.household import Person


class ContextProvider(ABC):
    """Adds a section to the agent's instructions for this turn: running tasks, what is known
    about the person, who is home… Returns `None` when it has nothing to say. Must be fast: it
    runs before every answer."""

    @abstractmethod
    async def context(self, person: Person | None, address: Address) -> str | None: ...
