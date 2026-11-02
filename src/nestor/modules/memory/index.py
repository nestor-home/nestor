"""The memories' vectors, a projection kept in step in the background: the memories remembered, corrected or
forgotten are embedded or dropped as they change, and everything is reconciled at start (a new model, memories
written while the embedder was down). A conversation never waits for an embedding call to write a memory.
Optional: without it, memories are searched by their words only.
"""

import asyncio
import contextlib
import logging
from collections.abc import Collection, Sequence

from nestor.core import Component, ProviderError
from nestor.modules.cognition.embedding import Embedder, Indexed, VectorIndex, fingerprint
from nestor.modules.memory.ports import MemoryStore
from nestor.modules.memory.types import Memory

log = logging.getLogger("nestor.memory")
KIND = "memory"
BATCH = 64  # memories embedded and stored together: a failure loses at most one batch


class MemoryIndex(Component):
    name = "memory-index"

    def __init__(
        self, store: MemoryStore, embedder: Embedder, vectors: VectorIndex, *, query_timeout_s: float = 1.0
    ) -> None:
        self.store, self.embedder, self.vectors = store, embedder, vectors
        self.query_timeout_s = query_timeout_s  # a turn waits this long for the question's vector, then words only
        self._changed: set[str] = set()  # memories to embed again or drop
        self._everything = False  # a full reconciliation is due
        self._dirty = asyncio.Event()
        self._idle = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._keep_in_step(), name="memory index")
        self.refresh()

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def refresh(self, memory_id: str | None = None) -> None:
        """A memory changed (remembered, corrected, forgotten), or with none, any may have: catch up soon, once
        for any number of changes meanwhile."""
        if memory_id is None:
            self._everything = True
        else:
            self._changed.add(memory_id)
        self._idle.clear()
        self._dirty.set()

    async def settled(self) -> None:
        """Until every change asked for is caught up with, or failed (tried again at the next change)."""
        await self._idle.wait()

    async def reconcile(self) -> int:
        """Embed every memory the embedder's space lacks or holds an older text of, drop the vectors of forgotten
        ones and of other spaces (a model replaced). Returns how many were embedded."""
        space = self.embedder.space
        known = await self.vectors.fingerprints(space, KIND)
        memories = await self.store.everything()
        embedded = await self._embed([m for m in memories if known.get(m.id) != fingerprint(m.text)])
        await self.vectors.delete(KIND, known.keys() - {m.id for m in memories})
        await self.vectors.keep_only(space)
        return embedded

    async def catch_up(self, memory_ids: Collection[str]) -> int:
        """Embed these memories again, and drop the vectors of those that are gone."""
        present = await self.store.get_many(memory_ids)
        await self.vectors.delete(KIND, set(memory_ids) - {m.id for m in present})
        return await self._embed(present)

    async def nearest(self, query: str, limit: int) -> list[str]:
        """The memories nearest to `query`, nearest first; none when the embedder cannot answer in time."""
        try:
            vector = await asyncio.wait_for(self.embedder.embed_query(query), self.query_timeout_s)
        except TimeoutError:
            log.warning("searching memories by their words only: no vector within %.1f s", self.query_timeout_s)
            return []
        except ProviderError as error:
            log.warning("searching memories by their words only: %s", error)
            return []
        return [item for item, _ in await self.vectors.nearest(self.embedder.space, KIND, vector, limit)]

    async def _embed(self, memories: Sequence[Memory]) -> int:
        """Embed and store by batches, each kept as soon as it is done."""
        for start in range(0, len(memories), BATCH):
            batch = memories[start : start + BATCH]
            vectors = await self.embedder.embed_documents([m.text for m in batch])
            indexed = [Indexed(m.id, fingerprint(m.text), v) for m, v in zip(batch, vectors, strict=True)]
            await self.vectors.put(self.embedder.space, KIND, indexed)
        return len(memories)

    async def _keep_in_step(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            everything, changed = self._everything, self._changed
            self._everything, self._changed = False, set()
            try:
                await (self.reconcile() if everything else self.catch_up(changed))
            except ProviderError as error:  # found by their words meanwhile; tried again at the next start
                log.warning("memories not embedded: %s", error)
            except Exception:  # never stop keeping up: the next change is tried all the same
                log.exception("the memory index failed to catch up")
            if not self._dirty.is_set():
                self._idle.set()
