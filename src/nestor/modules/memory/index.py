"""The memories' vectors, a projection kept in step in the background: after a memory is remembered, corrected
or forgotten, and at start (a new model, memories written while the embedder was down). A conversation never
waits for an embedding call to write a memory. Optional: without it, memories are searched by their words only.
"""

import asyncio
import contextlib
import logging

from nestor.core import Component, ProviderError
from nestor.modules.cognition.embedding import Embedder, Indexed, VectorIndex, fingerprint
from nestor.modules.memory.ports import MemoryStore

log = logging.getLogger("nestor.memory")
KIND = "memory"
QUERY_TIMEOUT_S = 1.0  # a turn waits this long for the question's vector, then searches by words only


class MemoryIndex(Component):
    name = "memory-index"

    def __init__(self, store: MemoryStore, embedder: Embedder, vectors: VectorIndex) -> None:
        self.store, self.embedder, self.vectors = store, embedder, vectors
        self._dirty = asyncio.Event()  # memories changed since the last reconciliation
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

    def refresh(self) -> None:
        """Memories changed: reconcile soon, once for any number of changes meanwhile."""
        self._idle.clear()
        self._dirty.set()

    async def settled(self) -> None:
        """Until every change asked for is reconciled (or failed, to be tried at the next change)."""
        await self._idle.wait()

    async def reconcile(self) -> int:
        """Embed every memory the embedder's space lacks or holds an older text of, in one batch; drop the
        vectors of forgotten ones and of other spaces (a model replaced). Returns how many were embedded."""
        space = self.embedder.space
        known = await self.vectors.fingerprints(space, KIND)
        memories = await self.store.everything()
        stale = [m for m in memories if known.get(m.id) != fingerprint(m.text)]
        vectors = await self.embedder.embed_documents([m.text for m in stale])
        indexed = [Indexed(m.id, fingerprint(m.text), v) for m, v in zip(stale, vectors, strict=True)]
        await self.vectors.put(space, KIND, indexed)
        await self.vectors.delete(KIND, known.keys() - {m.id for m in memories})
        await self.vectors.keep_only(space)
        return len(stale)

    async def nearest(self, query: str, limit: int) -> list[str]:
        """The memories nearest to `query`, nearest first; none when the embedder cannot answer in time."""
        try:
            vector = await asyncio.wait_for(self.embedder.embed_query(query), QUERY_TIMEOUT_S)
        except (ProviderError, TimeoutError) as error:
            log.warning("searching memories by their words only: %s", error or "the embedder is slow")
            return []
        return [item for item, _ in await self.vectors.nearest(self.embedder.space, KIND, vector, limit)]

    async def _keep_in_step(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            try:
                await self.reconcile()
            except ProviderError as error:  # found by their words meanwhile; tried again at the next change
                log.warning("memories not embedded: %s", error)
            if not self._dirty.is_set():
                self._idle.set()
