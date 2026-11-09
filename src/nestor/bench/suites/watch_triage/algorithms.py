"""The triage algorithms compared by the suite, both production's `Triage` (its question, its reading of the
answer, its second try), differing only in how many watches each call judges:

- batch: one call per item, judging every watch of its kind at once (what Nestor runs);
- per-watch: one call per watch of the item's kind.

An item the model cannot sort is unsorted for the watches of that call, and matches none of them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from nestor.modules.cognition import LanguageModel
from nestor.modules.initiative.watches import Incoming, Triage, Watch


class Algorithm(StrEnum):
    BATCH = "batch"
    PER_WATCH = "per-watch"


@dataclass(frozen=True, slots=True, kw_only=True)
class Decision:
    """What the algorithm made of one item for one watch."""

    watch: str
    matches: bool = False
    urgent: bool = False
    unsorted: bool = False  # the model could not be reached or read: nothing announced


async def decide(
    algorithm: Algorithm, model: LanguageModel, watches: Sequence[Watch], item: Incoming, *, language: str
) -> list[Decision]:
    concerned = [w for w in watches if item.kind in w.kinds]
    if not concerned:
        return []
    triage = Triage(model, language=language)
    calls = [concerned] if algorithm is Algorithm.BATCH else [[w] for w in concerned]
    decisions = []
    for judged in calls:
        verdicts = await triage.verdicts(judged, item)
        for watch in judged:
            verdict = verdicts.get(watch.id) if verdicts is not None else None
            decisions.append(
                Decision(
                    watch=watch.id,
                    matches=verdict is not None,
                    urgent=verdict is not None and verdict.urgent,
                    unsorted=verdicts is None,
                )
            )
    return decisions
