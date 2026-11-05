"""Newer releases of Nestor, read from its release feed: what changed and what they speak."""

import asyncio
from datetime import date, datetime
from typing import Any

import pytest

from nestor.core import ContractError
from nestor.modules.journal import Journal
from nestor.modules.system import (
    Change,
    ChangeKind,
    Installation,
    InstallKind,
    Release,
    Releases,
    UpdateFailed,
    UpdateRequested,
    Updates,
)
from nestor.testing.journal import MemoryEventLog
from nestor.testing.system import FakeInstaller, StaticReleaseFeed

NOW = datetime.fromisoformat("2026-11-04T09:00:00+00:00")
FEED = {
    "protocols": ["nestor.satellite/1"],
    "releases": [
        {"version": "0.7.0", "date": "2026-11-03", "url": "https://x/v0.7.0",
         "changes": [{"kind": "feature", "text": "episodes"}]},
        {"version": "0.10.0", "date": "2026-11-20", "url": "https://x/v0.10.0",
         "changes": [{"kind": "breaking", "text": "models by role"}, {"kind": "fix", "text": "a fix"}]},
        {"version": "0.8.0", "date": "2026-11-05", "url": "https://x/v0.8.0", "changes": []},
    ],
}  # fmt: skip


def test_releases_are_ordered_by_version_and_those_after_the_running_one_are_newer() -> None:
    releases = Releases.from_json(FEED)
    assert [r.version for r in releases.releases] == ["0.10.0", "0.8.0", "0.7.0"]
    assert [r.version for r in releases.newer_than("0.7.0")] == ["0.10.0", "0.8.0"]
    assert releases.newer_than("0.10.0") == ()
    latest = releases.latest
    assert latest == Release(
        "0.10.0",
        date(2026, 11, 20),
        "https://x/v0.10.0",
        (Change(ChangeKind.BREAKING, "models by role"), Change(ChangeKind.FIX, "a fix")),
    )
    assert latest.breaking and not releases.releases[1].breaking
    assert releases.protocols == {"nestor.satellite/1"}


@pytest.mark.parametrize(
    "feed",
    [
        [],
        {"releases": []},
        {"protocols": "nestor.satellite/1", "releases": []},
        {"protocols": [], "releases": [{"version": "0.8.0"}]},
        {"protocols": [], "releases": [{"version": "0.8.0-rc1", "date": "2026-11-05", "url": "u", "changes": []}]},
        {"protocols": [], "releases": [{"version": "0.8.0", "date": "soon", "url": "u", "changes": []}]},
        {"protocols": [], "releases": [{"version": "0.8.0", "date": "2026-11-05", "url": "u",
                                        "changes": [{"kind": "chore", "text": "x"}]}]},
        {"protocols": [], "releases": [{"version": "0.8.0", "date": "2026-11-05", "url": "u",
                                        "changes": [{"kind": "fix", "text": 3}]}]},
        {"protocols": [], "releases": [{"version": 8, "date": "2026-11-05", "url": "u", "changes": []}]},
    ],
    ids=["not an object", "no protocols", "protocols as text", "incomplete release", "pre-release",
         "bad date", "unknown kind", "text not text", "version not text"],
)  # fmt: skip
def test_a_feed_off_its_shape_is_refused(feed: object) -> None:
    with pytest.raises(ContractError):
        Releases.from_json(feed)


PIP = Installation(InstallKind.PIP, ("pip install --upgrade nestor-home",))


class Restarts:
    """Who asked for a restart, in order."""

    def __init__(self) -> None:
        self.by: list[str] = []
        self.asked = asyncio.Event()

    async def __call__(self, by: str) -> None:
        self.by.append(by)
        self.asked.set()


def _updates(feed: StaticReleaseFeed, installer: FakeInstaller | None = None, **options: Any) -> Updates:
    return Updates(feed, "0.7.0", Journal(MemoryEventLog()), Restarts(), PIP, installer=installer, **options)


async def test_a_feed_that_cannot_be_read_keeps_the_last_one_read() -> None:
    feed = StaticReleaseFeed()
    updates = _updates(feed, clock=lambda: NOW)
    await updates.check()
    assert (updates.releases, updates.checked_at, updates.newer()) == (None, None, ())
    feed.releases = Releases.from_json(FEED)
    await updates.check()
    assert updates.releases == feed.releases and updates.checked_at == NOW
    feed.releases = None
    await updates.check()
    assert updates.releases is not None and updates.checked_at == NOW


async def test_the_feed_is_read_after_a_pause_then_regularly_until_closed() -> None:
    feed = StaticReleaseFeed(Releases.from_json(FEED))
    async with _updates(feed, first_check_s=0.01, every_s=0.01) as updates:
        assert feed.reads == 0, "not when it starts"
        await asyncio.sleep(0.1)
        assert feed.reads >= 2 and updates.releases is not None
    read = feed.reads
    await asyncio.sleep(0.05)
    assert feed.reads == read


async def _read(installer: FakeInstaller | None) -> tuple[Updates, Journal, Restarts]:
    journal, restarts = Journal(MemoryEventLog()), Restarts()
    feed = StaticReleaseFeed(Releases.from_json(FEED))
    updates = Updates(feed, "0.7.0", journal, restarts, PIP, installer=installer)
    await updates.check()
    return updates, journal, restarts


async def test_only_the_newest_release_is_installed_then_nestor_restarts() -> None:
    installer = FakeInstaller(wait=True)
    updates, journal, restarts = await _read(installer)
    assert [r.version for r in updates.newer()] == ["0.10.0", "0.8.0"]
    for version in ("0.8.0", "0.7.0", "9.9.9"):
        with pytest.raises(ContractError):
            await updates.install(version, by="mathis")
    await updates.install("0.10.0", by="mathis")
    assert updates.installing == "0.10.0"
    with pytest.raises(ContractError):
        await updates.install("0.10.0", by="mathis")
    installer.release.set()
    await asyncio.wait_for(restarts.asked.wait(), 1)
    assert installer.installed == ["0.10.0"] and restarts.by == ["mathis"]
    [asked] = await journal.history(UpdateRequested)
    assert (asked.by, asked.running, asked.target) == ("mathis", "0.7.0", "0.10.0")


class Broken(FakeInstaller):
    """An installer that fails in a way nobody planned (a command that cannot start, a bug)."""

    async def install(self, version: str) -> None:
        raise FileNotFoundError("nestor")


@pytest.mark.parametrize("installer", [FakeInstaller(fails=True), Broken()], ids=["refused", "unplanned error"])
async def test_a_release_that_does_not_install_leaves_the_running_one_and_says_so(installer: FakeInstaller) -> None:
    updates, journal, restarts = await _read(installer)
    await updates.install("0.10.0", by="mathis")
    async with asyncio.timeout(1):
        while not await journal.history(UpdateFailed):
            await asyncio.sleep(0.005)
    assert (updates.installing, updates.failed, restarts.by) == (None, "0.10.0", [])
    [failed] = await journal.history(UpdateFailed)
    assert failed.target == "0.10.0"
    await updates.install("0.10.0", by="mathis")  # it can be tried again
    assert updates.installing == "0.10.0"


async def test_an_instance_without_an_installer_updates_the_way_it_was_installed() -> None:
    updates, _, _ = await _read(None)
    with pytest.raises(ContractError):
        await updates.install("0.10.0", by="mathis")
