"""How often each watch has matched, and when last: from the journal."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from nestor.admin.state import AdminState
from nestor.modules.initiative import WatchTriggered


@dataclass(frozen=True, slots=True)
class Triggers:
    counts: Counter[str]
    last: dict[str, datetime]

    @classmethod
    async def of(cls, admin: AdminState) -> "Triggers":
        counts: Counter[str] = Counter()
        last: dict[str, datetime] = {}
        for event in await admin.nestor.journal.history(WatchTriggered):
            counts[event.watch_id] += 1
            last[event.watch_id] = event.at
        return cls(counts, last)
