"""The tool provider port: a source of tools whose set may change while Nestor runs."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from nestor.core import Component
from nestor.modules.cognition.model import ToolCall
from nestor.modules.cognition.tools.types import Tool, ToolContext, ToolOutput


class ToolProvider(Component, ABC):
    """Contract: `tools` is cheap and reflects the current state (a connection enabled or revoked
    changes it); tool names are unique across providers."""

    @abstractmethod
    def tools(self) -> Sequence[Tool]: ...


class InWriting(ABC):
    """The person's own written channel, which their account authenticates: what a shared device cannot settle
    goes there. A sensitive action asked aloud is confirmed there; what belongs to someone, asked by a voice nobody
    recognised, is written to them there."""

    @abstractmethod
    async def confirm(self, call: ToolCall, context: ToolContext, *, about: str) -> ToolOutput:
        """Ask `context.person` to confirm `call` (`about`: what the tool does) in writing; once they do, it runs
        where it was asked. Returns what the agent tells the room meanwhile."""

    @abstractmethod
    async def send(self, call: ToolCall, output: str, context: ToolContext) -> ToolOutput:
        """Write what `call` found to `context.person`; returns what the agent tells the room meanwhile."""
