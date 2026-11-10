"""An active watch as the admin shows it."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import OriginOut, People, PersonRef
from nestor.admin.api.v1.watches.triggers import Triggers
from nestor.modules.initiative import Watch


class WatchOut(BaseModel):
    id: str
    what: str  # in the person's words
    kinds: list[str]  # what it watches ("mail")
    owner: PersonRef | None
    once: bool  # ends at the first match
    created_at: datetime
    until: datetime | None
    origin: OriginOut | None  # None when it was not asked in a conversation
    triggered: int  # how many items matched it so far
    last_triggered_at: datetime | None

    @classmethod
    def of(cls, watch: Watch, people: People, triggers: Triggers) -> "WatchOut":
        origin = watch.created_in
        return cls(
            id=watch.id,
            what=watch.what,
            kinds=list(watch.kinds),
            owner=people.ref(watch.owner),
            once=watch.once,
            created_at=watch.created_at,
            until=watch.until,
            origin=OriginOut.of(origin) if origin else None,
            triggered=triggers.counts[watch.id],
            last_triggered_at=triggers.last.get(watch.id),
        )


class WatchesOut(BaseModel):
    watches: list[WatchOut]  # newest first
    kinds: list[str]  # what the plugged sources can bring; empty: no watch can trigger
