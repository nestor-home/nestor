"""Presence values: what is known about each person, and how finely."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum

from nestor.core import PersonId, utc_now


class Granularity(IntEnum):
    """How much the presence source can tell, from coarse to fine."""

    HOME = 1  # each person is home or away (Home Assistant `person` entities)
    OCCUPIED_ROOMS = 2  # also which rooms are occupied, not by whom (presence or motion sensors per area)
    PERSON_ROOM = 3  # also which room each person is in (room-level tracking tied to a person)


@dataclass(frozen=True, slots=True)
class Whereabouts:
    """One person's presence. `home` is `None` when unknown (no tracker for them)."""

    home: bool | None = None
    room: str | None = None  # area id, only from a PERSON_ROOM source
    # when these whereabouts started, when the source knows; not part of what they are (equality ignores it)
    since: datetime | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Presence:
    granularity: Granularity
    people: Mapping[PersonId, Whereabouts] = field(default_factory=dict)
    occupied_rooms: frozenset[str] = frozenset()
    at: datetime = field(default_factory=utc_now)

    def of(self, person: PersonId) -> Whereabouts:
        return self.people.get(person, Whereabouts())

    def rooms_where(self, person: PersonId) -> frozenset[str] | None:
        """Rooms the person may be in: exact with PERSON_ROOM, the occupied rooms when they are the only one
        home, `None` when the source cannot tell (then any room with a satellite is a guess)."""
        whereabouts = self.of(person)
        if whereabouts.home is False:
            return frozenset()
        if whereabouts.room is not None:
            return frozenset({whereabouts.room})
        alone = whereabouts.home and all(w.home is not True for p, w in self.people.items() if p != person)
        if self.granularity >= Granularity.OCCUPIED_ROOMS and alone:
            return self.occupied_rooms
        return None
