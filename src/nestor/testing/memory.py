"""Doubles and contract suites for the memory and episode stores."""

from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from nestor.core import PersonId
from nestor.modules.channels import Address, Medium
from nestor.modules.memory import Memory, MemoryStore
from nestor.modules.memory.episodes import Episode, EpisodeStore
from nestor.testing.text import folded_words


def words(text: str) -> set[str]:
    """Lower-cased words without accents, of two letters or more: how memory search compares text."""
    return {w for w in folded_words(text) if len(w) > 1}


class InMemoryMemoryStore(MemoryStore):
    name = "memory-store"

    def __init__(self) -> None:
        self.memories: dict[str, Memory] = {}

    async def put(self, memory: Memory) -> None:
        self.memories[memory.id] = memory

    async def get(self, memory_id: str) -> Memory | None:
        return self.memories.get(memory_id)

    async def get_many(self, ids: Collection[str]) -> list[Memory]:
        return [m for i in dict.fromkeys(ids) if (m := self.memories.get(i)) is not None]

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

    async def everything(self) -> list[Memory]:
        return list(self.memories.values())


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

    async def test_several_memories_are_read_at_once_and_all_of_them_listed(self) -> None:
        async with self.store() as store:
            kept = [Memory(text=text) for text in ("premier", "deuxième", "troisième")]
            for memory in kept:
                await store.put(memory)
            some = await store.get_many([kept[0].id, "absent", kept[2].id, kept[0].id])
            assert sorted(m.text for m in some) == ["premier", "troisième"], "an unknown id is left out, once"
            assert await store.get_many([]) == []
            assert sorted(m.id for m in await store.everything()) == sorted(m.id for m in kept)


class InMemoryEpisodeStore(EpisodeStore):
    name = "episode-store"

    def __init__(self) -> None:
        self.episodes: dict[str, Episode] = {}

    async def put(self, episode: Episode) -> None:
        self.episodes[episode.id] = episode

    async def get_many(self, ids: Collection[str]) -> list[Episode]:
        return [e for i in dict.fromkeys(ids) if (e := self.episodes.get(i)) is not None]

    async def everything(self) -> list[Episode]:
        return list(self.episodes.values())

    async def search(
        self,
        query: str,
        *,
        person: PersonId,
        limit: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Episode]:
        wanted = words(query)
        scored = [(len(wanted & words(e.text)), e) for e in self._theirs(person, since, until)]
        return [e for score, e in sorted(scored, key=lambda s: -s[0]) if score][:limit]

    async def recent(
        self, *, person: PersonId, limit: int, since: datetime | None = None, until: datetime | None = None
    ) -> list[Episode]:
        return sorted(self._theirs(person, since, until), key=lambda e: e.ended_at, reverse=True)[:limit]

    def _theirs(self, person: PersonId, since: datetime | None, until: datetime | None) -> list[Episode]:
        return [e for e in self.episodes.values() if e.seen_by(person, since, until)]


def episode(
    id: str, summary: str, *people: str, ended: datetime, address: Address | None = None, topics: tuple[str, ...] = ()
) -> Episode:
    """An episode for a test: a conversation of `people` that ended at `ended`."""
    return Episode(
        id=id,
        address=address or Address("telegram", "42"),
        medium=Medium.WRITTEN,
        participants=tuple(PersonId(p) for p in people),
        started_at=ended - timedelta(minutes=5),
        ended_at=ended,
        summary=summary,
        topics=topics,
    )


class EpisodeStoreContract:
    """Behaviour every `EpisodeStore` must show. Implement `store()`; it is used as a context manager."""

    def store(self) -> EpisodeStore:
        raise NotImplementedError

    async def test_only_the_participants_find_an_episode_by_its_words_whatever_the_accents(self) -> None:
        at = datetime(2026, 10, 20, 20, tzinfo=UTC)
        async with self.store() as store:
            await store.put(episode("e1", "Léa a parlé du restaurant Da Marco", "lea", ended=at, topics=("dîner",)))
            await store.put(episode("e2", "Hugo et le restaurant chinois", "hugo", ended=at))
            assert [e.id for e in await store.search("RESTAURANT diner", person=PersonId("lea"), limit=5)] == ["e1"]
            assert await store.search("Da Marco", person=PersonId("hugo"), limit=5) == []

    async def test_the_latest_come_first_within_the_dates_asked(self) -> None:
        async with self.store() as store:
            for day in (20, 25, 30):
                ended = datetime(2026, 10, day, 12, tzinfo=UTC)
                await store.put(episode(f"e{day}", f"le {day}", "lea", ended=ended))
            lea = PersonId("lea")
            assert [e.id for e in await store.recent(person=lea, limit=2)] == ["e30", "e25"]
            within = await store.recent(
                person=lea, limit=5, since=datetime(2026, 10, 21, tzinfo=UTC), until=datetime(2026, 10, 29, tzinfo=UTC)
            )
            assert [e.id for e in within] == ["e25"]
            assert [e.id for e in await store.recent(person=PersonId("hugo"), limit=5)] == []

    async def test_episodes_are_replaced_read_at_once_and_listed(self) -> None:
        at = datetime(2026, 10, 20, tzinfo=UTC)
        async with self.store() as store:
            await store.put(episode("e1", "avant", "lea", ended=at))
            await store.put(episode("e1", "après", "lea", ended=at))
            await store.put(episode("e2", "autre", "hugo", ended=at))
            assert [e.summary for e in await store.get_many(["e1", "absent", "e1"])] == ["après"]
            assert sorted(e.id for e in await store.everything()) == ["e1", "e2"]
