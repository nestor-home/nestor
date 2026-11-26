"""Remembering, recalling, correcting, moving, forgetting and retiring — every change logged before it applies.
Recall is hybrid when an index is plugged in (words and meaning, see `index`), by words only without."""

from collections.abc import Awaitable, Collection

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.embedding import Vector
from nestor.modules.journal import Journal
from nestor.modules.memory.events import (
    MemoryCorrected,
    MemoryForgotten,
    MemoryMoved,
    MemoryRecorded,
    MemoryRetired,
)
from nestor.modules.memory.index import SearchIndex, recalled
from nestor.modules.memory.ports import MemoryStore
from nestor.modules.memory.types import HOUSEHOLD, Memory, Place, Retirement


class Memories:
    def __init__(self, journal: Journal, store: MemoryStore, index: SearchIndex[Memory] | None = None) -> None:
        self.journal, self.store, self.index = journal, store, index

    async def remember(
        self,
        text: str,
        *,
        place: Place = HOUSEHOLD,
        source: Address | None = None,
        told_by: PersonId | None = None,
        exchange: Exchange | None = None,
        episode: str | None = None,
        task: str | None = None,
        tied_to: str | None = None,
    ) -> Memory:
        text = text.strip()
        if not text:
            raise ContractError("a memory needs some text")
        filed(place)
        memory = Memory(text=text, place=place, source=source, told_by=told_by, tied_to=tied_to)
        await self.journal.publish(
            MemoryRecorded(
                source="memory",
                session=source.session if source else None,
                memory_id=memory.id,
                text=text,
                place=str(place),
                learnt_in=source,
                told_by=told_by,
                exchange=exchange,
                episode=episode,
                task=task,
                tied_to=tied_to,
            )
        )
        await self._kept(memory)
        return memory

    async def correct(
        self,
        memory_id: str,
        text: str,
        *,
        by: PersonId | None = None,
        exchange: Exchange | None = None,
        merged: tuple[str, ...] = (),
    ) -> Memory:
        memory = await self._existing(memory_id)
        if not text.strip():
            raise ContractError("a memory needs some text")
        corrected = memory.corrected(text.strip())
        await self.journal.publish(
            MemoryCorrected(
                source="memory", memory_id=memory_id, text=corrected.text, by=by, exchange=exchange, merged=merged
            )
        )
        await self._kept(corrected)
        return corrected

    async def move(
        self, memory_id: str, place: Place, *, by: PersonId | None = None, exchange: Exchange | None = None
    ) -> Memory:
        memory = await self._existing(memory_id)
        moved = memory.moved(filed(place))
        await self.journal.publish(
            MemoryMoved(source="memory", memory_id=memory_id, place=str(place), by=by, exchange=exchange)
        )
        await self._kept(moved)
        return moved

    async def forget(self, memory_id: str, *, by: PersonId | None = None, exchange: Exchange | None = None) -> Memory:
        memory = await self._existing(memory_id)
        await self.journal.publish(MemoryForgotten(source="memory", memory_id=memory_id, by=by, exchange=exchange))
        await self._dropped(memory_id)
        return memory

    async def retire(
        self, memory_id: str, reason: Retirement, *, why: str | None = None, into: str | None = None
    ) -> Memory:
        """No longer used, and journaled with what it said and why: never erased without trace."""
        memory = await self._existing(memory_id)
        await self.journal.publish(
            MemoryRetired(
                source="memory",
                memory_id=memory_id,
                text=memory.text,
                place=str(memory.place),
                reason=reason,
                why=why,
                tied_to=memory.tied_to,
                into=into,
            )
        )
        await self._dropped(memory_id)
        return memory

    async def untie(self, tie: str) -> list[Memory]:
        """Retire the memories tied to `tie` (`task:<id>`), which has ended."""
        return [await self.retire(m.id, Retirement.ENDED) for m in await self.store.tied(tie)]

    async def query(self, text: str) -> Vector | None:
        """The vector of a question, to recall by meaning; none without an index or in time."""
        return await self.index.query(text) if self.index else None

    async def recall(
        self,
        query: str,
        *,
        vector: Awaitable[Vector | None] | None = None,
        about: PersonId | None = None,
        place: Place | None = None,
        limit: int = 8,
        exclude: Collection[str] = (),
    ) -> list[Memory]:
        """The best `limit` memories for `query` (and its `vector`, see `query`), leaving out `exclude` (already
        shown); `about` and `place` restrict them as the store does."""
        return await recalled(
            self.index,
            query,
            lambda depth: self.store.search(query, about=about, place=place, limit=depth),
            vector,
            limit=limit,
            exclude=exclude,
            keep=lambda m: (about is None or m.about in (about, None)) and (place is None or place.holds(m.place)),
        )

    async def recent(
        self, *, about: PersonId | None = None, place: Place | None = None, limit: int = 20
    ) -> list[Memory]:
        return await self.store.recent(about=about, place=place, limit=limit)

    async def _existing(self, memory_id: str) -> Memory:
        memory = await self.store.get(memory_id)
        if memory is None:
            raise ContractError(f"no memory {memory_id!r}")
        return memory

    async def _kept(self, memory: Memory) -> None:
        await self.store.put(memory)
        if self.index:
            self.index.refresh(memory.id)

    async def _dropped(self, memory_id: str) -> None:
        await self.store.delete(memory_id)
        if self.index:
            self.index.refresh(memory_id)


def filed(place: Place) -> Place:
    """`place`, when a memory can be filed there: a shelf of named places needs a name."""
    if place.whole:
        raise ContractError(f"a memory is filed in one of the {place.shelf.value}: {place.shelf.value}/<name>")
    return place
