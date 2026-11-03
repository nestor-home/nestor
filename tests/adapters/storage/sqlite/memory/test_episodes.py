"""Episodes in SQLite: the contract."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteEpisodeStore
from nestor.testing.memory import EpisodeStoreContract


class TestSQLiteEpisodeStore(EpisodeStoreContract):
    @pytest.fixture(autouse=True)
    def _path(self, db_path: Path) -> None:
        self.path = db_path

    def store(self) -> SQLiteEpisodeStore:
        return SQLiteEpisodeStore(SQLiteDatabase(self.path), owns_database=True)
