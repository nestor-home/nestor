"""The ledger: what was spent, read from the store that projects the journal's `usage.recorded`.

The store is caught up with the journal when it opens and before every reading, so that what is read is exactly
what the journal holds; emptied (another time zone, a new schema), it is rebuilt from the journal alone.
"""

import asyncio
import calendar
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nestor.core import Component, Money, Unit, utc_now
from nestor.modules.journal import Entry, Journal, LogQuery
from nestor.modules.usage.events import UsageRecorded
from nestor.modules.usage.ports import UsageStore
from nestor.modules.usage.types import Dimension, Group, Interval, Line, Point, Totals, UsageFilter

PAGE = 1000  # journal entries read at a time when catching up


@dataclass(frozen=True, slots=True)
class Summary:
    """A period at a glance, with what to compare it to."""

    totals: Totals
    previous: Totals  # the period of the same length just before
    month: Totals  # the current calendar month, so far
    projected_month: Money  # the month's spending if it goes on as it went so far
    conversations: int  # conversations the period's calls served


class Ledger(Component):
    name = "usage-ledger"

    def __init__(
        self, journal: Journal, store: UsageStore, timezone: str, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.journal, self.store, self.timezone = journal, store, timezone
        self._zone = ZoneInfo(timezone)
        self._clock = clock
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self.store.open(self.timezone)
        await self.catch_up()

    async def catch_up(self) -> int:
        """Bring the store up to the journal; how many calls it added."""
        async with self._lock:
            added, after = 0, await self.store.position()
            while entries := await self.journal.log.read(
                LogQuery(types=frozenset({UsageRecorded.event_type}), after=after, limit=PAGE)
            ):
                lines = [line for entry in entries if (line := _line(entry)) is not None]
                await self.store.add(lines)
                added, after = added + len(lines), entries[-1].position
            return added

    async def summary(self, where: UsageFilter) -> Summary:
        await self.catch_up()
        now = self._clock()
        until = where.until or now
        since = where.since or until - timedelta(days=30)
        span = until - since
        local = now.astimezone(self._zone)
        month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days = calendar.monthrange(local.year, local.month)[1]
        month = await self.store.totals(_within(where, month_start, None))
        elapsed = (now - month_start).total_seconds() / (days * 86400)
        conversations = await self.store.groups(_within(where, since, until), Dimension.CONVERSATION)
        return Summary(
            totals=await self.store.totals(_within(where, since, until)),
            previous=await self.store.totals(_within(where, since - span, since)),
            month=month,
            projected_month=Money(round(month.cost.nusd / elapsed)) if elapsed > 0 else month.cost,
            conversations=sum(1 for g in conversations if g.key is not None),
        )

    async def groups(self, where: UsageFilter, by: Dimension, *, limit: int | None = None) -> list[Group]:
        await self.catch_up()
        return await self.store.groups(where, by, limit=limit)

    async def series(self, where: UsageFilter, every: Interval, by: Dimension | None = None) -> list[Point]:
        await self.catch_up()
        return await self.store.series(where, every, by)

    async def lines(self, where: UsageFilter, *, before: int | None = None, limit: int = 50) -> list[Line]:
        await self.catch_up()
        return await self.store.lines(where, before=before, limit=limit)


def _within(where: UsageFilter, since: datetime | None, until: datetime | None) -> UsageFilter:
    return UsageFilter(since=since, until=until, only=where.only)


def _line(entry: Entry) -> Line | None:
    event = entry.event()
    if not isinstance(event, UsageRecorded):
        return None
    return Line(
        id=event.id,
        position=entry.position,
        at=event.at,
        consumer=event.consumer,
        kind=event.kind,
        provider=event.provider,
        served=event.served,
        units={Unit(u): q for u, q in event.units.items() if u in Unit},
        cost=Money(event.cost_nusd) if event.cost_nusd is not None else None,
        basis=event.basis,
        price=event.price,
        duration_ms=event.duration_ms,
        outcome=event.outcome,
        purpose=event.purpose,
        person=event.person,
        channel=event.channel,
        medium=event.medium,
        session=event.session,
        conversation=event.conversation,
        turn=event.turn,
        origin=event.origin,
    )
