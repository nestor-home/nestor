"""Camera privacy: a device's camera films whenever someone allowed asks, unless the household set a rule for it,
quiet hours or someone at home. A rule ends what it no longer allows, and presence that cannot tell keeps the
camera off."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time

import pytest

from nestor.core import PersonId
from nestor.modules.home import Granularity, Presence, Whereabouts
from nestor.modules.initiative.schedules.types import Day
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
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog
from nestor.testing.satellites import SOFTWARE, FilmingRelay, pair_by_code

CAMERA = Manifest(Device("camera-salon", "pi", "salon"), (DeclaredCapability(VIDEO_CAPTURE),), software=SOFTWARE)
OWNER = Viewer(account_id="a-mathis", person=PersonId("mathis"), may=frozenset(Purpose), everywhere=frozenset(Purpose))
NIGHTS = QuietHours(days=(Day.MON,), start=time(22), end=time(7))  # Monday night, into Tuesday
MONDAY = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)  # a Monday, at noon in the household's time (UTC)
HOUSEHOLD = tuple(map(PersonId, ("mathis", "lea", "jules")))
NO_RULE = Privacy()


def home(**people: bool | None) -> Presence:
    """What Home Assistant sees: those it tracks, home or away (None: unknown); the others it does not track."""
    return Presence(granularity=Granularity.HOME, people={PersonId(p): Whereabouts(home=h) for p, h in people.items()})


@pytest.mark.parametrize("at", [MONDAY, MONDAY.replace(hour=23), MONDAY.replace(day=17, hour=3)])
def test_without_a_rule_the_camera_films_whenever_asked(at: datetime) -> None:
    assert MediaAccess().off(at, None, HOUSEHOLD) is None


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
def test_quiet_hours_run_past_midnight_from_the_days_they_start_on(at: datetime, expected: Off | None) -> None:
    assert MediaAccess(privacy=Privacy(quiet=(NIGHTS,))).off(at, None, HOUSEHOLD) is expected


@pytest.mark.parametrize(
    ("presence", "home_people", "expected"),
    [
        (home(mathis=False, lea=False, jules=False), (), None),  # nobody home
        (home(mathis=True, lea=False, jules=False), (), Off.SOMEONE_HOME),  # anyone of the household
        (home(mathis=False, lea=None, jules=False), (), Off.SOMEONE_HOME),  # cannot tell: never film on a guess
        (home(mathis=False, lea=False), (), Off.SOMEONE_HOME),  # Jules is not tracked: he may be home
        (home(mathis=True, lea=False), ("lea",), None),  # only Léa counts, and she is away
        (home(mathis=False, lea=True), ("lea",), Off.SOMEONE_HOME),
        (home(mathis=False, lea=False, jules=False), ("paul",), None),  # Paul left the household: he no longer counts
        (None, (), Off.SOMEONE_HOME),  # no presence at all
    ],
)
def test_a_camera_off_when_someone_is_home_follows_who_counts(
    presence: Presence | None, home_people: tuple[str, ...], expected: Off | None
) -> None:
    rule = Privacy(off_when_home=True, home_people=tuple(map(PersonId, home_people)))
    assert MediaAccess(privacy=rule).off(MONDAY, presence, HOUSEHOLD) is expected


def test_a_switched_off_camera_says_so_before_any_rule() -> None:
    access = MediaAccess(camera=False, privacy=Privacy(quiet=(NIGHTS,)))
    assert access.off(MONDAY.replace(hour=23), None, HOUSEHOLD) is Off.SWITCHED_OFF


@dataclass
class Clock:
    now: datetime = MONDAY

    def __call__(self) -> datetime:
        return self.now


@asynccontextmanager
async def watching(privacy: Privacy = NO_RULE) -> AsyncGenerator[tuple[MediaSessions, Clock, Journal]]:
    journal, clock = Journal(MemoryEventLog()), Clock()
    pairing = Pairing(journal)
    async with pairing:
        await pair_by_code(pairing, CAMERA)
        await pairing.set_access(CAMERA.device.id, MediaAccess(privacy=privacy))
        relay = FilmingRelay(b"jpeg")
        yield (
            MediaSessions(journal, pairing, relay, MemoryBlobStore(), household=HOUSEHOLD, clock=clock),
            clock,
            journal,
        )


async def test_quiet_hours_refuse_a_picture_and_say_why() -> None:
    async with watching(Privacy(quiet=(NIGHTS,))) as (media, clock, _):
        clock.now = MONDAY.replace(hour=23)
        with pytest.raises(MediaRefused) as refused:
            await media.snapshot(CAMERA.device.id, OWNER)
    assert refused.value.off is Off.QUIET_HOURS


async def test_a_rule_that_begins_ends_what_was_being_watched_and_says_which() -> None:
    async with watching(Privacy(quiet=(NIGHTS,))) as (media, clock, journal):
        clock.now = MONDAY.replace(hour=21, minute=59)
        await media.open(CAMERA.device.id, Purpose.VIEW, OWNER, {"sdp": "v=0", "type": "offer"})
        clock.now = MONDAY.replace(hour=22)
        await media.check()
        [closed] = await journal.history(MediaSessionClosed)
    assert (closed.reason, closed.off) == (MediaEnd.CAMERA_OFF, Off.QUIET_HOURS)


async def test_the_rules_survive_a_restart() -> None:
    rule = Privacy(quiet=(NIGHTS,), off_when_home=True, home_people=(PersonId("lea"),))
    async with watching(rule) as (_, _, journal):
        restarted = Pairing(journal)
        async with restarted:
            [satellite] = restarted.satellites()
    assert satellite.access == replace(MediaAccess(), privacy=rule)
