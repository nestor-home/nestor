"""Newer releases of Nestor, read from its release feed: what changed and what they speak."""

import asyncio
from datetime import date, datetime
from typing import Any

import pytest

from nestor.core import ContractError
from nestor.modules.system import (
    Change,
    ChangeKind,
    Release,
    Releases,
    Updates,
    version_key,
)
from nestor.testing.system import StaticReleaseFeed

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


def test_versions_compare_as_numbers() -> None:
    assert version_key("0.10.0") > version_key("0.9.3")
    with pytest.raises(ContractError):
        version_key("latest")


def _updates(feed: StaticReleaseFeed, **options: Any) -> Updates:
    return Updates(feed, "0.7.0", **options)


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
