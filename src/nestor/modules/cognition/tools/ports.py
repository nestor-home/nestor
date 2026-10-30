"""The tool provider port: a source of tools whose set may change while Nestor runs."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from nestor.core import Component
from nestor.modules.cognition.tools.types import Tool


class ToolProvider(Component, ABC):
    """Contract: `tools` is cheap and reflects the current state (a connection enabled or revoked
    changes it); tool names are unique across providers."""

    @abstractmethod
    def tools(self) -> Sequence[Tool]: ...
