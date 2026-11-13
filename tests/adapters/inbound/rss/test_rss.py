"""News feeds as watch items: RSS and Atom read alike, an unchanged feed answers 304, an entry comes once across
restarts, what was there before is not new, and a broken or private feed yields nothing. Feeds are served by a fake
server through mocked HTTP; names resolve through a fake DNS."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from nestor.adapters.common.web import FEEDS, PublicWeb
from nestor.adapters.inbound.polled import Watched
from nestor.adapters.inbound.rss import FeedSource
from nestor.modules.initiative import Incoming
from nestor.testing.initiative import InboundEventSourceContract

from ...dns import resolve
from .feeds import FakeFeed

URL = "https://kernel.example/feed"
DNS = {"kernel.example": "93.184.215.14", "nas.home": "192.168.1.20"}


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve(monkeypatch, DNS)


@pytest.fixture
def web() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def feed_source(folder: Path, url: str = URL) -> FeedSource:
    return FeedSource("rss", [Watched("Kernel", url)], PublicWeb(accept=FEEDS), folder, every_s=0.01)


async def taken(source: FeedSource, wait_s: float = 0.1) -> list[Incoming]:
    """What the source yields within `wait_s`."""
    found: list[Incoming] = []

    async def take() -> None:
        async for item in source.items():
            found.append(item)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(take(), wait_s)
    return found


class TestFeedSource(InboundEventSourceContract):
    @pytest.fixture(autouse=True)
    def served(self, web: respx.MockRouter, tmp_path: Path) -> None:
        self.feed, self.state = FakeFeed(), tmp_path / "rss"
        web.get(URL).mock(side_effect=self.feed)

    def source(self) -> FeedSource:
        return feed_source(self.state)

    async def arrive(self, title: str) -> None:
        self.feed.add(title)


@pytest.mark.parametrize("atom", [False, True], ids=["rss-2.0", "atom"])
async def test_a_new_entry_is_an_item_with_its_title_link_summary_and_date(
    web: respx.MockRouter, tmp_path: Path, atom: bool
) -> None:
    feed = FakeFeed(atom)
    feed.add("Linux 6.18")
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        feed.add("Linux 7.0 released")
        (item,) = await taken(source)
    assert (item.kind, item.title, item.sender) == ("feed", "Linux 7.0 released", "Kernel")
    assert item.body == "Les nouveautés\n\nhttps://kernel.example/0"
    assert item.data["published"] == "2026-11-13T08:00:00+00:00"


@pytest.mark.parametrize("dated", [False, True], ids=["etag", "last-modified"])
async def test_an_unchanged_feed_is_asked_with_its_validator_and_answers_304(
    web: respx.MockRouter, tmp_path: Path, dated: bool
) -> None:
    feed = FakeFeed(dated=dated)
    feed.add("Linux 6.18")
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        assert await taken(source) == []
    assert feed.answers[0] == 200 and set(feed.answers[1:]) == {304}
    assert feed.conditional[0] is None and all(feed.conditional[1:])


async def test_what_was_in_the_feed_before_is_not_new_and_a_republished_entry_comes_once(
    web: respx.MockRouter, tmp_path: Path
) -> None:
    feed = FakeFeed()
    for title in ("Linux 6.16", "Linux 6.17"):
        feed.add(title)
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        feed.add("Linux 7.0")
        assert [i.title for i in await taken(source)] == ["Linux 7.0"]
    feed.entries.reverse()  # the feed reorders: its ETag changes, its entries do not
    async with feed_source(tmp_path / "rss") as restarted:
        assert await taken(restarted) == []


async def test_an_entry_without_a_title_or_a_readable_date_is_named_by_its_summary(
    web: respx.MockRouter, tmp_path: Path
) -> None:
    feed = FakeFeed()
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        feed.broken = (
            b"<rss><channel><item><guid>1</guid><pubDate>someday</pubDate>"
            b"<description>Linux 7.0 is out, with a new scheduler.</description></item></channel></rss>"
        )
        (item,) = await taken(source)
    assert item.title == "Linux 7.0 is out, with a new scheduler."
    assert item.data["published"] is None


@pytest.mark.parametrize(
    "broken",
    [
        b"<rss><channel><item><title>cut short",
        b"<html><body>Not a feed</body></html>",
        b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        b"<rss><channel><item><title>&b;</title></item></channel></rss>",
    ],
    ids=["malformed", "not-a-feed", "entities"],
)
async def test_a_feed_that_cannot_be_read_yields_nothing_and_is_read_again_once_mended(
    web: respx.MockRouter, tmp_path: Path, broken: bytes
) -> None:
    feed = FakeFeed()
    feed.add("Linux 6.18")
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        feed.broken = broken
        assert await taken(source) == []
        feed.broken = None
        feed.add("Linux 7.0")
        assert [i.title for i in await taken(source)] == ["Linux 7.0"]


@pytest.mark.parametrize("url", ["http://nas.home/feed.xml", "http://127.0.0.1:8470/feed", "file:///etc/passwd"])
async def test_a_feed_off_the_public_internet_is_never_fetched(web: respx.MockRouter, tmp_path: Path, url: str) -> None:
    inside = web.route().respond(200, content=FakeFeed().body())
    async with feed_source(tmp_path / "rss", url) as source:
        assert await taken(source) == []
    assert not inside.called


async def test_an_entry_still_listed_by_a_long_feed_is_never_new_twice(web: respx.MockRouter, tmp_path: Path) -> None:
    feed = FakeFeed()
    for number in range(700):
        feed.add(f"Release {number}")
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        feed.add("Linux 7.0")
        assert [i.title for i in await taken(source)] == ["Linux 7.0"]
        feed.add("Linux 7.1")
        assert [i.title for i in await taken(source)] == ["Linux 7.1"]


async def test_an_entry_whose_handling_was_cut_short_comes_again_after_a_restart(
    web: respx.MockRouter, tmp_path: Path
) -> None:
    feed = FakeFeed()
    web.get(URL).mock(side_effect=feed)
    async with feed_source(tmp_path / "rss") as source:
        feed.add("Linux 7.0")
        feed.add("Linux 7.1")
        items = source.items()
        assert (await anext(items)).title == "Linux 7.0"
        await items.aclose()  # stopped while the entry was being triaged: the next one was never asked for
    async with feed_source(tmp_path / "rss") as restarted:
        assert [i.title for i in await taken(restarted)] == ["Linux 7.0", "Linux 7.1"]


async def test_a_feed_that_redirects_to_a_malformed_address_or_hangs_is_tried_again(
    web: respx.MockRouter, tmp_path: Path
) -> None:
    hung = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        await hung.wait()
        return httpx.Response(500)

    feed = FakeFeed()
    route = web.get(URL).mock(side_effect=hang)
    source = FeedSource(
        "rss", [Watched("Kernel", URL)], PublicWeb(accept=FEEDS), tmp_path / "rss", every_s=0.01, deadline_s=0.05
    )
    async with asyncio.timeout(1):
        await source.start()  # the first read hangs: the start does not
    try:
        route.mock(return_value=httpx.Response(302, headers={"Location": "http://kernel.example:99999/feed"}))
        assert await taken(source) == []
        route.mock(side_effect=feed)
        assert await taken(source) == [], "the first read that answers takes the feed as it is"
        feed.add("Linux 7.0")
        assert [i.title for i in await taken(source)] == ["Linux 7.0"]
    finally:
        await source.close()
