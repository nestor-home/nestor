"""Account verifiers in SQLite: the same contract, kept across restarts without any instance key."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteVerifierStore
from nestor.modules.accounts import VerifierStore
from nestor.testing.accounts import VerifierStoreContract


class TestSQLiteVerifierStore(VerifierStoreContract):
    @pytest.fixture(autouse=True)
    def _directory(self, tmp_path: Path) -> None:
        self.path = tmp_path / "nestor.db"

    def store(self) -> VerifierStore:
        return SQLiteVerifierStore(SQLiteDatabase(self.path), owns_database=True)


async def test_verifiers_survive_a_restart(tmp_path: Path) -> None:
    async with SQLiteVerifierStore(SQLiteDatabase(tmp_path / "n.db"), owns_database=True) as store:
        await store.put("account:a", "scrypt$kept")
    async with SQLiteVerifierStore(SQLiteDatabase(tmp_path / "n.db"), owns_database=True) as store:
        assert await store.get("account:a") == "scrypt$kept"
