"""Vectors in SQLite with sqlite-vec: the index contract, one table per space, created on demand."""

import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteVectorIndex
from nestor.core import ContractError
from nestor.modules.cognition.embedding import EmbeddingSpace, Indexed, VectorIndex
from nestor.testing.cognition import VectorIndexContract


class TestSQLiteVectorIndex(VectorIndexContract):
    @pytest.fixture(autouse=True)
    def _folder(self, tmp_path: Path) -> None:
        self.folder = tmp_path

    def index(self) -> contextlib.AbstractAsyncContextManager[VectorIndex]:
        @contextlib.asynccontextmanager
        async def opened() -> AsyncGenerator[VectorIndex]:
            async with SQLiteDatabase(self.folder / "n.db") as database, SQLiteVectorIndex(database) as index:
                yield index

        return opened()


async def test_vectors_survive_a_restart_and_a_wrong_dimension_is_refused(tmp_path: Path) -> None:
    space = EmbeddingSpace(model="m", dimensions=3)
    async with SQLiteDatabase(tmp_path / "n.db") as database, SQLiteVectorIndex(database) as index:
        await index.put(space, "memory", [Indexed("a", "f", [1.0, 0.0, 0.0])])
        with pytest.raises(ContractError, match="2 dimensions in a space of 3"):
            await index.put(space, "memory", [Indexed("b", "f", [1.0, 0.0])])
    async with SQLiteDatabase(tmp_path / "n.db") as database, SQLiteVectorIndex(database) as index:
        assert await index.fingerprints(space, "memory") == {"a": "f"}
