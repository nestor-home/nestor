"""Where an unprompted message goes: presence, satellites, quiet hours, written requests."""

from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from nestor.core import ContractError, PersonId
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Medium
from nestor.modules.home import Granularity, Presence, Whereabouts
from nestor.modules.household import Person
from nestor.modules.initiative import DeliveryPolicy, Plan, QuietHours
from nestor.testing.channels import InMemoryChannel

TELEGRAM = Address("telegram", "42")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", reach=TELEGRAM)
NOON = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)  # 12:00 in Paris
NIGHT = datetime(2026, 10, 30, 23, 30, tzinfo=UTC)  # 00:30 in Paris


class Satellite(InMemoryChannel):
    medium = Medium.SPOKEN

    def __init__(self, channel_id: str, room: str) -> None:
        super().__init__(channel_id)
        self.room = room


CHANNELS = [Satellite("voice", "salon"), Satellite("voice-bureau", "bureau"), InMemoryChannel("telegram")]
POLICY = DeliveryPolicy(quiet_hours=QuietHours.parse("22:30-07:30"), main_room="salon")


def plan(presence: Presence | None, *, origin: Address | None = None, now: datetime = NOON, **kwargs: bool) -> Plan:
    return POLICY.plan(MATHIS, channels=CHANNELS, presence=presence, origin=origin, now=now, **kwargs)


def at(
    granularity: Granularity, *, home: bool | None, room: str | None = None, occupied: Iterable[str] = ()
) -> Presence:
    return Presence(
        granularity=granularity,
        people={MATHIS.id: Whereabouts(home=home, room=room)},
        occupied_rooms=frozenset(occupied),
    )


def test_in_a_room_with_a_satellite_it_is_said_there_then_written_if_unanswered() -> None:
    result = plan(at(Granularity.PERSON_ROOM, home=True, room="bureau"))
    assert (result.spoken, result.written, result.follow_up) == (Address("voice-bureau", "bureau"), TELEGRAM, True)
    assert result.reason == Message.of("delivery-in-room", person="Mathis", room="bureau")


def test_home_without_room_sensors_uses_the_main_satellite() -> None:
    result = plan(at(Granularity.HOME, home=True))
    assert result.spoken == Address("voice", "salon") and result.written == TELEGRAM
    assert result.reason == Message.of("delivery-home-main-satellite", person="Mathis", room="salon")


def test_alone_at_home_with_occupancy_sensors_the_occupied_room_is_used() -> None:
    assert plan(at(Granularity.OCCUPIED_ROOMS, home=True, occupied={"bureau"})).spoken == Address(
        "voice-bureau", "bureau"
    )


def test_occupied_rooms_without_any_satellite_mean_a_message() -> None:
    result = plan(at(Granularity.OCCUPIED_ROOMS, home=True, occupied={"cuisine"}))
    assert (result.spoken, result.written) == (None, TELEGRAM)


def test_away_means_a_message() -> None:
    result = plan(at(Granularity.HOME, home=False))
    assert (result.spoken, result.written, result.reason) == (
        None,
        TELEGRAM,
        Message.of("delivery-away", person="Mathis"),
    )


def test_unknown_whereabouts_and_no_main_satellite_mean_a_message() -> None:
    policy = DeliveryPolicy()
    result = policy.plan(MATHIS, channels=CHANNELS, presence=at(Granularity.HOME, home=None), origin=None, now=NOON)
    assert (result.spoken, result.written) == (None, TELEGRAM)


def test_quiet_hours_silence_the_voice_unless_urgent() -> None:
    home = at(Granularity.HOME, home=True)
    assert plan(home, now=NIGHT).spoken is None
    assert plan(home, now=NIGHT).written == TELEGRAM
    assert plan(home, now=NIGHT, urgent=True).spoken == Address("voice", "salon")


def test_a_written_request_is_always_written() -> None:
    result = plan(at(Granularity.PERSON_ROOM, home=True, room="salon"), written=True)
    assert (result.spoken, result.written) == (None, TELEGRAM)


def test_without_presence_it_goes_back_to_the_conversation() -> None:
    spoken = plan(None, origin=Address("voice", "salon"))
    written = plan(None, origin=Address("web", "x"))
    assert (spoken.spoken, spoken.written) == (Address("voice", "salon"), TELEGRAM)
    assert (written.spoken, written.written) == (None, TELEGRAM)
    stranger = POLICY.plan(None, channels=CHANNELS, presence=None, origin=Address("web", "x"), now=NOON)
    assert (stranger.spoken, stranger.written) == (None, Address("web", "x"))


@pytest.mark.parametrize(
    ("hours", "inside", "outside"),
    [("22:30-07:30", "23:00", "12:00"), ("13:00-14:00", "13:30", "14:00")],
)
def test_quiet_hours_may_wrap_past_midnight(hours: str, inside: str, outside: str) -> None:
    from datetime import time

    quiet = QuietHours.parse(hours)
    assert quiet.contains(time.fromisoformat(inside)) and not quiet.contains(time.fromisoformat(outside))


def test_malformed_quiet_hours_are_refused() -> None:
    with pytest.raises(ContractError, match="HH:MM-HH:MM"):
        QuietHours.parse("tard")


def test_one_voice_channel_may_serve_several_rooms() -> None:
    class Gateway(InMemoryChannel):
        medium = Medium.SPOKEN

        @property
        def rooms(self) -> frozenset[str]:
            return frozenset({"cuisine", "bureau"})

    presence = at(Granularity.PERSON_ROOM, home=True, room="cuisine")
    result = POLICY.plan(MATHIS, channels=[Gateway("voice")], presence=presence, origin=None, now=NOON)
    assert result.spoken == Address("voice", "cuisine")


def test_a_main_satellite_nobody_is_connected_to_means_a_message() -> None:
    class Offline(InMemoryChannel):
        medium = Medium.SPOKEN

        @property
        def rooms(self) -> frozenset[str]:
            return frozenset()

    result = POLICY.plan(
        MATHIS, channels=[Offline("voice")], presence=at(Granularity.HOME, home=True), origin=None, now=NOON
    )
    assert (result.spoken, result.written) == (None, TELEGRAM)
