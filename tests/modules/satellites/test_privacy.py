"""Camera privacy: a device's camera films whenever someone allowed asks, unless the household set a rule for it,
quiet hours or someone at home. A rule ends what it no longer allows, and presence that cannot tell keeps the
camera off."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from nestor.core import PersonId
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    VIDEO_CAPTURE,
    DeclaredCapability,
    Device,
    Manifest,
    MediaAccess,
    MediaEnd,
    MediaRefused,
    MediaSessionClosed,
    MediaSessions,
    Off,
    Pairing,
    Privacy,
    Purpose,
    QuietHours,
    Viewer,
)
from nestor.testing.home import StaticPresence
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog
from nestor.testing.satellites import SOFTWARE, FilmingRelay, pair_by_code

CAMERA = Manifest(Device("camera-salon", "pi", "salon"), (DeclaredCapability(VIDEO_CAPTURE),), software=SOFTWARE)
OWNER = Viewer(account_id="a-mathis", person=PersonId("mathis"), may=frozenset(Purpose), everywhere=frozenset(Purpose))
NIGHTS = QuietHours(days=(0,), start="22:00", end="07:00")  # Monday night, into Tuesday
MONDAY = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)  # a Monday, at noon in the household's time (UTC)
NO_RULE = Privacy()


@dataclass
class Clock:
    now: datetime = MONDAY

    def __call__(self) -> datetime:
        return self.now


@asynccontextmanager
async def home(
    privacy: Privacy = NO_RULE, *, presence: StaticPresence | None = None
) -> AsyncGenerator[tuple[MediaSessions, Clock, Journal]]:
    journal, clock = Journal(MemoryEventLog()), Clock()
    pairing = Pairing(journal)
    async with pairing:
        await pair_by_code(pairing, CAMERA)
        await pairing.set_access(CAMERA.device.id, MediaAccess(privacy=privacy))
        media = MediaSessions(
            journal, pairing, FilmingRelay(b"jpeg"), MemoryBlobStore(), presence=presence, clock=clock
        )
        yield media, clock, journal


def off(media: MediaSessions) -> Off | None:
    [offer] = media.offers(OWNER)
    return offer.off


async def test_without_a_rule_the_camera_films_whenever_asked() -> None:
    async with home() as (media, clock, _):
        for at in (MONDAY, MONDAY.replace(hour=23), MONDAY.replace(day=17, hour=3)):
            clock.now = at
            assert off(media) is None
            assert (await media.snapshot(CAMERA.device.id, OWNER))[1] == b"jpeg"


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (MONDAY.replace(hour=21, minute=59), None),
        (MONDAY.replace(hour=22), Off.QUIET_HOURS),
        (MONDAY.replace(day=17, hour=6, minute=59), Off.QUIET_HOURS),  # Tuesday morning: the slot began on Monday
        (MONDAY.replace(day=17, hour=7), None),
        (MONDAY.replace(day=17, hour=23), None),  # Tuesday night: the slot only starts on Mondays
    ],
)
async def test_quiet_hours_run_past_midnight_from_the_days_they_start_on(at: datetime, expected: Off | None) -> None:
    async with home(Privacy(quiet=(NIGHTS,))) as (media, clock, _):
        clock.now = at
        assert off(media) is expected


async def test_quiet_hours_refuse_a_picture_and_say_why() -> None:
    async with home(Privacy(quiet=(NIGHTS,))) as (media, clock, _):
        clock.now = MONDAY.replace(hour=23)
        with pytest.raises(MediaRefused) as refused:
            await media.snapshot(CAMERA.device.id, OWNER)
    assert refused.value.off is Off.QUIET_HOURS


@pytest.mark.parametrize(
    ("people", "home_people", "expected"),
    [
        ({"mathis": False, "lea": False}, (), None),  # nobody home
        ({"mathis": True, "lea": False}, (), Off.SOMEONE_HOME),  # anyone
        ({"mathis": False, "lea": None}, (), Off.SOMEONE_HOME),  # cannot tell: never film on a guess
        ({"mathis": True, "lea": False}, ("lea",), None),  # only Léa counts, and she is away
        ({"mathis": False, "lea": True}, ("lea",), Off.SOMEONE_HOME),
    ],
)
async def test_a_camera_off_when_someone_is_home_follows_who_counts(
    people: dict[str, bool | None], home_people: tuple[str, ...], expected: Off | None
) -> None:
    presence = StaticPresence()
    for person, at_home in people.items():
        presence.set(person, home=at_home)
    rule = Privacy(off_when_home=True, home_people=tuple(map(PersonId, home_people)))
    async with home(rule, presence=presence) as (media, _, _):
        assert off(media) is expected


async def test_a_presence_rule_without_presence_keeps_the_camera_off() -> None:
    async with home(Privacy(off_when_home=True)) as (media, _, _):
        assert off(media) is Off.SOMEONE_HOME


async def test_a_rule_that_begins_ends_what_was_being_watched() -> None:
    async with home(Privacy(quiet=(NIGHTS,))) as (media, clock, journal):
        clock.now = MONDAY.replace(hour=21, minute=59)
        await media.open(CAMERA.device.id, Purpose.VIEW, OWNER, {"sdp": "v=0", "type": "offer"})
        clock.now = MONDAY.replace(hour=22)
        await media.check()
        [closed] = await journal.history(MediaSessionClosed)
    assert closed.reason is MediaEnd.PRIVACY


async def test_the_rules_survive_a_restart() -> None:
    rule = Privacy(quiet=(NIGHTS,), off_when_home=True, home_people=(PersonId("lea"),))
    async with home(rule) as (_, _, journal):
        restarted = Pairing(journal)
        async with restarted:
            [satellite] = restarted.satellites()
    assert satellite.access == replace(MediaAccess(), privacy=rule)
