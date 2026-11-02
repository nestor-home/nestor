"""Memories in SQLite, searched with an accent-insensitive FTS5 index ranked by BM25."""

import sqlite3
from collections.abc import Collection

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.adapters.storage.sqlite.event_log import from_time_key, time_key
from nestor.adapters.storage.sqlite.text import match
from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.memory import Memory, MemoryStore

_COLUMNS = "id, text, about, source, told_by, created_at, updated_at"


class SQLiteMemoryStore(MemoryStore):
    name = "sqlite-memory"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def put(self, memory: Memory) -> None:
        row = (
            memory.id,
            memory.text,
            memory.about,
            str(memory.source) if memory.source else None,
            memory.told_by,
            time_key(memory.created_at),
            time_key(memory.updated_at),
        )
        await self.database.write(
            lambda c: c.execute(
                f"INSERT INTO memories ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET text = excluded.text, about = excluded.about, "
                "updated_at = excluded.updated_at",
                row,
            )
        )

    async def get(self, memory_id: str) -> Memory | None:
        row = await self.database.read(
            lambda c: c.execute(f"SELECT {_COLUMNS} FROM memories WHERE id = ?", (memory_id,)).fetchone()
        )
        return _memory(row) if row else None

    async def get_many(self, ids: Collection[str]) -> list[Memory]:
        if not ids:
            return []
        marks = ", ".join("?" * len(ids))
        rows = await self.database.read(
            lambda c: c.execute(f"SELECT {_COLUMNS} FROM memories WHERE id IN ({marks})", tuple(ids)).fetchall()
        )
        return [_memory(r) for r in rows]

    async def delete(self, memory_id: str) -> None:
        await self.database.write(lambda c: c.execute("DELETE FROM memories WHERE id = ?", (memory_id,)))

    async def search(self, query: str, *, about: PersonId | None = None, limit: int = 10) -> list[Memory]:
        if (words := match(query)) is None:
            return []
        sql = (
            f"SELECT {', '.join('m.' + c for c in _COLUMNS.split(', '))} FROM memories_text "
            "JOIN memories m ON m.rowid = memories_text.rowid WHERE memories_text MATCH ?"
        )
        params: list[object] = [words]
        if about is not None:
            sql += " AND (m.about = ? OR m.about IS NULL)"
            params.append(about)
        sql += " ORDER BY bm25(memories_text) LIMIT ?"
        params.append(limit)
        rows = await self.database.read(lambda c: c.execute(sql, params).fetchall())
        return [_memory(r) for r in rows]

    async def recent(self, *, about: PersonId | None = None, limit: int = 20) -> list[Memory]:
        where, params = ("WHERE about = ? OR about IS NULL", [about]) if about is not None else ("", [])

        def query(connection: sqlite3.Connection) -> list[tuple]:
            sql = f"SELECT {_COLUMNS} FROM memories {where} ORDER BY updated_at DESC, rowid DESC LIMIT ?"
            return connection.execute(sql, [*params, limit]).fetchall()

        return [_memory(r) for r in await self.database.read(query)]

    async def everything(self) -> list[Memory]:
        rows = await self.database.read(lambda c: c.execute(f"SELECT {_COLUMNS} FROM memories").fetchall())
        return [_memory(r) for r in rows]


def _memory(row: tuple) -> Memory:
    id_, text, about, source, told_by, created_at, updated_at = row
    return Memory(
        id=id_,
        text=text,
        about=PersonId(about) if about else None,
        source=Address.parse(source) if source else None,
        told_by=PersonId(told_by) if told_by else None,
        created_at=from_time_key(created_at),
        updated_at=from_time_key(updated_at),
    )
