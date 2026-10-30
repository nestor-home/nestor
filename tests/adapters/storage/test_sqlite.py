"""SQLite storage: the event log contract, plus what only a database file can break."""

import sqlite3
from pathlib import Path

import pytest

from nestor.adapters.storage.files import FileBlobStore
from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteEventLog
from nestor.core import ContractError
from nestor.modules.journal import LogQuery
from nestor.testing.journal import BlobStoreContract, EventLogContract, Probe


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "nestor.db"


class TestSQLiteEventLog(EventLogContract):
    @pytest.fixture(autouse=True)
    def _path(self, db_path: Path) -> None:
        self.path = db_path

    def event_log(self) -> SQLiteEventLog:
        return SQLiteEventLog.at(self.path)


class TestFileBlobStore(BlobStoreContract):
    @pytest.fixture(autouse=True)
    def _root(self, tmp_path: Path) -> None:
        self.root = tmp_path / "blobs"

    def blob_store(self) -> FileBlobStore:
        return FileBlobStore(self.root)


async def test_events_survive_a_restart(db_path: Path) -> None:
    event = Probe(source="test", label="persisté", count=7)
    async with SQLiteEventLog.at(db_path) as log:
        await log.append(event)
    async with SQLiteEventLog.at(db_path) as log:
        entries = await log.read(LogQuery())
    assert [e.event() for e in entries] == [event]


async def test_stores_sharing_a_database_do_not_close_it(db_path: Path) -> None:
    async with SQLiteDatabase(db_path) as db:
        async with SQLiteEventLog(db) as log:
            await log.append(Probe(source="test", label="partagé"))
        assert len(await SQLiteEventLog(db).read(LogQuery())) == 1


async def test_the_log_cannot_be_rewritten_even_with_raw_sql(db_path: Path) -> None:
    async with SQLiteEventLog.at(db_path) as log:
        await log.append(Probe(source="test", label="gravé"))
        for statement in ("UPDATE events SET source = 'x'", "DELETE FROM events"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                await log.database.write(lambda c, s=statement: c.execute(s))
        assert len(await log.read(LogQuery())) == 1


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


async def test_an_invalid_blob_digest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ContractError):
        await FileBlobStore(tmp_path).get("../../etc/passwd")
