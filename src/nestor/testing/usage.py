"""Helpers and contract suites for usage: what a call reported, and the behaviour every `UsageStore` and
`PriceCatalogue` adapter must show."""

from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nestor.core import ModelType, Money, PersonId, Tally, Unit, Usage, counting
from nestor.modules.channels import Medium
from nestor.modules.usage import (
    Beat,
    CallPurpose,
    CostBasis,
    Dimension,
    Interval,
    Line,
    Outcome,
    UsageFilter,
    UsageRecorded,
    UsageStore,
)


async def consumed[T](call: Awaitable[T]) -> tuple[T, Tally]:
    """What `call` returns, and what it reported it consumed (`nestor.core.report`) while it ran."""
    tally = Tally()
    with counting(tally):
        result = await call
    return result, tally


def said(tally: Tally) -> Usage:
    """What a call reported, after checking it reported at all: the contract of every model."""
    assert tally.usage != Usage(), "a call says what it consumed (nestor.core.report): its units, or at least its model"
    return tally.usage


def line(position: int, at: datetime, *, cost: int | None = 1_000_000, **given: Any) -> Line:
    """A call as the ledger keeps it: 1 000 tokens in, 100 out, $0.001, for `mathis` unless `given` says else."""
    fields: dict[str, Any] = {
        "source": "usage",
        "id": f"call-{position}",
        "at": at,
        "consumer": "haiku",
        "kind": ModelType.LANGUAGE,
        "provider": "openrouter",
        "served": "anthropic/claude-haiku-4.5",
        "units": {Unit.INPUT_TOKENS: 1000, Unit.OUTPUT_TOKENS: 100},
        "cost_nusd": cost,
        "basis": CostBasis.REPORTED if cost is not None else CostBasis.UNKNOWN,
        "price": None,
        "duration_ms": 800,
        "outcome": Outcome.OK,
        "purpose": CallPurpose.TURN,
        "person": PersonId("mathis"),
        "channel": "telegram",
        "medium": Medium.WRITTEN,
        "conversation": "c1",
        "turn": f"t{position}",
    }
    return Line(position, UsageRecorded(**(fields | given)))


PARIS = "Europe/Paris"
NOV = datetime(2026, 11, 2, 9, tzinfo=UTC)  # a Monday


class UsageStoreContract:
    """Behaviour every `UsageStore` adapter must show. Mix into a `Test…` class and implement `store()`, a fresh
    store over the same storage at each call (so that reopening it is tested)."""

    def store(self) -> UsageStore:
        raise NotImplementedError

    @asynccontextmanager
    async def opened(self, zone: str = PARIS) -> AsyncGenerator[UsageStore]:
        async with self.store() as store:
            await store.open(zone)
            yield store

    async def test_a_call_is_kept_once_and_the_position_follows_the_journal(self) -> None:
        async with self.opened() as store:
            await store.add([line(3, NOV), line(7, NOV)])
            await store.add([line(7, NOV), line(5, NOV)])  # caught up again from an older position
            assert (await store.totals(UsageFilter())).calls == 3
            assert await store.position() == 7

    async def test_totals_leave_unknown_costs_out_and_say_how_many(self) -> None:
        async with self.opened() as store:
            await store.add([line(1, NOV), line(2, NOV, cost=2_500_000), line(3, NOV, cost=None)])
            totals = await store.totals(UsageFilter())
            assert (totals.cost, totals.calls, totals.unknown) == (Money(3_500_000), 3, 1)
            assert totals.units == {Unit.INPUT_TOKENS: 3000, Unit.OUTPUT_TOKENS: 300}
            assert (totals.duration_ms, totals.conversations) == (2400, 1)

    async def test_a_filter_keeps_a_period_and_the_values_asked_for_none_included(self) -> None:
        async with self.opened() as store:
            await store.add([
                line(1, NOV),
                line(2, NOV + timedelta(hours=1), person=None, purpose=CallPurpose.WATCH),  # Nestor's own work
                line(3, NOV + timedelta(hours=2), person=PersonId("lea")),
                line(4, NOV + timedelta(days=1)),
            ])  # fmt: skip
            today = UsageFilter(since=NOV, until=NOV + timedelta(days=1))
            assert (await store.totals(today)).calls == 3, "until is excluded"
            mine = UsageFilter(only={Dimension.PERSON: frozenset({"mathis", None})})
            assert [c.position for c in await store.lines(mine)] == [4, 2, 1]
            assert (await store.totals(UsageFilter(only={Dimension.PERSON: frozenset()}))).calls == 0

    async def test_groups_come_the_costliest_first(self) -> None:
        async with self.opened() as store:
            await store.add([
                line(1, NOV, consumer="haiku"),
                line(2, NOV, consumer="opus", cost=9_000_000),
                line(3, NOV, consumer="haiku", cost=None),
            ])  # fmt: skip
            groups = await store.groups(UsageFilter(), Dimension.CONSUMER)
            assert [(g.key, g.totals.cost, g.totals.calls) for g in groups] == [
                ("opus", Money(9_000_000), 1),
                ("haiku", Money(1_000_000), 2),
            ]

    async def test_time_is_cut_in_the_household_s_days_weeks_and_months(self) -> None:
        async with self.opened() as store:
            late = datetime(2026, 11, 1, 23, 30, tzinfo=UTC)  # Monday 2 November, 00:30 in Paris
            wednesday = NOV + timedelta(days=2)
            await store.add([line(1, late), line(2, NOV, consumer="opus"), line(3, NOV + timedelta(days=7))])
            await store.add([line(4, wednesday, consumer="opus")])
            zone = ZoneInfo(PARIS)
            days = await store.series(UsageFilter(), Interval.DAY)
            assert [p.start.day for p in days] == [2, 4, 9]
            assert [g.totals.calls for g in days[0].groups] == [2]
            weeks = await store.series(UsageFilter(), Interval.WEEK, Dimension.CONSUMER)
            assert [(p.start.day, [g.key for g in p.groups]) for p in weeks] == [(2, ["opus", "haiku"]), (9, ["haiku"])]
            months = await store.series(UsageFilter(), Interval.MONTH)
            assert [(p.start, p.groups[0].totals.calls) for p in months] == [(datetime(2026, 11, 1, tzinfo=zone), 4)]
            hours = await store.series(UsageFilter(), Interval.HOUR)
            assert hours[0].start == datetime(2026, 11, 2, 0, tzinfo=zone)

    async def test_within_a_bucket_of_time_the_costliest_comes_first(self) -> None:
        async with self.opened() as store:
            await store.add([line(1, NOV, consumer="alpha", cost=9_000_000), line(2, NOV, consumer="zulu")])
            (day,) = await store.series(UsageFilter(), Interval.DAY, Dimension.CONSUMER)
        assert [g.key for g in day.groups] == ["alpha", "zulu"], "by what they cost, not by their names"

    async def test_calls_come_newest_first_page_by_page(self) -> None:
        async with self.opened() as store:
            await store.add([line(p, NOV + timedelta(minutes=p)) for p in range(1, 6)])
            first = await store.lines(UsageFilter(), limit=2)
            assert [c.position for c in first] == [5, 4]
            assert [c.position for c in await store.lines(UsageFilter(), before=4, limit=2)] == [3, 2]
            assert first[0] == line(5, NOV + timedelta(minutes=5)), "a call comes back as it was kept"

    async def test_another_time_zone_empties_it_for_a_rebuild(self) -> None:
        async with self.opened() as store:
            await store.add([line(1, NOV)])
        async with self.opened(PARIS) as again:
            assert (await again.totals(UsageFilter())).calls == 1, "the same zone keeps it"
        async with self.opened("America/New_York") as moved:
            assert (await moved.position(), (await moved.totals(UsageFilter())).calls) == (0, 0)

    async def test_the_rhythm_is_what_each_hour_of_each_weekday_cost(self) -> None:
        async with self.opened() as store:
            late = datetime(2026, 11, 1, 23, 30, tzinfo=UTC)  # Monday 00:30 in Paris
            await store.add([line(1, late), line(2, late + timedelta(days=7), cost=2_000_000), line(3, NOV)])
            beats = sorted(await store.rhythm(UsageFilter()), key=lambda b: (b.weekday, b.hour))
        assert beats == [Beat(0, 0, Money(3_000_000), 2), Beat(0, 10, Money(1_000_000), 1)]
