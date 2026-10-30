"""Presence: what the home knows, and which rooms a person may be in."""

from collections.abc import Iterable
from datetime import timedelta

import pytest

from nestor.core import PersonId, utc_now
from nestor.modules.home import Granularity, Presence, Whereabouts
from nestor.testing.home import PresenceSourceContract, StaticPresence

MATHIS, MATHILDE = PersonId("mathis"), PersonId("mathilde")


class TestStaticPresence(PresenceSourceContract):
    def source(self) -> StaticPresence:
        return StaticPresence().set("mathis", home=True, since=utc_now()).set("mathilde", home=False)

    def expected(self) -> dict[PersonId, Whereabouts]:
        return {MATHIS: Whereabouts(home=True), MATHILDE: Whereabouts(home=False)}


def test_the_contract_rejects_rooms_beyond_the_granularity() -> None:
    class Overclaiming(TestStaticPresence):
        def source(self) -> StaticPresence:
            return StaticPresence().set("mathis", home=True, room="salon")

        def expected(self) -> dict[PersonId, Whereabouts]:
            return {MATHIS: Whereabouts(home=True, room="salon")}

    try:
        Overclaiming().test_presence_matches_the_home_at_the_declared_granularity()
    except AssertionError as error:
        assert "beyond the granularity" in str(error)
    else:
        raise AssertionError("the contract accepted rooms from a home-only source")


def test_the_contract_rejects_whereabouts_dated_in_the_future() -> None:
    class Prophetic(TestStaticPresence):
        def source(self) -> StaticPresence:
            return StaticPresence().set("mathis", home=True, since=utc_now() + timedelta(days=1))

    with pytest.raises(AssertionError):
        Prophetic().test_since_when_is_a_moment_of_the_past()


def test_since_when_is_not_what_whereabouts_are() -> None:
    assert Whereabouts(home=True, since=utc_now()) == Whereabouts(home=True)


def presence(granularity: Granularity, people: dict[PersonId, Whereabouts], occupied: Iterable[str] = ()) -> Presence:
    return Presence(granularity=granularity, people=people, occupied_rooms=frozenset(occupied))


def test_someone_away_is_in_no_room() -> None:
    p = presence(Granularity.PERSON_ROOM, {MATHIS: Whereabouts(home=False)})
    assert p.rooms_where(MATHIS) == frozenset()


def test_room_level_tracking_gives_the_room() -> None:
    p = presence(Granularity.PERSON_ROOM, {MATHIS: Whereabouts(home=True, room="bureau")}, {"salon", "bureau"})
    assert p.rooms_where(MATHIS) == {"bureau"}


def test_occupied_rooms_point_to_the_person_only_when_they_are_alone_home() -> None:
    alone = presence(
        Granularity.OCCUPIED_ROOMS, {MATHIS: Whereabouts(home=True), MATHILDE: Whereabouts(home=False)}, {"salon"}
    )
    together = presence(
        Granularity.OCCUPIED_ROOMS, {MATHIS: Whereabouts(home=True), MATHILDE: Whereabouts(home=True)}, {"salon"}
    )
    assert alone.rooms_where(MATHIS) == {"salon"}
    assert together.rooms_where(MATHIS) is None


def test_home_only_presence_cannot_tell_the_room() -> None:
    p = presence(Granularity.HOME, {MATHIS: Whereabouts(home=True)})
    assert p.rooms_where(MATHIS) is None
    assert p.of(PersonId("stranger")) == Whereabouts()
