"""Double and contract suite for the presence port."""

from collections.abc import Mapping

from nestor.core import PersonId
from nestor.modules.home import Granularity, Presence, PresenceSource, Whereabouts


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

    def set(self, person: str, *, home: bool | None, room: str | None = None) -> "StaticPresence":
        self.people[PersonId(person)] = Whereabouts(home=home, room=room)
        return self


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
        if source.granularity < Granularity.PERSON_ROOM:
            assert all(w.room is None for w in presence.people.values()), "rooms reported beyond the granularity"
        if source.granularity < Granularity.OCCUPIED_ROOMS:
            assert not presence.occupied_rooms, "occupied rooms reported beyond the granularity"
