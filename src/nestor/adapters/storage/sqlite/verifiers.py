"""Account verifiers in SQLite: password hashes and token digests, one row per owner.

They are one-way already (scrypt, SHA-256), so they are stored as is: no instance key is needed to
sign in, even on an instance without connectors.
"""

import sqlite3

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.adapters.storage.sqlite.event_log import time_key
from nestor.core import utc_now
from nestor.modules.accounts import VerifierStore


class SQLiteVerifierStore(VerifierStore):
    name = "sqlite-verifiers"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def put(self, owner: str, verifier: str) -> None:
        row = (owner, verifier, time_key(utc_now()))
        await self.database.write(
            lambda c: c.execute(
                "INSERT INTO verifiers (owner, verifier, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT (owner) DO UPDATE SET verifier = excluded.verifier, updated_at = excluded.updated_at",
                row,
            )
        )

    async def get(self, owner: str) -> str | None:
        def query(connection: sqlite3.Connection) -> tuple[str] | None:
            return connection.execute("SELECT verifier FROM verifiers WHERE owner = ?", (owner,)).fetchone()

        row = await self.database.read(query)
        return row[0] if row else None

    async def forget(self, owner: str) -> None:
        await self.database.write(lambda c: c.execute("DELETE FROM verifiers WHERE owner = ?", (owner,)))
