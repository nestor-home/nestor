"""When accounts were last seen, in SQLite: one row per account, only ever moved forward."""

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.adapters.storage.sqlite.event_log import time_key
from nestor.modules.accounts import ActivityStore


class SQLiteActivityStore(ActivityStore):
    name = "sqlite-activity"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def record(self, account_id: str, at: datetime) -> None:
        row = (account_id, time_key(at))
        await self.database.write(
            lambda c: c.execute(
                "INSERT INTO account_activity (account_id, seen_at) VALUES (?, ?) ON CONFLICT (account_id) "
                "DO UPDATE SET seen_at = MAX(seen_at, excluded.seen_at)",
                row,
            )
        )

    async def seen(self) -> Mapping[str, datetime]:
        def query(connection: sqlite3.Connection) -> list[tuple[str, str]]:
            return connection.execute("SELECT account_id, seen_at FROM account_activity").fetchall()

        rows = await self.database.read(query)
        return {account: datetime.strptime(at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC) for account, at in rows}
