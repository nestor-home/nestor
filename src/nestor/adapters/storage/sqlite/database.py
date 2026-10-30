"""One SQLite database shared by every store, driven from a single worker thread.

`sqlite3` is blocking: every call runs on one dedicated thread, which also serialises writes
(SQLite allows a single writer anyway). Calls are short; the event loop never waits on disk.
"""

import asyncio
import sqlite3
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nestor.adapters.storage.sqlite.schema import MIGRATIONS
from nestor.core import Component, ContractError

type Work[T] = Callable[[sqlite3.Connection], T]


class SQLiteDatabase(Component):
    name = "sqlite"

    def __init__(self, path: Path | str, migrations: Sequence[str] = MIGRATIONS) -> None:
        self.path = Path(path)
        self._migrations = tuple(migrations)
        self._connection: sqlite3.Connection | None = None
        self._worker: ThreadPoolExecutor | None = None

    @property
    def schema_version(self) -> int:
        return len(self._migrations)

    async def start(self) -> None:
        if self._connection is not None:
            return
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nestor-sqlite")
        try:
            self._connection = await asyncio.get_running_loop().run_in_executor(self._worker, self._open)
        except BaseException:
            self._worker.shutdown(wait=False)
            self._worker = None
            raise

    async def close(self) -> None:
        if self._connection is None or self._worker is None:
            return
        connection, worker = self._connection, self._worker
        self._connection = self._worker = None
        await asyncio.get_running_loop().run_in_executor(worker, connection.close)
        worker.shutdown(wait=True)

    async def read[T](self, work: Work[T]) -> T:
        return await self._submit(work)

    async def write[T](self, work: Work[T]) -> T:
        """Run `work` in one transaction: everything it writes is committed together, or nothing."""

        def transaction(connection: sqlite3.Connection) -> T:
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = work(connection)
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
            return result

        return await self._submit(transaction)

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")  # durable across crashes in WAL mode
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")  # Litestream briefly holds locks
            self._migrate(connection)
        except BaseException:
            connection.close()
            raise
        return connection

    def _migrate(self, connection: sqlite3.Connection) -> None:
        (current,) = connection.execute("PRAGMA user_version").fetchone()
        if current > self.schema_version:
            raise ContractError(
                f"{self.path} has schema version {current}, this code knows {self.schema_version}: upgrade Nestor"
            )
        for version, script in enumerate(self._migrations[current:], start=current + 1):
            connection.executescript(f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;")

    async def _submit[T](self, work: Work[T]) -> T:
        connection, worker = self._connection, self._worker
        if connection is None or worker is None:
            raise ContractError(f"database {self.path} is not open")
        return await asyncio.get_running_loop().run_in_executor(worker, work, connection)
