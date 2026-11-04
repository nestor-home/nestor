"""Where the instance learns about newer releases of itself, and how it installs one."""

from abc import ABC, abstractmethod

from nestor.core import Component
from nestor.modules.system.types import Releases


class ReleaseFeed(Component):
    """The published list of releases. Read-only: nothing it says is ever installed or run."""

    @abstractmethod
    async def fetch(self) -> Releases:
        """The feed as published now; `ProviderError` when it cannot be read."""


class Installer(ABC):
    """Installs a release of Nestor where the running one is installed, for the next start. Only
    where that is possible (a Python environment it may write; never a container image)."""

    @abstractmethod
    async def install(self, version: str) -> None:
        """Install `version` and check it starts with this configuration; on any failure, put the running
        version back and raise `ProviderError`."""
