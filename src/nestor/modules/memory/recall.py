"""What a turn's instructions carry of the past. Generous rather than precise, as ChatGPT does with its saved
memories and chat history: a line costs little, the model sorts them out, and missing one costs more than
carrying a few it does not need.

- The household layer carries every memory, the latest first, up to a budget: the same from a turn to the
  next, so the provider's prompt cache keeps it.
- Beyond the budget, the turn layer adds those the person's last messages find among the others.
- The turn layer carries the latest episodes of whoever speaks (what their recent conversations were about),
  then those their last messages find among the older ones.

Measured by the `memory-recall` bench.
"""

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple

from nestor.core import PersonId
from nestor.modules.memory.episodes import Episode, Episodes
from nestor.modules.memory.service import Memories
from nestor.modules.memory.types import Memory


class Strategy(StrEnum):
    BOTH = "both"  # the latest up to the budget, then those the words find among the others
    RECENT = "recent"  # the latest up to the budget only
    SEARCH = "search"  # those the words find only


@dataclass(frozen=True, slots=True, kw_only=True)
class RecallSettings:
    strategy: Strategy = Strategy.BOTH
    recent: int = 150  # the household layer's budget: a few thousand tokens, cached
    found: int = 12  # how many found memories at most, beyond those already shown
    recent_episodes: int = 3  # the latest conversations of whoever speaks
    found_episodes: int = 4  # how many found older conversations at most


class TurnMemories(NamedTuple):
    shown: list[Memory]  # the household layer's: the latest, up to the budget
    found: list[Memory]  # the turn layer's: what was said finds among the others
    latest_episodes: list[Episode]  # whoever speaks: their latest conversations
    found_episodes: list[Episode]  # whoever speaks: the older conversations what was said finds


async def for_turn(
    memories: Memories, episodes: Episodes, said: str | None, person: PersonId | None, settings: RecallSettings
) -> TurnMemories:
    """What a turn's instructions carry. Every memory of the household may matter, not only those about whoever
    speaks ("what does Léa like?"); episodes are only theirs. What is all shown already is not searched, and the
    question is embedded once for both searches, so a household that fits waits for no embedding call."""
    shown, latest = await asyncio.gather(
        memories.recent(limit=settings.recent) if settings.strategy is not Strategy.SEARCH else _nothing(),
        episodes.recent(person, limit=settings.recent_episodes + 1) if person else _nothing(),
    )
    older_episodes = len(latest) > settings.recent_episodes  # one more was asked for, to know
    latest = latest[: settings.recent_episodes]
    all_shown = settings.strategy is Strategy.BOTH and len(shown) < settings.recent
    search_memories = bool(said) and settings.strategy is not Strategy.RECENT and settings.found > 0 and not all_shown
    search_episodes = bool(said) and settings.found_episodes > 0 and older_episodes
    if not (search_memories or search_episodes) or not said:
        return TurnMemories(shown, [], latest, [])
    vector = asyncio.create_task(memories.query(said))
    try:
        found, found_episodes = await asyncio.gather(
            memories.recall(said, vector=vector, limit=settings.found, exclude={m.id for m in shown})
            if search_memories
            else _nothing(),
            episodes.recall(
                said, vector=vector, person=person, limit=settings.found_episodes, exclude={e.id for e in latest}
            )
            if search_episodes and person
            else _nothing(),
        )
    finally:
        vector.cancel()  # no longer needed, whatever happened
    return TurnMemories(shown, found, latest, found_episodes)


async def _nothing() -> list:
    return []
