"""Which memories go into a turn's instructions. Generous rather than precise, as ChatGPT does with its saved
memories: a memory is a short line, the model sorts them out, and missing one costs more than carrying a few
it does not need.

- The household layer carries every memory, the latest first, up to a budget: the same from a turn to the
  next, so the provider's prompt cache keeps it.
- Beyond the budget, the turn layer adds those the person's last messages find among the others.

Measured by the `memory-recall` bench.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple

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


class TurnMemories(NamedTuple):
    shown: list[Memory]  # the household layer's: the latest, up to the budget
    found: list[Memory]  # the turn layer's: what was said finds among the others


async def for_turn(memories: Memories, said: str | None, settings: RecallSettings) -> TurnMemories:
    """The memories a turn's instructions carry. Every memory of the household may matter, not only those
    about whoever speaks ("what does Léa like?"). When every memory is already shown, nothing is searched, so
    no embedding call is waited for."""
    shown = await memories.recent(limit=settings.recent) if settings.strategy is not Strategy.SEARCH else []
    everything_shown = settings.strategy is Strategy.BOTH and len(shown) < settings.recent
    if not said or settings.strategy is Strategy.RECENT or not settings.found or everything_shown:
        return TurnMemories(shown, [])
    found = await memories.recall(said, limit=settings.found, exclude={m.id for m in shown})
    return TurnMemories(shown, found)
