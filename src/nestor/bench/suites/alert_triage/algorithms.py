"""The triage algorithms compared by the suite, both production's `Triage` (its question, its reading of the
answer, its second try), differing only in how many alerts each call judges:

- batch: one call per item, judging every alert of its kind at once (what Nestor runs);
- per-alert: one call per alert of the item's kind.

An item the model cannot sort is unsorted for the alerts of that call, and matches none of them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from nestor.modules.cognition import LanguageModel
from nestor.modules.initiative import Alert, Incoming, Triage


class Algorithm(StrEnum):
    BATCH = "batch"
    PER_ALERT = "per-alert"


@dataclass(frozen=True, slots=True, kw_only=True)
class Decision:
    """What the algorithm made of one item for one alert."""

    alert: str
    matches: bool = False
    unsorted: bool = False  # the model could not be reached or read: nothing rings


async def decide(
    algorithm: Algorithm, model: LanguageModel, alerts: Sequence[Alert], item: Incoming, *, language: str
) -> list[Decision]:
    concerned = [a for a in alerts if item.kind in a.kinds]
    if not concerned:
        return []
    triage = Triage(model, language=language)
    calls = [concerned] if algorithm is Algorithm.BATCH else [[a] for a in concerned]
    answers = [await triage.matches(judged, item) for judged in calls]  # one after the other: in parallel, rate limits
    return [
        Decision(alert=a.id, matches=matches is not None and a.id in matches, unsorted=matches is None)
        for judged, matches in zip(calls, answers, strict=True)
        for a in judged
    ]
