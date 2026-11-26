"""Memories in SQLite, searched with an accent-insensitive FTS5 index ranked by BM25, over their text and the name of
their project or topic."""

from collections.abc import Collection

from nestor.adapters.storage.sqlite.common import from_time_key, match, time_key
from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.memory import Memory, MemoryStore, Place, Shelf

_COLUMNS = ("id", "text", "place", "source", "told_by", "tied_to", "created_at", "updated_at")
_SELECT = ", ".join(f"m.{c}" for c in _COLUMNS)
_PEOPLE = f"{Shelf.PEOPLE.value}/"


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
            str(memory.place),
            memory.place.label,
            str(memory.source) if memory.source else None,
            memory.told_by,
            memory.tied_to,
            time_key(memory.created_at),
            time_key(memory.updated_at),
        )
        await self.database.write(
            lambda c: c.execute(
                "INSERT INTO memories (id, text, place, label, source, told_by, tied_to, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET text = excluded.text, "
                "place = excluded.place, label = excluded.label, updated_at = excluded.updated_at",
                row,
            )
        )

    async def get(self, memory_id: str) -> Memory | None:
        found = await self._select("WHERE m.id = ?", [memory_id])
        return found[0] if found else None

    async def get_many(self, ids: Collection[str]) -> list[Memory]:
        if not ids:
            return []
        return await self._select(f"WHERE m.id IN ({', '.join('?' * len(ids))})", list(ids))

    async def delete(self, memory_id: str) -> None:
        await self.database.write(lambda c: c.execute("DELETE FROM memories WHERE id = ?", (memory_id,)))

    async def search(
        self, query: str, *, about: PersonId | None = None, place: Place | None = None, limit: int = 10
    ) -> list[Memory]:
        if (words := match(query)) is None:
            return []
        where, params = _within(about, place)
        sql = (
            f"SELECT {_SELECT} FROM memories_text JOIN memories m ON m.rowid = memories_text.rowid "
            f"WHERE memories_text MATCH ? {' AND ' + where if where else ''} ORDER BY bm25(memories_text) LIMIT ?"
        )
        rows = await self.database.read(lambda c: c.execute(sql, [words, *params, limit]).fetchall())
        return [_memory(r) for r in rows]

    async def recent(
        self, *, about: PersonId | None = None, place: Place | None = None, limit: int = 20
    ) -> list[Memory]:
        where, params = _within(about, place)
        return await self._select(
            f"{'WHERE ' + where if where else ''} ORDER BY m.updated_at DESC, m.rowid DESC LIMIT ?", [*params, limit]
        )

    async def everything(self) -> list[Memory]:
        return await self._select("", [])

    async def tied(self, tie: str) -> list[Memory]:
        return await self._select("WHERE m.tied_to = ?", [tie])

    async def _select(self, tail: str, params: list[object]) -> list[Memory]:
        sql = f"SELECT {_SELECT} FROM memories m {tail}"
        return [_memory(r) for r in await self.database.read(lambda c: c.execute(sql, params).fetchall())]


def _within(about: PersonId | None, place: Place | None) -> tuple[str, list[object]]:
    """The conditions keeping one person's memories and the shared ones, and those of a place or a shelf."""
    where: list[str] = []
    params: list[object] = []
    if about is not None:
        where.append("(m.place = ? OR m.place NOT LIKE ?)")
        params += [f"{_PEOPLE}{about}", f"{_PEOPLE}%"]
    if place is not None and place.name is None:
        where.append("(m.place = ? OR m.place LIKE ?)")
        params += [place.shelf.value, f"{place.shelf.value}/%"]
    elif place is not None:
        where.append("m.place = ?")
        params.append(str(place))
    return " AND ".join(where), params


def _memory(row: tuple) -> Memory:
    id_, text, place, source, told_by, tied_to, created_at, updated_at = row
    return Memory(
        id=id_,
        text=text,
        place=Place.parse(place),
        source=Address.parse(source) if source else None,
        told_by=PersonId(told_by) if told_by else None,
        tied_to=tied_to,
        created_at=from_time_key(created_at),
        updated_at=from_time_key(updated_at),
    )
