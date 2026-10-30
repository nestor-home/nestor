"""Double and contract suite for the memory store."""

import unicodedata

from nestor.core import PersonId
from nestor.modules.memory import Memory, MemoryStore


def words(text: str) -> set[str]:
    """Lower-cased words without accents: how memory search compares text."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return {w for w in "".join(c if c.isalnum() else " " for c in plain).split() if len(w) > 1}


class InMemoryMemoryStore(MemoryStore):
    name = "memory-store"

    def __init__(self) -> None:
        self.memories: dict[str, Memory] = {}

    async def put(self, memory: Memory) -> None:
        self.memories[memory.id] = memory

    async def get(self, memory_id: str) -> Memory | None:
        return self.memories.get(memory_id)

    async def delete(self, memory_id: str) -> None:
        self.memories.pop(memory_id, None)

    async def search(self, query: str, *, about: PersonId | None = None, limit: int = 10) -> list[Memory]:
        wanted = words(query)
        scored = [
            (len(wanted & words(m.text)), m)
            for m in self.memories.values()
            if about is None or m.about in (about, None)
        ]
        return [m for score, m in sorted(scored, key=lambda s: -s[0]) if score][:limit]

    async def recent(self, *, about: PersonId | None = None, limit: int = 20) -> list[Memory]:
        kept = [m for m in self.memories.values() if about is None or m.about in (about, None)]
        return sorted(kept, key=lambda m: m.updated_at, reverse=True)[:limit]


class MemoryStoreContract:
    """Behaviour every `MemoryStore` must show. Implement `store()`; it is used as a context manager."""

    def store(self) -> MemoryStore:
        raise NotImplementedError

    async def test_a_memory_is_found_by_its_words_whatever_the_accents(self) -> None:
        mathilde = PersonId("mathilde")
        async with self.store() as store:
            await store.put(Memory(text="Mathilde est végétarienne", about=mathilde))
            await store.put(Memory(text="Le code du portail est 1234"))
            found = await store.search("menu vegetarien pour MATHILDE")
        assert [m.text for m in found][:1] == ["Mathilde est végétarienne"]

    async def test_a_search_about_someone_keeps_their_memories_and_the_household_ones(self) -> None:
        mathis, mathilde = PersonId("mathis"), PersonId("mathilde")
        async with self.store() as store:
            await store.put(Memory(text="aime le café serré", about=mathis))
            await store.put(Memory(text="aime le café au lait", about=mathilde))
            await store.put(Memory(text="le café est dans le placard"))
            found = await store.search("café", about=mathis)
        assert sorted(m.text for m in found) == ["aime le café serré", "le café est dans le placard"]

    async def test_a_memory_is_replaced_then_deleted(self) -> None:
        async with self.store() as store:
            memory = Memory(text="Le chat s'appelle Biscotte")
            await store.put(memory)
            await store.put(memory.corrected("Le chat s'appelle Brioche"))
            stored = await store.get(memory.id)
            assert stored is not None and stored.text == "Le chat s'appelle Brioche"
            assert [m.text for m in await store.search("Biscotte")] == []
            await store.delete(memory.id)
            await store.delete(memory.id)
            assert await store.get(memory.id) is None
            assert await store.search("Brioche") == []

    async def test_recent_memories_come_newest_first(self) -> None:
        async with self.store() as store:
            for text in ("premier", "deuxième", "troisième"):
                await store.put(Memory(text=text))
            recent = await store.recent(limit=2)
        assert [m.text for m in recent] == ["troisième", "deuxième"]
