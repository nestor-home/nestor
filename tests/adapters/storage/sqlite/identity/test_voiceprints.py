"""Voiceprints in SQLite: the contract."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase
from nestor.adapters.storage.sqlite.identity import SQLiteVoiceprintStore
from nestor.testing.identity import VoiceprintStoreContract


class TestSQLiteVoiceprintStore(VoiceprintStoreContract):
    @pytest.fixture(autouse=True)
    def _path(self, db_path: Path) -> None:
        self.path = db_path

    def store(self) -> SQLiteVoiceprintStore:
        return SQLiteVoiceprintStore(SQLiteDatabase(self.path), owns_database=True)
