"""Vectors in the instance's SQLite database, with sqlite-vec: one `vec0` table per embedding space, created on
demand (its dimension is fixed by the table). They are a projection, outside the versioned schema: dropping
one loses nothing, the index fills it again. Search is exhaustive: a household's few thousand vectors take
milliseconds (measured: 4 ms for 5,000 of 768 dimensions), no approximate index is needed.
"""

import re
import sqlite3
import struct
from collections.abc import Collection, Mapping, Sequence

from nestor.adapters.storage.sqlite.database import SQLiteDatabase
from nestor.core import ContractError
from nestor.modules.cognition.embedding import EmbeddingSpace, Indexed, Vector, VectorIndex

_PREFIX = "vectors_"
_TABLE = re.compile(rf"^{_PREFIX}[0-9a-f]{{16}}$")


def _table(space: EmbeddingSpace) -> str:
    return f"{_PREFIX}{space.id}"


def _blob(vector: Vector) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class SQLiteVectorIndex(VectorIndex):
    name = "sqlite-vectors"

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self._ready: set[str] = set()

    async def start(self) -> None:
        import sqlite_vec  # it loads numpy: only when vectors are used

        def load(connection: sqlite3.Connection) -> None:
            try:
                connection.enable_load_extension(True)
                sqlite_vec.load(connection)
                connection.enable_load_extension(False)
            except (AttributeError, sqlite3.OperationalError) as error:
                raise ContractError(
                    f"this Python's SQLite cannot load extensions, which vector search needs: {error}"
                ) from None

        await self.database.read(load)

    async def put(self, space: EmbeddingSpace, kind: str, items: Sequence[Indexed]) -> None:
        if wrong := next((i for i in items if len(i.vector) != space.dimensions), None):
            raise ContractError(f"a vector of {len(wrong.vector)} dimensions in a space of {space.dimensions}")
        if not items:
            return
        table = await self._create(space)

        def write(connection: sqlite3.Connection) -> None:  # vec0 has no upsert: replaced by delete and insert
            connection.executemany(f"DELETE FROM {table} WHERE id = ?", [(f"{kind}:{i.item}",) for i in items])
            connection.executemany(
                f"INSERT INTO {table} (id, embedding, kind, item, fingerprint) VALUES (?, ?, ?, ?, ?)",
                [(f"{kind}:{i.item}", _blob(i.vector), kind, i.item, i.fingerprint) for i in items],
            )

        await self.database.write(write)

    async def delete(self, kind: str, items: Collection[str]) -> None:
        if not items:
            return

        def remove(connection: sqlite3.Connection) -> None:
            keys = [(f"{kind}:{item}",) for item in items]
            for table in _tables(connection):
                connection.executemany(f"DELETE FROM {table} WHERE id = ?", keys)

        await self.database.write(remove)

    async def nearest(self, space: EmbeddingSpace, kind: str, vector: Vector, limit: int) -> list[tuple[str, float]]:
        table = await self._create(space)
        rows = await self.database.read(
            lambda c: c.execute(
                f"SELECT item, distance FROM {table} WHERE embedding MATCH ? AND k = ? AND kind = ? ORDER BY distance",
                (_blob(vector), limit, kind),
            ).fetchall()
        )
        return [(str(item), float(distance)) for item, distance in rows]

    async def fingerprints(self, space: EmbeddingSpace, kind: str) -> Mapping[str, str]:
        table = await self._create(space)
        rows = await self.database.read(
            lambda c: c.execute(f"SELECT item, fingerprint FROM {table} WHERE kind = ?", (kind,)).fetchall()
        )
        return {str(item): str(fingerprint) for item, fingerprint in rows}

    async def keep_only(self, space: EmbeddingSpace) -> None:
        def drop(connection: sqlite3.Connection) -> None:
            for table in _tables(connection):
                if table != _table(space):
                    connection.execute(f"DROP TABLE {table}")

        await self.database.write(drop)
        self._ready &= {_table(space)}

    async def _create(self, space: EmbeddingSpace) -> str:
        table = _table(space)
        if table not in self._ready:
            await self.database.write(
                lambda c: c.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0 (id TEXT PRIMARY KEY, "
                    f"embedding FLOAT[{space.dimensions}] distance_metric=cosine, kind TEXT, +item TEXT, "
                    "+fingerprint TEXT)"
                )
            )
            self._ready.add(table)
        return table


def _tables(connection: sqlite3.Connection) -> list[str]:
    """The vector tables, without the shadow tables sqlite-vec keeps for each."""
    names = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL%'")
    return [name for (name,) in names if _TABLE.match(name)]
