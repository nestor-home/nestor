"""Remembering, recalling, correcting and forgetting — every change logged before it applies. Recall is hybrid
when an index is plugged in (words and meaning, see `index`), by words only without."""

from collections.abc import Awaitable, Collection

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.embedding import Vector
from nestor.modules.journal import Journal
from nestor.modules.memory.events import MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.index import SearchIndex, recalled
from nestor.modules.memory.ports import MemoryStore
from nestor.modules.memory.types import Memory


class Memories:
    def __init__(self, journal: Journal, store: MemoryStore, index: SearchIndex[Memory] | None = None) -> None:
        self.journal, self.store, self.index = journal, store, index

    async def remember(
        self,
        text: str,
        *,
        about: PersonId | None = None,
        source: Address | None = None,
        told_by: PersonId | None = None,
        exchange: Exchange | None = None,
        episode: str | None = None,
    ) -> Memory:
        text = text.strip()
        if not text:
            raise ContractError("a memory needs some text")
        memory = Memory(text=text, about=about, source=source, told_by=told_by)
        await self.journal.publish(
            MemoryRecorded(
                source="memory",
                session=source.session if source else None,
                memory_id=memory.id,
                text=text,
                about=about,
                learnt_in=source,
                told_by=told_by,
                exchange=exchange,
                episode=episode,
            )
        )
        await self.store.put(memory)
        if self.index:
            self.index.refresh(memory.id)
        return memory

    async def correct(
        self, memory_id: str, text: str, *, by: PersonId | None = None, exchange: Exchange | None = None
    ) -> Memory:
        memory = await self._existing(memory_id)
        corrected = memory.corrected(text.strip())
        await self.journal.publish(
            MemoryCorrected(source="memory", memory_id=memory_id, text=corrected.text, by=by, exchange=exchange)
        )
        await self.store.put(corrected)
        if self.index:
            self.index.refresh(corrected.id)
        return corrected

    async def forget(self, memory_id: str, *, by: PersonId | None = None, exchange: Exchange | None = None) -> Memory:
        memory = await self._existing(memory_id)
        await self.journal.publish(MemoryForgotten(source="memory", memory_id=memory_id, by=by, exchange=exchange))
        await self.store.delete(memory_id)
        if self.index:
            self.index.refresh(memory_id)
        return memory

    async def query(self, text: str) -> Vector | None:
        """The vector of a question, to recall by meaning; none without an index or in time."""
        return await self.index.query(text) if self.index else None

    async def recall(
        self,
        query: str,
        *,
        vector: Awaitable[Vector | None] | None = None,
        about: PersonId | None = None,
        limit: int = 8,
        exclude: Collection[str] = (),
    ) -> list[Memory]:
        """The best `limit` memories for `query` (and its `vector`, see `query`), leaving out `exclude` (already
        shown)."""
        return await recalled(
            self.index,
            query,
            lambda depth: self.store.search(query, about=about, limit=depth),
            vector,
            limit=limit,
            exclude=exclude,
            keep=lambda m: about is None or m.about in (about, None),
        )

    async def recent(self, *, about: PersonId | None = None, limit: int = 20) -> list[Memory]:
        return await self.store.recent(about=about, limit=limit)

    async def _existing(self, memory_id: str) -> Memory:
        memory = await self.store.get(memory_id)
        if memory is None:
            raise ContractError(f"no memory {memory_id!r}")
        return memory
