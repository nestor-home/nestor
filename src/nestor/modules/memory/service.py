"""Remembering, recalling, correcting and forgetting — every change logged before it applies.

Recall is hybrid when an index is plugged in: the memories found by their words (FTS5, BM25) and those nearest
in meaning (vectors) are fused by reciprocal rank, as Anthropic's contextual retrieval does: a memory high in
either list comes high, one in both comes first. Without an index, by words only.
"""

from collections.abc import Sequence

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.journal import Journal
from nestor.modules.memory.events import MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.index import MemoryIndex
from nestor.modules.memory.ports import MemoryStore
from nestor.modules.memory.types import Memory

RRF_K = 60  # the usual constant of reciprocal rank fusion: how much the first ranks weigh over the next
CANDIDATES = 30  # how deep each list is read before fusing


class Memories:
    def __init__(self, journal: Journal, store: MemoryStore, index: MemoryIndex | None = None) -> None:
        self.journal, self.store, self.index = journal, store, index

    async def remember(
        self,
        text: str,
        *,
        about: PersonId | None = None,
        source: Address | None = None,
        told_by: PersonId | None = None,
        exchange: Exchange | None = None,
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
            )
        )
        await self.store.put(memory)
        if self.index:
            await self.index.index(memory)
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
            await self.index.index(corrected)
        return corrected

    async def forget(self, memory_id: str, *, by: PersonId | None = None, exchange: Exchange | None = None) -> Memory:
        memory = await self._existing(memory_id)
        await self.journal.publish(MemoryForgotten(source="memory", memory_id=memory_id, by=by, exchange=exchange))
        await self.store.delete(memory_id)
        if self.index:
            await self.index.unindex(memory_id)
        return memory

    async def recall(self, query: str, *, about: PersonId | None = None, limit: int = 8) -> list[Memory]:
        depth = max(limit, CANDIDATES)
        by_words = await self.store.search(query, about=about, limit=depth)
        if self.index is None:
            return by_words[:limit]
        known = {m.id: m for m in by_words}
        nearest: list[Memory] = []
        for memory_id in await self.index.nearest(query, depth):
            memory = known.get(memory_id) or await self.store.get(memory_id)
            if memory is not None and (about is None or memory.about in (about, None)):
                nearest.append(memory)
        return fused((by_words, nearest))[:limit]

    async def recent(self, *, about: PersonId | None = None, limit: int = 20) -> list[Memory]:
        return await self.store.recent(about=about, limit=limit)

    async def _existing(self, memory_id: str) -> Memory:
        memory = await self.store.get(memory_id)
        if memory is None:
            raise ContractError(f"no memory {memory_id!r}")
        return memory


def fused(rankings: Sequence[Sequence[Memory]]) -> list[Memory]:
    """Reciprocal rank fusion of ranked lists, best first."""
    scores: dict[str, float] = {}
    memories: dict[str, Memory] = {}
    for ranking in rankings:
        for rank, memory in enumerate(ranking):
            scores[memory.id] = scores.get(memory.id, 0.0) + 1.0 / (RRF_K + rank + 1)
            memories[memory.id] = memory
    return [memories[i] for i in sorted(scores, key=lambda i: -scores[i])]
