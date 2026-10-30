"""Base class of everything plugged into Nestor (adapters, executors, bodies…)."""

from collections.abc import Mapping
from enum import StrEnum
from types import TracebackType
from typing import Self

from nestor.core.contracts.capabilities import Capabilities


class Health(StrEnum):
    """What a running component can tell about itself."""

    STARTED = "started"
    DEGRADED = "degraded"  # works, partly (a fallback in use, some of what it offers missing)
    UNAVAILABLE = "unavailable"  # started but cannot serve now (server unreachable, disconnected)


class Component:
    """A pluggable part: it has a name, declares its capabilities and owns resources.

    Resources are acquired in `start` and always released in `close`, which must be idempotent.
    Use it as an async context manager so `close` runs even when the body fails.
    """

    name: str = "component"  # a class default; the runtime gives each configured instance its own name
    capabilities: Capabilities = Capabilities()
    brand: str | None = None  # the vendor or protocol behind it, as a slug people recognise ("telegram")

    def health(self) -> Health:
        """Whether it can serve right now; a component that cannot tell says it runs."""
        return Health.STARTED

    def details(self) -> Mapping[str, str]:
        """What people may want to know about it (its model, its speech service…), never a secret."""
        return {}

    async def start(self) -> None:
        """Acquire resources (connections, sessions). The default component has none."""

    async def close(self) -> None:
        """Release resources. Called once or more; never raises for an already closed component."""

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.close()
