"""The usage ledger in SQLite: the contract."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteUsageStore
from nestor.modules.usage import UsageStore
from nestor.testing.usage import UsageStoreContract


class TestSQLiteUsageStore(UsageStoreContract):
    @pytest.fixture(autouse=True)
    def _directory(self, tmp_path: Path) -> None:
        self.path = tmp_path / "nestor.db"

    def store(self) -> UsageStore:
        return SQLiteUsageStore(SQLiteDatabase(self.path), owns_database=True)
