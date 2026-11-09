"""Doubles for the home ports, and the presence port's contract suite."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from nestor.core import PersonId, utc_now
from nestor.modules.cognition.tools import Tool, ToolProvider
from nestor.modules.home import Granularity, Home, HomeOverview, Presence, PresenceSource, Resident, Room, Whereabouts


class StaticPresence(PresenceSource):
    """Presence set by the test: `at_home`, `in_room`, `occupied`."""

    name = "static-presence"

    def __init__(self, granularity: Granularity = Granularity.HOME) -> None:
        self._granularity = granularity
        self.people: dict[PersonId, Whereabouts] = {}
        self.occupied: set[str] = set()

    @property
    def granularity(self) -> Granularity:
        return self._granularity

    def presence(self) -> Presence:
        return Presence(
            granularity=self._granularity, people=dict(self.people), occupied_rooms=frozenset(self.occupied)
        )

    def set(
        self, person: str, *, home: bool | None, room: str | None = None, since: datetime | None = None
    ) -> "StaticPresence":
        self.people[PersonId(person)] = Whereabouts(home=home, room=room, since=since)
        return self


class StaticTools(ToolProvider):
    """Tools given by the test."""

    name = "static-tools"

    def __init__(self, tools: Sequence[Tool] = ()) -> None:
        self.given = tuple(tools)

    def tools(self) -> Sequence[Tool]:
        return self.given


class StaticHome(Home):
    """A home set by the test: its presence, its tools, its rooms and residents; `connected` says if it answers."""

    name = "static-home"

    def __init__(
        self,
        presence: StaticPresence | None = None,
        tools: Sequence[Tool] = (),
        *,
        rooms: Sequence[Room] = (),
        residents: Sequence[Resident] = (),
        people: Mapping[str, str] | None = None,
        connected: bool = True,
    ) -> None:
        self._presence, self._tools = presence or StaticPresence(), StaticTools(tools)
        self.rooms, self.residents, self.connected = tuple(rooms), tuple(residents), connected
        self.people = {PersonId(p): e for p, e in (people or {}).items()}

    @property
    def presence(self) -> StaticPresence:
        return self._presence

    @property
    def tools(self) -> StaticTools:
        return self._tools

    def room_of(self, label: str) -> str | None:
        wanted = label.strip().casefold()
        return next((r.id for r in self.rooms if wanted in (r.id.casefold(), r.name.casefold())), None)

    def overview(self) -> HomeOverview:
        return HomeOverview(
            connected=self.connected,
            granularity=self._presence.granularity,
            rooms=self.rooms if self.connected else (),
            residents=self.residents if self.connected else (),
            people=dict(self.people),
        )


class PresenceSourceContract:
    """Behaviour every `PresenceSource` must show. Implement `source()`, already started and settled
    (its live cache filled), and `expected()`: the presence the fake home behind it describes."""

    def source(self) -> PresenceSource:
        raise NotImplementedError

    def expected(self) -> Mapping[PersonId, Whereabouts]:
        raise NotImplementedError

    def test_presence_matches_the_home_at_the_declared_granularity(self) -> None:
        source = self.source()
        presence = source.presence()
        assert presence.granularity is source.granularity
        assert dict(presence.people) == dict(self.expected())
        if not source.granularity.at_least(Granularity.PERSON_ROOM):
            assert all(w.room is None for w in presence.people.values()), "rooms reported beyond the granularity"
        if not source.granularity.at_least(Granularity.OCCUPIED_ROOMS):
            assert not presence.occupied_rooms, "occupied rooms reported beyond the granularity"

    def test_since_when_is_a_moment_of_the_past(self) -> None:
        dated = [w.since for w in self.source().presence().people.values() if w.since is not None]
        assert all(since.tzinfo is not None and since <= utc_now() for since in dated)
