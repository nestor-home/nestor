"""The episode store port: the searchable projection of the episodes worth recalling."""

from abc import ABC, abstractmethod
from collections.abc import Collection
from datetime import datetime

from nestor.core import Component, PersonId
from nestor.modules.memory.episodes.types import Episode


class EpisodeStore(Component, ABC):
    """Contract (checked by `nestor.testing.memory.EpisodeStoreContract`):
    - `put` inserts or replaces by id; `get_many` leaves an unknown id out; `everything` lists them all;
    - `search` finds the episodes of `person` sharing words with the query, ignoring case and accents, best
      first; `recent` lists them by end, newest first; both keep only those that ended within `since` and
      `until` when given.
    """

    @abstractmethod
    async def put(self, episode: Episode) -> None: ...

    @abstractmethod
    async def get_many(self, ids: Collection[str]) -> list[Episode]: ...

    @abstractmethod
    async def everything(self) -> list[Episode]: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        person: PersonId,
        limit: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Episode]: ...

    @abstractmethod
    async def recent(
        self, *, person: PersonId, limit: int, since: datetime | None = None, until: datetime | None = None
    ) -> list[Episode]: ...
