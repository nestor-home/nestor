"""Ports of usage: the public price catalogue and the ledger's store."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from nestor.core import Component
from nestor.modules.usage.types import Dimension, Group, Interval, Line, Point, Rates, Totals, UsageFilter


class PriceCatalogue(Component, ABC):
    """The public prices of hosted models, looked up by the provider that bills them and the model's name.

    Contract: `rates` answers from memory, never waits on the network, and returns `None` for a model it does not
    list; it reads its last copy at start and keeps it up to date in the background, keeping the last good one while
    the source cannot be read."""

    @abstractmethod
    def rates(self, provider: str, model: str) -> Rates | None: ...


class UsageStore(Component, ABC):
    """The ledger: one line per call, kept from the journal's `usage.recorded` and rebuilt from it at will.

    Contract (checked by `nestor.testing.usage.UsageStoreContract`):
    - `add` keeps a line once, whatever times it is given (by its id), and moves `position` to the greatest seen;
    - every reading counts only the lines `UsageFilter` keeps; `totals` leaves unknown costs out of `cost` and counts
      them in `unknown`;
    - days, weeks and months are those of the time zone given at `open`, a store kept for another is emptied.
    """

    @abstractmethod
    async def open(self, timezone: str) -> None: ...

    @abstractmethod
    async def position(self) -> int:
        """The last journal position it holds; 0 when empty."""

    @abstractmethod
    async def add(self, lines: Sequence[Line]) -> None: ...

    @abstractmethod
    async def totals(self, where: UsageFilter) -> Totals: ...

    @abstractmethod
    async def groups(self, where: UsageFilter, by: Dimension, *, limit: int | None = None) -> list[Group]:
        """Totals by value of `by`, the costliest first."""

    @abstractmethod
    async def series(self, where: UsageFilter, every: Interval, by: Dimension | None = None) -> list[Point]:
        """Totals by bucket of time (the buckets without calls are left out), split by `by` if given."""

    @abstractmethod
    async def lines(self, where: UsageFilter, *, before: int | None = None, limit: int = 50) -> list[Line]:
        """Calls one by one, newest first, those before journal position `before`."""
