"""The SQLite database: WAL, versioned migrations, transactions, and a connection its stores share."""

import sqlite3
from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteEventLog
from nestor.core import ContractError
from nestor.modules.journal import LogQuery
from nestor.testing.journal import Probe


async def test_stores_sharing_a_database_do_not_close_it(db_path: Path) -> None:
    async with SQLiteDatabase(db_path) as db:
        async with SQLiteEventLog(db) as log:
            await log.append(Probe(source="test", label="partagé"))
        assert len(await SQLiteEventLog(db).read(LogQuery())) == 1


async def test_the_database_runs_in_wal_mode_at_the_latest_schema(db_path: Path) -> None:
    async with SQLiteDatabase(db_path) as db:
        mode = await db.read(lambda c: c.execute("PRAGMA journal_mode").fetchone()[0])
        version = await db.read(lambda c: c.execute("PRAGMA user_version").fetchone()[0])
    assert (mode, version) == ("wal", db.schema_version)


async def test_migrations_apply_once_and_in_order(db_path: Path) -> None:
    first = ("CREATE TABLE t (n INTEGER);",)
    async with SQLiteDatabase(db_path, first) as db:
        await db.write(lambda c: c.execute("INSERT INTO t VALUES (1)"))
    async with SQLiteDatabase(db_path, (*first, "ALTER TABLE t ADD COLUMN label TEXT;")) as db:
        rows = await db.read(lambda c: c.execute("SELECT n, label FROM t").fetchall())
    assert rows == [(1, None)]


async def test_a_database_written_by_a_newer_nestor_is_refused(db_path: Path) -> None:
    async with SQLiteDatabase(db_path, ("CREATE TABLE a (n);", "CREATE TABLE b (n);")):
        pass
    with pytest.raises(ContractError, match="upgrade Nestor"):
        await SQLiteDatabase(db_path, ("CREATE TABLE a (n);",)).start()


async def test_a_failed_transaction_writes_nothing(db_path: Path) -> None:
    async with SQLiteDatabase(db_path, ("CREATE TABLE t (n INTEGER);",)) as db:

        def half_done(connection: sqlite3.Connection) -> None:
            connection.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("crash midway")

        with pytest.raises(RuntimeError):
            await db.write(half_done)
        assert await db.read(lambda c: c.execute("SELECT count(*) FROM t").fetchone()[0]) == 0


async def test_a_closed_database_refuses_work(db_path: Path) -> None:
    db = SQLiteDatabase(db_path)
    await db.start()
    await db.start()
    await db.close()
    await db.close()
    with pytest.raises(ContractError, match="not open"):
        await db.read(lambda c: None)
