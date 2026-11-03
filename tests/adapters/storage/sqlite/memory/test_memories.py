"""Memories in SQLite: the contract, full-text search that never becomes syntax, and a restart."""

from pathlib import Path

import pytest

from nestor.adapters.storage.sqlite import SQLiteDatabase, SQLiteMemoryStore
from nestor.core import PersonId
from nestor.modules.channels import Address
from nestor.modules.memory import Memory
from nestor.testing.memory import MemoryStoreContract


class TestSQLiteMemoryStore(MemoryStoreContract):
    @pytest.fixture(autouse=True)
    def _path(self, db_path: Path) -> None:
        self.path = db_path

    def store(self) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(SQLiteDatabase(self.path), owns_database=True)


async def test_search_text_never_becomes_fts_syntax(db_path: Path) -> None:
    async with SQLiteMemoryStore(SQLiteDatabase(db_path), owns_database=True) as store:
        await store.put(Memory(text='Le mot de passe du wifi est "maison"'))
        assert [m.text for m in await store.search('wifi" OR text:* NEAR(')] == ['Le mot de passe du wifi est "maison"']
        assert await store.search("?! *") == []


async def test_memories_survive_a_restart_with_their_source(db_path: Path) -> None:
    memory = Memory(text="Biscotte est le chat", source=Address("voice", "salon"), told_by=PersonId("mathis"))
    async with SQLiteMemoryStore(SQLiteDatabase(db_path), owns_database=True) as store:
        await store.put(memory)
    async with SQLiteMemoryStore(SQLiteDatabase(db_path), owns_database=True) as store:
        assert await store.get(memory.id) == memory
        assert await store.recent(about=PersonId("mathis")) == [memory]
