"""Episodes in SQLite, searched with an accent-insensitive FTS5 index ranked by BM25, each seen only by its
participants (a JSON array matched with `json_each`)."""

import json
import sqlite3
from collections.abc import Collection
from datetime import datetime

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.adapters.storage.sqlite.event_log import from_time_key, time_key
from nestor.adapters.storage.sqlite.text import match
from nestor.core import PersonId
from nestor.modules.channels import Address, Medium
from nestor.modules.memory.episodes import Episode, EpisodeStore

_COLUMNS = ("id", "address", "medium", "participants", "started_at", "ended_at", "summary", "topics")
_SELECT = ", ".join(f"e.{c}" for c in _COLUMNS)
_THEIRS = "EXISTS (SELECT 1 FROM json_each(e.participants) WHERE value = ?)"


class SQLiteEpisodeStore(EpisodeStore):
    name = "sqlite-episodes"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def put(self, episode: Episode) -> None:
        row = (
            episode.id,
            str(episode.address),
            episode.medium.value,
            json.dumps(list(episode.participants)),
            time_key(episode.started_at),
            time_key(episode.ended_at),
            episode.summary,
            json.dumps(list(episode.topics), ensure_ascii=False),
        )
        updates = ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS[1:])
        await self.database.write(
            lambda c: c.execute(
                f"INSERT INTO episodes ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}",
                row,
            )
        )

    async def get_many(self, ids: Collection[str]) -> list[Episode]:
        if not ids:
            return []
        marks = ", ".join("?" * len(ids))
        return await self._select(f"WHERE e.id IN ({marks})", list(ids))

    async def everything(self) -> list[Episode]:
        return await self._select("", [])

    async def search(
        self,
        query: str,
        *,
        person: PersonId,
        limit: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Episode]:
        if (words := match(query)) is None:
            return []
        where, params = _within(since, until)
        rows = await self.database.read(
            lambda c: c.execute(
                f"SELECT {_SELECT} FROM episodes_text JOIN episodes e ON e.rowid = episodes_text.rowid "
                f"WHERE episodes_text MATCH ? AND {_THEIRS}{where} ORDER BY bm25(episodes_text) LIMIT ?",
                [words, person, *params, limit],
            ).fetchall()
        )
        return [_episode(r) for r in rows]

    async def recent(
        self, *, person: PersonId, limit: int, since: datetime | None = None, until: datetime | None = None
    ) -> list[Episode]:
        where, params = _within(since, until)
        return await self._select(f"WHERE {_THEIRS}{where} ORDER BY e.ended_at DESC LIMIT ?", [person, *params, limit])

    async def _select(self, clause: str, params: list[object]) -> list[Episode]:
        def query(connection: sqlite3.Connection) -> list[tuple]:
            return connection.execute(f"SELECT {_SELECT} FROM episodes e {clause}", params).fetchall()

        return [_episode(r) for r in await self.database.read(query)]


def _within(since: datetime | None, until: datetime | None) -> tuple[str, list[object]]:
    """The SQL keeping the episodes that ended within the bounds, and its parameters."""
    where, params = "", []
    if since is not None:
        where, params = f"{where} AND e.ended_at >= ?", [*params, time_key(since)]
    if until is not None:
        where, params = f"{where} AND e.ended_at <= ?", [*params, time_key(until)]
    return where, params


def _episode(row: tuple) -> Episode:
    id_, address, medium, participants, started_at, ended_at, summary, topics = row
    return Episode(
        id=id_,
        address=Address.parse(address),
        medium=Medium(medium),
        participants=tuple(PersonId(p) for p in json.loads(participants)),
        started_at=from_time_key(started_at),
        ended_at=from_time_key(ended_at),
        summary=summary,
        topics=tuple(json.loads(topics)),
    )
