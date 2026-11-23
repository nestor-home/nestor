"""The ledger: what was spent, read from the store that projects the journal's `usage.recorded`.

The store is caught up with the journal when it opens, and before a reading once a call was recorded since the last,
so that what is read is exactly what the journal holds; emptied (another time zone, a new schema), it is rebuilt from
the journal alone. Periods are
the household's: "today" starts at its midnight, "this month" on its first.
"""

import asyncio
import calendar
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nestor.core import Component, Money, utc_now
from nestor.modules.journal import Journal, LogQuery, Subscription
from nestor.modules.usage.events import UsageRecorded
from nestor.modules.usage.ports import Line, UsageStore
from nestor.modules.usage.types import (
    Beat,
    Dimension,
    Group,
    Interval,
    Period,
    Point,
    Span,
    Totals,
    UsageFilter,
)

PAGE = 1000  # journal entries read at a time when catching up
RECORDED = frozenset({UsageRecorded.event_type})
DAYS: Mapping[Period, int] = {Period.TODAY: 1, Period.WEEK: 7, Period.THIRTY_DAYS: 30, Period.QUARTER: 90}
BUCKETS: Mapping[Period, Interval] = {
    Period.TODAY: Interval.HOUR,
    Period.WEEK: Interval.DAY,
    Period.THIRTY_DAYS: Interval.DAY,
    Period.MONTH: Interval.DAY,
    Period.QUARTER: Interval.WEEK,
}


@dataclass(frozen=True, slots=True)
class Summary:
    """A period at a glance, with what to compare it to."""

    span: Span
    totals: Totals
    previous: Totals  # the period of the same length just before
    month: Totals  # the current calendar month, so far
    projected_month: Money  # the month's spending if it goes on as it went so far


class Ledger(Component):
    name = "usage-ledger"

    def __init__(
        self, journal: Journal, store: UsageStore, timezone: str, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.journal, self.store, self.timezone = journal, store, timezone
        self._zone = ZoneInfo(timezone)
        self._clock = clock
        self._lock = asyncio.Lock()
        self._recorded: Subscription | None = None  # the calls recorded since the store last caught up
        self._opened = False

    async def start(self) -> None:
        self._recorded = self.journal.subscribe(UsageRecorded)  # before catching up: no call slips in between
        await self.store.open(self.timezone)
        await self.catch_up()
        self._opened = True

    async def close(self) -> None:
        if self._recorded is not None:
            self._recorded.close()
            self._recorded = None

    async def catch_up(self) -> int:
        """Bring the store up to the journal, if a call was recorded since it last did (or it never did); how many
        calls it added."""
        async with self._lock:
            recorded = self._recorded.drain() if self._recorded is not None else []
            if self._opened and not recorded:
                return 0
            added, after = 0, await self.store.position()
            while entries := await self.journal.log.read(LogQuery(types=RECORDED, after=after, limit=PAGE)):
                lines = [Line(e.position, call) for e in entries if isinstance(call := e.event(), UsageRecorded)]
                await self.store.add(lines)
                added, after = added + len(lines), entries[-1].position
            return added

    def span(self, period: Period) -> Span:
        """A period in the household's clock, up to now."""
        now = self._clock()
        midnight = now.astimezone(self._zone).replace(hour=0, minute=0, second=0, microsecond=0)
        # calendar arithmetic on the household's clock: a day is a day, whatever the summer time
        since = midnight.replace(day=1) if period is Period.MONTH else midnight - timedelta(days=DAYS[period] - 1)
        return Span(since, now, BUCKETS[period])

    async def summary(self, span: Span, only: Mapping[Dimension, frozenset[str | None]]) -> Summary:
        await self.catch_up()
        month = self.span(Period.MONTH)
        totals, previous, so_far = await asyncio.gather(
            self.store.totals(span.keeping(only)),
            self.store.totals(span.before.keeping(only)),
            self.store.totals(month.keeping(only)),
        )
        local = month.until.astimezone(self._zone)
        elapsed = (month.until - month.since) / timedelta(days=calendar.monthrange(local.year, local.month)[1])
        projected = Money(round(so_far.cost.nusd / elapsed)) if elapsed > 0 else so_far.cost
        return Summary(span, totals, previous, so_far, projected)

    async def groups(self, where: UsageFilter, by: Dimension) -> list[Group]:
        await self.catch_up()
        return await self.store.groups(where, by)

    async def series(self, where: UsageFilter, every: Interval, by: Dimension | None = None) -> list[Point]:
        await self.catch_up()
        return await self.store.series(where, every, by)

    async def rhythm(self, where: UsageFilter) -> list[Beat]:
        await self.catch_up()
        return await self.store.rhythm(where)

    async def lines(self, where: UsageFilter, *, before: int | None = None, limit: int = 50) -> list[Line]:
        await self.catch_up()
        return await self.store.lines(where, before=before, limit=limit)
