"""Recording episodes and bringing back those of a person: the latest, and those a question finds by words and
by meaning (see `memory.index`)."""

from collections.abc import Awaitable, Collection
from datetime import datetime

from nestor.core import PersonId
from nestor.modules.cognition.embedding import Vector
from nestor.modules.journal import Journal
from nestor.modules.memory.episodes.events import EpisodeSummarized
from nestor.modules.memory.episodes.ports import EpisodeStore
from nestor.modules.memory.episodes.types import Episode
from nestor.modules.memory.index import SearchIndex, recalled


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

    async def find(self, conversation: str) -> Episode | None:
        """A conversation that ended, whether or not its summary was worth keeping (the journal has those)."""
        (kept,) = await self.store.get_many([conversation]) or (None,)
        if kept is not None:
            return kept
        for summarized in await self.journal.history(EpisodeSummarized, newest_first=True):
            if summarized.conversation_id == conversation:
                return Episode(
                    id=conversation,
                    address=summarized.address,
                    medium=summarized.medium,
                    participants=summarized.participants,
                    started_at=summarized.started_at,
                    ended_at=summarized.ended_at,
                    summary=summarized.summary,
                    topics=summarized.topics,
                )
        return None

    async def recent(
        self, person: PersonId, *, limit: int, since: datetime | None = None, until: datetime | None = None
    ) -> list[Episode]:
        return await self.store.recent(person=person, limit=limit, since=since, until=until)

    async def recall(
        self,
        query: str,
        *,
        vector: Awaitable[Vector | None] | None = None,
        person: PersonId,
        limit: int,
        exclude: Collection[str] = (),
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Episode]:
        """The episodes of `person` best matching `query` (and its `vector`), within `since` and `until`."""
        return await recalled(
            self.index,
            query,
            lambda depth: self.store.search(query, person=person, limit=depth, since=since, until=until),
            vector,
            limit=limit,
            exclude=exclude,
            keep=lambda episode: episode.seen_by(person, since, until),
        )
