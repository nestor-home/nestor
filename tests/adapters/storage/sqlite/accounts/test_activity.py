"""Account activity in SQLite: the contract."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteActivityStore, SQLiteDatabase
from nestor.modules.accounts import ActivityStore
from nestor.testing.accounts import ActivityStoreContract


class TestSQLiteActivityStore(ActivityStoreContract):
    @pytest.fixture(autouse=True)
    def _directory(self, tmp_path: Path) -> None:
        self.path = tmp_path / "nestor.db"

    def store(self) -> ActivityStore:
        return SQLiteActivityStore(SQLiteDatabase(self.path), owns_database=True)
