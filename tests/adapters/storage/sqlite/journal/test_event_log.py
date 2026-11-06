"""The event log in SQLite: the contract, plus what only a database file can break."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteEventLog
from nestor.modules.journal import Journal, LogQuery
from nestor.testing.journal import EventLogContract, Probe, labels


class TestSQLiteEventLog(EventLogContract):
    @pytest.fixture(autouse=True)
    def _path(self, db_path: Path) -> None:
        self.path = db_path

    def event_log(self) -> SQLiteEventLog:
        return SQLiteEventLog.at(self.path)


async def test_events_survive_a_restart(db_path: Path) -> None:
    event = Probe(source="test", label="persisté", count=7)
    async with SQLiteEventLog.at(db_path) as log:
        await log.append(event)
    async with SQLiteEventLog.at(db_path) as log:
        entries = await log.read(LogQuery())
    assert [e.event() for e in entries] == [event]


async def test_the_log_cannot_be_rewritten_even_with_raw_sql(db_path: Path) -> None:
    async with SQLiteEventLog.at(db_path) as log:
        await log.append(Probe(source="test", label="gravé"))
        for statement in ("UPDATE events SET source = 'x'", "DELETE FROM events"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                await log.database.write(lambda c, s=statement: c.execute(s))
        assert len(await log.read(LogQuery())) == 1


async def test_events_published_at_once_reach_subscribers_in_the_order_of_the_log(db_path: Path) -> None:
    async with SQLiteEventLog.at(db_path) as log:
        journal = Journal(log)
        subscription = journal.subscribe(Probe)
        await asyncio.gather(*(journal.publish(Probe(source="test", label=f"p{i}")) for i in range(30)))
        delivered = [event.label for _ in range(30) if isinstance(event := await subscription.next(timeout_s=1), Probe)]
        logged = labels(await log.read(LogQuery()))
    assert sorted(logged) == sorted(f"p{i}" for i in range(30))
    assert delivered == logged, "a subscriber rebuilding state live agrees with one replaying the log"
