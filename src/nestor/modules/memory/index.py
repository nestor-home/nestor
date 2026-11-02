"""The memories' vectors, kept in step with the memories: embedded when one is remembered or corrected, dropped
when it is forgotten, and reconciled at start (a new model, memories written while the embedder was down).
Optional: without it, memories are searched by their words only."""

import asyncio
import contextlib
import hashlib
import logging

from nestor.core import Component, ProviderError
from nestor.modules.cognition.embedding import Embedder, VectorIndex
from nestor.modules.memory.ports import MemoryStore
from nestor.modules.memory.types import Memory

log = logging.getLogger("nestor.memory")
KIND = "memory"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class MemoryIndex(Component):
    name = "memory-index"

    def __init__(self, store: MemoryStore, embedder: Embedder, vectors: VectorIndex) -> None:
        self.store, self.embedder, self.vectors = store, embedder, vectors
        self._reconciling: asyncio.Task[int] | None = None

    async def start(self) -> None:
        self._reconciling = asyncio.create_task(self.reconcile(), name="memory index")

    async def close(self) -> None:
        if self._reconciling is not None:
            self._reconciling.cancel()
            with contextlib.suppress(asyncio.CancelledError, ProviderError):
                await self._reconciling
            self._reconciling = None

    async def reconcile(self) -> int:
        """Embed every memory the embedder's space lacks or holds an older text of, drop the vectors of
        forgotten ones and of other spaces (a model replaced); returns how many were embedded. Until it is
        done, search finds the missing ones by their words."""
        space = self.embedder.space
        known = await self.vectors.fingerprints(space, KIND)
        memories = await self.store.everything()
        stale = [m for m in memories if known.get(m.id) != fingerprint(m.text)]
        for memory, vector in zip(stale, await self.embedder.embed_documents([m.text for m in stale]), strict=True):
            await self.vectors.put(space, KIND, memory.id, fingerprint(memory.text), vector)
        for gone in known.keys() - {m.id for m in memories}:
            await self.vectors.delete(KIND, gone)
        await self.vectors.keep_only(space)
        return len(stale)

    async def index(self, memory: Memory) -> None:
        try:
            (vector,) = await self.embedder.embed_documents([memory.text])
        except ProviderError as error:  # found by its words meanwhile; the next start embeds it
            log.warning("memory %s not embedded: %s", memory.id, error)
            return
        await self.vectors.put(self.embedder.space, KIND, memory.id, fingerprint(memory.text), vector)

    async def unindex(self, memory_id: str) -> None:
        await self.vectors.delete(KIND, memory_id)

    async def nearest(self, query: str, limit: int) -> list[str]:
        """The memories nearest to `query`, nearest first; none when the embedder cannot answer now."""
        try:
            vector = await self.embedder.embed_query(query)
        except ProviderError as error:
            log.warning("searching memories by their words only: %s", error)
            return []
        return [item for item, _ in await self.vectors.nearest(self.embedder.space, KIND, vector, limit)]
