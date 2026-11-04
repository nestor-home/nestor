"""Where the instance learns about newer releases of itself."""

from abc import abstractmethod

from nestor.core import Component
from nestor.modules.system.types import Releases


class ReleaseFeed(Component):
    """The published list of releases. Read-only: nothing it says is ever installed or run."""

    @abstractmethod
    async def fetch(self) -> Releases:
        """The feed as published now; `ProviderError` when it cannot be read."""
