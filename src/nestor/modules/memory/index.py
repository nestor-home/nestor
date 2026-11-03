"""The vectors of a corpus (the memories, the episodes), a projection kept in step in the background: what is
written, changed or removed is embedded or dropped as it changes, and everything is reconciled at start (a new
model, items written while the embedder was down). A conversation never waits for an embedding call to write.
Optional: without it, a corpus is searched by its words only.

Search is hybrid, as Anthropic's contextual retrieval does it: the items found by their words (FTS5, BM25)
and those nearest in meaning are fused by reciprocal rank, so an item high in either list comes high, one in
both comes first.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from typing import Protocol

from nestor.core import Component, ProviderError
from nestor.modules.cognition.embedding import Embedder, Indexed, Vector, VectorIndex, fingerprint

log = logging.getLogger("nestor.memory")
BATCH = 64  # items embedded and stored together: a failure loses at most one batch
RRF_K = 60  # the usual constant of reciprocal rank fusion: how much the first ranks weigh over the next
CANDIDATES = 30  # how deep each list is read before fusing


class Searchable(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def text(self) -> str: ...  # what is embedded


class Corpus[T: Searchable](Protocol):
    """What an index reads: every item, or some by id (an unknown id is left out)."""

    async def everything(self) -> list[T]: ...

    async def get_many(self, ids: Collection[str]) -> list[T]: ...


class SearchIndex[T: Searchable](Component):
    """The vectors of one kind of item (`memory`, `episode`) in the embedder's space."""

    def __init__(
        self,
        kind: str,
        corpus: Corpus[T],
        embedder: Embedder,
        vectors: VectorIndex,
        *,
        query_timeout_s: float = 1.0,
    ) -> None:
        self.kind, self.corpus, self.embedder, self.vectors = kind, corpus, embedder, vectors
        self.name = f"{kind}-index"
        self.query_timeout_s = query_timeout_s  # a turn waits this long for the question's vector, then words only
        self._changed: set[str] = set()  # items to embed again or drop
        self._everything = False  # a full reconciliation is due
        self._dirty = asyncio.Event()
        self._idle = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._keep_in_step(), name=self.name)
        self.refresh()

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def refresh(self, item: str | None = None) -> None:
        """An item changed (written, corrected, removed), or with none, any may have: catch up soon, once for
        any number of changes meanwhile."""
        if item is None:
            self._everything = True
        else:
            self._changed.add(item)
        self._idle.clear()
        self._dirty.set()

    async def settled(self) -> None:
        """Until every change asked for is caught up with, or failed (tried again at the next change)."""
        await self._idle.wait()

    async def reconcile(self) -> int:
        """Embed every item the embedder's space lacks or holds an older text of, drop the vectors of removed
        ones and of other spaces (a model replaced). Returns how many were embedded."""
        space = self.embedder.space
        known = await self.vectors.fingerprints(space, self.kind)
        items = await self.corpus.everything()
        embedded = await self._embed([i for i in items if known.get(i.id) != fingerprint(i.text)])
        await self.vectors.delete(self.kind, known.keys() - {i.id for i in items})
        await self.vectors.keep_only(space)
        return embedded

    async def catch_up(self, ids: Collection[str]) -> int:
        """Embed these items again, and drop the vectors of those that are gone."""
        present = await self.corpus.get_many(ids)
        await self.vectors.delete(self.kind, set(ids) - {i.id for i in present})
        return await self._embed(present)

    async def query(self, text: str) -> Vector | None:
        """The vector of a question; none when the embedder cannot answer in time (search by words only)."""
        try:
            return await asyncio.wait_for(self.embedder.embed_query(text), self.query_timeout_s)
        except TimeoutError:
            log.warning("searching by words only: no vector within %.1f s", self.query_timeout_s)
        except ProviderError as error:
            log.warning("searching by words only: %s", error)
        return None

    async def search(
        self,
        by_words: Sequence[T],
        vector: Vector | None,
        *,
        limit: int,
        exclude: Collection[str] = (),
        keep: Callable[[T], bool] = lambda _: True,
    ) -> list[T]:
        """The best `limit` items: `by_words` (already filtered by the corpus) fused with the nearest to
        `vector` that `keep` accepts, leaving out `exclude` (already shown)."""
        found = [i for i in by_words if i.id not in exclude]
        if vector is None:
            return found[:limit]
        depth = max(limit, CANDIDATES) + len(exclude)
        ids = [i for i, _ in await self.vectors.nearest(self.embedder.space, self.kind, vector, depth)]
        wanted = [i for i in ids if i not in exclude]
        known = {i.id: i for i in found}
        known |= {i.id: i for i in await self.corpus.get_many([i for i in wanted if i not in known])}
        nearest = [item for i in wanted if (item := known.get(i)) is not None and keep(item)]
        return fused((found, nearest))[:limit]

    async def _embed(self, items: Sequence[T]) -> int:
        """Embed and store by batches, each kept as soon as it is done."""
        for start in range(0, len(items), BATCH):
            batch = items[start : start + BATCH]
            vectors = await self.embedder.embed_documents([i.text for i in batch])
            indexed = [Indexed(i.id, fingerprint(i.text), v) for i, v in zip(batch, vectors, strict=True)]
            await self.vectors.put(self.embedder.space, self.kind, indexed)
        return len(items)

    async def _keep_in_step(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            everything, changed = self._everything, self._changed
            self._everything, self._changed = False, set()
            try:
                await (self.reconcile() if everything else self.catch_up(changed))
            except ProviderError as error:  # found by their words meanwhile; tried again at the next start
                log.warning("%s not embedded: %s", self.kind, error)
            except Exception:  # never stop keeping up: the next change is tried all the same
                log.exception("the %s index failed to catch up", self.kind)
            if not self._dirty.is_set():
                self._idle.set()


async def recalled[T: Searchable](
    index: SearchIndex[T] | None,
    query: str,
    by_words: Callable[[int], Awaitable[list[T]]],
    vector: Awaitable[Vector | None] | None = None,
    *,
    limit: int,
    exclude: Collection[str] = (),
    keep: Callable[[T], bool] = lambda _: True,
) -> list[T]:
    """The best `limit` items: those `by_words` finds (given how deep to read), fused with the nearest to the
    query's vector when there is an index, the words alone otherwise. The vector is computed while the words are
    searched; a caller searching several corpora passes it, to embed the query once."""
    if index is None:
        return [i for i in await by_words(limit + len(exclude)) if i.id not in exclude][:limit]
    embedding = asyncio.ensure_future(vector or index.query(query))
    try:
        found = await by_words(max(limit, CANDIDATES) + len(exclude))
        return await index.search(found, await embedding, limit=limit, exclude=exclude, keep=keep)
    finally:
        if vector is None:
            embedding.cancel()


def fused[T: Searchable](rankings: Sequence[Sequence[T]]) -> list[T]:
    """Reciprocal rank fusion of ranked lists, best first."""
    scores: dict[str, float] = {}
    items: dict[str, T] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (RRF_K + rank + 1)
            items[item.id] = item
    return [items[i] for i in sorted(scores, key=lambda i: -scores[i])]
