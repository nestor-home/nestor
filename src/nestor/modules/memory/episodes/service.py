"""Recording episodes and bringing back those of a person: the latest, and those a question finds by words and
by meaning (see `memory.index`)."""

from collections.abc import Collection
from datetime import datetime

from nestor.core import PersonId
from nestor.modules.cognition.embedding import Vector
from nestor.modules.journal import Journal
from nestor.modules.memory.episodes.events import EpisodeSummarized
from nestor.modules.memory.episodes.ports import EpisodeStore
from nestor.modules.memory.episodes.types import Episode
from nestor.modules.memory.index import CANDIDATES, SearchIndex


class Episodes:
    def __init__(self, journal: Journal, store: EpisodeStore, index: SearchIndex[Episode] | None = None) -> None:
        self.journal, self.store, self.index = journal, store, index

    async def record(self, episode: Episode) -> None:
        """Journal it, then keep it if it is worth recalling."""
        await self.journal.publish(
            EpisodeSummarized(
                source="memory",
                session=episode.address.session,
                conversation_id=episode.id,
                address=episode.address,
                medium=episode.medium,
                participants=episode.participants,
                started_at=episode.started_at,
                ended_at=episode.ended_at,
                summary=episode.summary,
                topics=episode.topics,
            )
        )
        if episode.summary:
            await self.store.put(episode)
            if self.index:
                self.index.refresh(episode.id)

    async def recent(
        self, person: PersonId, *, limit: int, since: datetime | None = None, until: datetime | None = None
    ) -> list[Episode]:
        return await self.store.recent(person=person, limit=limit, since=since, until=until)

    async def recall(
        self,
        query: str,
        *,
        vector: Vector | None,
        person: PersonId,
        limit: int,
        exclude: Collection[str] = (),
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Episode]:
        """The episodes of `person` best matching `query` (and its `vector`), within `since` and `until`."""
        by_words = await self.store.search(
            query, person=person, limit=max(limit, CANDIDATES) + len(exclude), since=since, until=until
        )
        if self.index is None:
            return [e for e in by_words if e.id not in exclude][:limit]

        def theirs(episode: Episode) -> bool:
            return person in episode.participants and (
                (since is None or episode.ended_at >= since) and (until is None or episode.ended_at <= until)
            )

        return await self.index.search(by_words, vector, limit=limit, exclude=exclude, keep=theirs)
