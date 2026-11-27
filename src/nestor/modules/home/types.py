"""Presence values: what is known about each person, and how finely."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from nestor.core import PersonId, utc_now


class Granularity(StrEnum):
    """How much the presence source can tell, from coarse to fine (`at_least` compares)."""

    HOME = "home"  # each person is home or away (Home Assistant `person` entities)
    OCCUPIED_ROOMS = "occupied_rooms"  # also which rooms are occupied, not by whom (presence or motion sensors)
    PERSON_ROOM = "person_room"  # also which room each person is in (room-level tracking tied to a person)

    def at_least(self, other: "Granularity") -> bool:
        order = list(Granularity)
        return order.index(self) >= order.index(other)


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
        if self.granularity.at_least(Granularity.OCCUPIED_ROOMS) and alone:
            return self.occupied_rooms
        return None

    def told(self, rooms: Iterable["Room"]) -> dict[PersonId, str]:
        """Where each person is, as a model is told: `unknown`, `away`, `home`, or `home, in <room>` by its name."""
        names = {room.id: room.name for room in rooms}

        def said(where: Whereabouts) -> str:
            if where.home is None:
                return "unknown"
            if not where.home:
                return "away"
            return f"home, in {names[where.room]}" if where.room in names else "home"

        return {person: said(where) for person, where in self.people.items()}

    def people_in(self, room: str) -> tuple[PersonId, ...]:
        """Who is known to be in this room: only a PERSON_ROOM source places people."""
        return tuple(person for person, whereabouts in self.people.items() if whereabouts.room == room)


@dataclass(frozen=True, slots=True, kw_only=True)
class Device:
    """Something of the home its system shows its assistant, as it names it: what the agent may speak of or act on,
    without its state (read with the home's tools when it matters).

    `kinds`: what it is, in the home system's words (Home Assistant's domains: `light`, `media_player`…). `parts`:
    what else it shows, by name, its own name left out when theirs starts with it (a washing machine's `Phase`,
    `Time remaining`). `sensitive`: acting on it waits for the person's go-ahead. `id`: the home system's, to tell
    two devices of one name apart."""

    id: str
    name: str
    kinds: tuple[str, ...]
    parts: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    sensitive: bool = False


@dataclass(frozen=True, slots=True)
class Room:
    """An area of the home system. `occupied` is `None` when nothing in it tells (no occupancy sensor); `floor`, the
    floor it is on when the home has floors; `devices`, what the home shows its assistant in it."""

    id: str
    name: str
    occupied: bool | None = None
    aliases: tuple[str, ...] = ()
    floor: str | None = None
    devices: tuple[Device, ...] = ()


@dataclass(frozen=True, slots=True)
class Resident:
    """Someone the home system knows (a Home Assistant `person`), to tie to a person of the household."""

    entity: str
    name: str
    home: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class HomeOverview:
    """What the home system can show of itself: whether it answers, how finely it places people, its rooms and what is
    in them, who it knows, how the household is tied to it, and what it could not use. Served from the live view, never
    fetched."""

    connected: bool
    granularity: Granularity
    rooms: tuple[Room, ...] = ()
    residents: tuple[Resident, ...] = ()
    people: Mapping[PersonId, str] = field(default_factory=dict)  # household person → resident entity
    trackers: Mapping[PersonId, str] = field(default_factory=dict)  # household person → room tracker entity
    unplaced_sensors: tuple[str, ...] = ()  # occupancy sensors it ignores: no room in the home system
    devices: tuple[Device, ...] = ()  # what it shows its assistant outside any room (the weather, shared lists)
