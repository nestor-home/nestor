"""The event log in SQLite: one row per event, append-only (enforced by triggers)."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.core import ContractError, Event, Record
from nestor.modules.journal import Entry, EventLog, LogQuery

_COLUMNS = "position, id, type, version, at, source, session, payload"


def time_key(at: datetime) -> str:
    """Fixed-width UTC text, so that SQL comparisons on it follow time."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class SQLiteEventLog(EventLog):
    name = "sqlite-event-log"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database

    @classmethod
    def at(cls, path: Path | str) -> "SQLiteEventLog":
        """A log with its own database file (the runtime shares one database between stores instead)."""
        return cls(SQLiteDatabase(path), owns_database=True)

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def append(self, event: Event) -> int:
        record = event.to_record()
        row = (
            event.id,
            event.event_type,
            event.version,
            time_key(event.at),
            event.source,
            event.session,
            json.dumps(record["payload"], ensure_ascii=False),
        )

        def insert(connection: sqlite3.Connection) -> int:
            try:
                cursor = connection.execute(
                    "INSERT INTO events (id, type, version, at, source, session, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
            except sqlite3.IntegrityError:
                raise ContractError(f"event {event.id} is already logged") from None
            return int(cursor.lastrowid or 0)

        return await self.database.write(insert)

    async def read(self, query: LogQuery) -> list[Entry]:
        where: list[str] = ["position > ?"]
        params: list[object] = [query.after]
        if query.types is not None:
            where.append(f"type IN ({', '.join('?' * len(query.types))})")
            params.extend(sorted(query.types))
        if query.session is not None:
            where.append("session = ?")
            params.append(query.session)
        if query.since is not None:
            where.append("at >= ?")
            params.append(time_key(query.since))
        if query.until is not None:
            where.append("at < ?")
            params.append(time_key(query.until))
        sql = f"SELECT {_COLUMNS} FROM events WHERE {' AND '.join(where)} ORDER BY position"
        if query.newest_first:
            sql += " DESC"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)
        rows = await self.database.read(lambda c: c.execute(sql, params).fetchall())
        return [Entry(row[0], _record(row)) for row in rows]


def _record(row: tuple) -> Record:
    _, id_, type_, version, at, source, session, payload = row
    return {
        "type": type_,
        "version": version,
        "id": id_,
        "at": datetime.strptime(at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC).isoformat(),
        "source": source,
        "session": session,
        "payload": json.loads(payload),
    }
