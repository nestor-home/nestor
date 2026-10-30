"""Remembering, recalling, correcting and forgetting — every change logged before it applies."""

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address
from nestor.modules.journal import Journal
from nestor.modules.memory.events import MemoryCorrected, MemoryForgotten, MemoryRecorded
from nestor.modules.memory.ports import MemoryStore
from nestor.modules.memory.types import Memory


class Memories:
    def __init__(self, journal: Journal, store: MemoryStore) -> None:
        self.journal, self.store = journal, store

    async def remember(
        self,
        text: str,
        *,
        about: PersonId | None = None,
        source: Address | None = None,
        told_by: PersonId | None = None,
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
            )
        )
        await self.store.put(memory)
        return memory

    async def correct(self, memory_id: str, text: str, *, by: PersonId | None = None) -> Memory:
        memory = await self._existing(memory_id)
        corrected = memory.corrected(text.strip())
        await self.journal.publish(MemoryCorrected(source="memory", memory_id=memory_id, text=corrected.text, by=by))
        await self.store.put(corrected)
        return corrected

    async def forget(self, memory_id: str, *, by: PersonId | None = None) -> Memory:
        memory = await self._existing(memory_id)
        await self.journal.publish(MemoryForgotten(source="memory", memory_id=memory_id, by=by))
        await self.store.delete(memory_id)
        return memory

    async def recall(self, query: str, *, about: PersonId | None = None, limit: int = 8) -> list[Memory]:
        return await self.store.search(query, about=about, limit=limit)

    async def recent(self, *, about: PersonId | None = None, limit: int = 20) -> list[Memory]:
        return await self.store.recent(about=about, limit=limit)

    async def _existing(self, memory_id: str) -> Memory:
        memory = await self.store.get(memory_id)
        if memory is None:
            raise ContractError(f"no memory {memory_id!r}")
        return memory
