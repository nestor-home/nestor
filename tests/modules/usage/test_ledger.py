"""The ledger reads exactly what the journal holds: caught up before every reading, rebuilt from it alone."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteEventLog, SQLiteUsageStore
from nestor.core import ModelType, Money
from nestor.modules.journal import Journal
from nestor.modules.usage import (
    CallPurpose,
    CostBasis,
    Dimension,
    Interval,
    Ledger,
    Outcome,
    Period,
    UsageFilter,
    UsageRecorded,
)

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)  # the eleventh day of a 30-day month, at noon in UTC (13:00 in Paris)


def call(at: datetime, cost: int | None, person: str | None = "mathis") -> UsageRecorded:
    return UsageRecorded(
        source="usage",
        at=at,
        consumer="haiku",
        kind=ModelType.LANGUAGE,
        provider="openrouter",
        served=None,
        units={"input_tokens": 1000},
        cost_nusd=cost,
        basis=CostBasis.REPORTED if cost is not None else CostBasis.UNKNOWN,
        price=None,
        duration_ms=500,
        outcome=Outcome.OK,
        purpose=CallPurpose.TURN,
        person=person,  # ty: ignore[invalid-argument-type]
    )


async def test_what_is_published_is_read_at_once_and_a_lost_ledger_is_rebuilt_from_the_journal(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "nestor.db")
    journal = Journal(SQLiteEventLog(database))
    async with database:
        async with Ledger(journal, SQLiteUsageStore(database), "Europe/Paris") as ledger:
            await journal.publish(call(NOW, 4_000_000))
            await journal.publish(call(NOW, None, person=None))
            assert [(g.key, g.totals.calls) for g in await ledger.groups(UsageFilter(), Dimension.PERSON)] == [
                ("mathis", 1),
                (None, 1),
            ]
        async with Ledger(journal, SQLiteUsageStore(database), "Asia/Tokyo") as moved:  # its days are rebuilt
            assert len(await moved.lines(UsageFilter())) == 2


async def test_a_period_is_the_household_s_and_comes_with_the_one_before_and_where_the_month_is_heading(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "nestor.db")
    journal = Journal(SQLiteEventLog(database))
    async with database, Ledger(journal, SQLiteUsageStore(database), "Europe/Paris", clock=lambda: NOW) as ledger:
        await journal.publish(call(NOW - timedelta(days=1), 3_000_000))  # this week
        await journal.publish(call(NOW - timedelta(days=9), 2_000_000))  # the week before, this month
        await journal.publish(call(NOW - timedelta(days=20), 7_000_000))  # last month
        week = ledger.span(Period.WEEK)
        summary = await ledger.summary(week, {})
    paris = ZoneInfo("Europe/Paris")
    assert (week.since, week.until, week.every) == (datetime(2026, 11, 5, tzinfo=paris), NOW, Interval.DAY)
    assert (summary.totals.cost, summary.previous.cost, summary.month.cost) == (
        Money(3_000_000),
        Money(2_000_000),
        Money(5_000_000),
    )
    month_so_far = (NOW - datetime(2026, 11, 1, tzinfo=paris)) / timedelta(days=30)  # 10 days and 13 hours of 30
    assert summary.projected_month == Money(round(5_000_000 / month_so_far))
