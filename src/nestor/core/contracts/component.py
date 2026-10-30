"""Base class of everything plugged into Nestor (adapters, executors, bodies…)."""

from types import TracebackType
from typing import Self

from nestor.core.contracts.capabilities import Capabilities


class Component:
    """A pluggable part: it has a name, declares its capabilities and owns resources.

    Resources are acquired in `start` and always released in `close`, which must be idempotent.
    Use it as an async context manager so `close` runs even when the body fails.
    """

    name: str = "component"  # a class default; the runtime gives each configured instance its own name
    capabilities: Capabilities = Capabilities()

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
