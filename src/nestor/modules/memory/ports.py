"""The memory store port: the searchable projection of memories."""

from abc import ABC, abstractmethod

from nestor.core import Component, PersonId
from nestor.modules.memory.types import Memory


class MemoryStore(Component, ABC):
    """Contract (checked by `nestor.testing.memory.MemoryStoreContract`):
    - `put` inserts or replaces by id; `get` of an unknown id is `None`; `delete` of one is a no-op;
    - `search` finds memories sharing words with the query, ignoring case and accents, best first;
      `about` restricts to one person (household-wide memories are always included);
    - `recent` lists by last update, newest first.
    """

    @abstractmethod
    async def put(self, memory: Memory) -> None: ...

    @abstractmethod
    async def get(self, memory_id: str) -> Memory | None: ...

    @abstractmethod
    async def delete(self, memory_id: str) -> None: ...

    @abstractmethod
    async def search(self, query: str, *, about: PersonId | None = None, limit: int = 10) -> list[Memory]: ...

    @abstractmethod
    async def recent(self, *, about: PersonId | None = None, limit: int = 20) -> list[Memory]: ...
