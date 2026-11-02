"""Which memories go into a turn's instructions. Generous rather than precise, as ChatGPT does with its saved
memories: a memory is a short line, the model sorts them out, and missing one costs more than carrying a few
it does not need.

- The household layer carries every memory, the latest first, up to a budget: the same from a turn to the
  next, so the provider's prompt cache keeps it.
- Beyond the budget, the turn layer adds those the conversation's last words find among the others.

Measured by the `memory-recall` bench.
"""

from dataclasses import dataclass
from enum import StrEnum

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


async def latest(memories: Memories, settings: RecallSettings) -> list[Memory]:
    """The household layer's memories."""
    return await memories.recent(limit=settings.recent) if settings.strategy is not Strategy.SEARCH else []


async def found(memories: Memories, words: str | None, settings: RecallSettings) -> list[Memory]:
    """The turn layer's memories: those `words` find, without the ones the household layer already shows.
    Every memory of the household may matter, not only those about whoever speaks: "what does Léa like?"."""
    if not words or settings.strategy is Strategy.RECENT or not settings.found:
        return []
    shown = {m.id for m in await latest(memories, settings)}
    if settings.strategy is Strategy.BOTH and len(shown) < settings.recent:
        return []  # every memory is already shown: no search, no embedding call to wait for
    hits = await memories.recall(words, limit=settings.found + len(shown))
    return [m for m in hits if m.id not in shown][: settings.found]


async def for_turn(memories: Memories, words: str | None, settings: RecallSettings) -> list[Memory]:
    """Every memory a turn's instructions carry, the found ones first."""
    return [*await found(memories, words, settings), *await latest(memories, settings)]
