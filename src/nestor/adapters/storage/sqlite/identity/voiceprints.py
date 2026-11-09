"""Voiceprints in SQLite, apart from the journal: forgetting a voice deletes its rows for good. One row per
voiceprint (float64 blob), the anchor's and the learned ones; a person's `voices` row says in which space."""

import sqlite3
import struct
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

from nestor.adapters.storage.sqlite.common import from_time_key, time_key
from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.core import ContractError, PersonId
from nestor.modules.identity import Learned, Profile, Vector, VoiceprintStore, VoiceSpace


def _blob(vector: Vector) -> bytes:
    return struct.pack(f"<{len(vector)}d", *vector)


def _vector(blob: bytes) -> Vector:
    return struct.unpack(f"<{len(blob) // 8}d", blob)


class SQLiteVoiceprintStore(VoiceprintStore):
    name = "sqlite-voiceprints"

    def __init__(self, database: SQLiteDatabase, *, owns_database: bool = False) -> None:
        self.database = database
        self._owns_database = owns_database

    async def start(self) -> None:
        if self._owns_database:
            await self.database.start()

    async def close(self) -> None:
        if self._owns_database:
            await self.database.close()

    async def profiles(self, space: VoiceSpace) -> Mapping[PersonId, Profile]:
        def read(c: sqlite3.Connection) -> dict[PersonId, Profile]:
            people = c.execute("SELECT person, learning, enrolled_at FROM voices WHERE space = ?", (space.id,))
            found: dict[PersonId, Profile] = {}
            for person, learning, enrolled_at in people.fetchall():
                rows = c.execute(
                    "SELECT anchor, vector, turn, room, at FROM voiceprints WHERE person = ? ORDER BY at, rowid",
                    (person,),
                ).fetchall()
                found[PersonId(person)] = Profile(
                    anchor=tuple(_vector(v) for anchor, v, *_ in rows if anchor),
                    learned=tuple(
                        Learned(voiceprint=_vector(v), turn=turn, room=room, at=from_time_key(at))
                        for anchor, v, turn, room, at in rows
                        if not anchor
                    ),
                    learning=bool(learning),
                    enrolled_at=from_time_key(enrolled_at),
                )
            return found

        return await self.database.read(read)

    async def enroll(
        self, person: PersonId, space: VoiceSpace, anchor: Sequence[Vector], *, learning: bool, at: datetime
    ) -> None:
        def write(c: sqlite3.Connection) -> None:
            c.execute("DELETE FROM voices WHERE person = ?", (person,))
            c.execute(
                "INSERT INTO voices (person, space, learning, enrolled_at) VALUES (?, ?, ?, ?)",
                (person, space.id, int(learning), time_key(at)),
            )
            c.executemany(
                "INSERT INTO voiceprints (person, anchor, vector, at) VALUES (?, 1, ?, ?)",
                [(person, _blob(v), time_key(at)) for v in anchor],
            )

        await self.database.write(write)

    async def learn(self, person: PersonId, sample: Learned, *, keep: int, per_room: int) -> None:
        def write(c: sqlite3.Connection) -> None:
            if c.execute("SELECT 1 FROM voices WHERE person = ?", (person,)).fetchone() is None:
                raise ContractError(f"{person!r} has not recorded their voice")
            c.execute(
                "INSERT INTO voiceprints (person, anchor, vector, turn, room, at) VALUES (?, 0, ?, ?, ?, ?)",
                (person, _blob(sample.voiceprint), sample.turn, sample.room, time_key(sample.at)),
            )
            newest = "ORDER BY at DESC, rowid DESC LIMIT -1 OFFSET ?"
            c.execute(
                f"DELETE FROM voiceprints WHERE rowid IN (SELECT rowid FROM voiceprints "
                f"WHERE person = ? AND anchor = 0 AND room = ? {newest})",
                (person, sample.room, per_room),
            )
            c.execute(
                f"DELETE FROM voiceprints WHERE rowid IN (SELECT rowid FROM voiceprints "
                f"WHERE person = ? AND anchor = 0 {newest})",
                (person, keep),
            )

        await self.database.write(write)

    async def unlearn(self, turns: Collection[str]) -> frozenset[PersonId]:
        if not turns:
            return frozenset()
        marks = ", ".join("?" * len(turns))

        def write(c: sqlite3.Connection) -> frozenset[PersonId]:
            people = c.execute(
                f"SELECT DISTINCT person FROM voiceprints WHERE anchor = 0 AND turn IN ({marks})", list(turns)
            ).fetchall()
            c.execute(f"DELETE FROM voiceprints WHERE anchor = 0 AND turn IN ({marks})", list(turns))
            return frozenset(PersonId(p) for (p,) in people)

        return await self.database.write(write)

    async def set_learning(self, person: PersonId, learning: bool) -> None:
        await self.database.write(
            lambda c: c.execute("UPDATE voices SET learning = ? WHERE person = ?", (int(learning), person))
        )

    async def forget(self, person: PersonId, *, learned_only: bool = False) -> None:
        if learned_only:
            await self.database.write(
                lambda c: c.execute("DELETE FROM voiceprints WHERE person = ? AND anchor = 0", (person,))
            )
        else:
            await self.database.write(lambda c: c.execute("DELETE FROM voices WHERE person = ?", (person,)))

    async def keep_only(self, space: VoiceSpace) -> None:
        await self.database.write(lambda c: c.execute("DELETE FROM voices WHERE space != ?", (space.id,)))

    async def keep_people(self, people: Collection[PersonId]) -> frozenset[PersonId]:
        kept = list(people)
        marks = ", ".join("?" * len(kept))
        others = f"person NOT IN ({marks})" if kept else "1 = 1"

        def write(c: sqlite3.Connection) -> frozenset[PersonId]:
            gone = c.execute(f"SELECT person FROM voices WHERE {others}", kept).fetchall()
            c.execute(f"DELETE FROM voices WHERE {others}", kept)
            return frozenset(PersonId(p) for (p,) in gone)

        return await self.database.write(write)
