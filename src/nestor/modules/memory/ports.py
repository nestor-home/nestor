"""The memory store port: the searchable projection of memories."""

from abc import ABC, abstractmethod
from collections.abc import Collection

from nestor.core import Component, PersonId
from nestor.modules.memory.types import Memory, Place


class MemoryStore(Component, ABC):
    """Contract (checked by `nestor.testing.memory.MemoryStoreContract`):
    - `put` inserts or replaces by id; `get` of an unknown id is `None`, `get_many` leaves it out; `delete` of
      one is a no-op;
    - `search` finds memories sharing words with the query or with the name of their project or topic, ignoring
      case and accents, best first;
    - `recent` lists by last update, newest first; `everything` lists them all, in no particular order; `tied`, those
      tied to one task (`task:<id>`);
    - `about` restricts to one person's and those every member shares (any place but another person's); `place`
      to that place, or to that shelf when it names none (`projects`).
    """

    @abstractmethod
    async def put(self, memory: Memory) -> None: ...

    @abstractmethod
    async def get(self, memory_id: str) -> Memory | None: ...

    @abstractmethod
    async def get_many(self, ids: Collection[str]) -> list[Memory]: ...

    @abstractmethod
    async def delete(self, memory_id: str) -> None: ...

    @abstractmethod
    async def search(
        self, query: str, *, about: PersonId | None = None, place: Place | None = None, limit: int = 10
    ) -> list[Memory]: ...

    @abstractmethod
    async def recent(
        self, *, about: PersonId | None = None, place: Place | None = None, limit: int = 20
    ) -> list[Memory]: ...

    @abstractmethod
    async def everything(self) -> list[Memory]: ...

    @abstractmethod
    async def tied(self, tie: str) -> list[Memory]: ...
