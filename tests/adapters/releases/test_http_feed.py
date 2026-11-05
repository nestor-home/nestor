"""The release feed over HTTPS: what it reads, and what it refuses to take for a feed."""

import json
from typing import Any

import httpx
import pytest

from nestor.adapters.releases import HttpReleaseFeed
from nestor.core import ProviderError

URL = "https://example.org/releases.json"
FEED = {"protocols": ["nestor.satellite/1"], "releases": [
    {"version": "0.8.0", "date": "2026-11-05", "url": "https://x/v0.8.0", "changes": []}]}  # fmt: skip


def feed(handler: httpx.MockTransport) -> HttpReleaseFeed:
    return HttpReleaseFeed(URL, client=httpx.AsyncClient(transport=handler))


async def test_it_reads_the_published_feed() -> None:
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=FEED)

    async with feed(httpx.MockTransport(answer)) as releases:
        latest = (await releases.fetch()).latest
    assert latest is not None and latest.version == "0.8.0" and seen == [URL]


@pytest.mark.parametrize(
    ("response", "transient"),
    [
        (httpx.Response(404), True),
        (httpx.Response(200, text="<html>"), False),
        (httpx.Response(200, content=json.dumps({"x": "y" * 1_000_001}).encode()), False),
    ],
    ids=["not found", "not json", "too large"],
)
async def test_an_unreadable_feed_is_a_provider_error(response: httpx.Response, transient: bool) -> None:
    async with feed(httpx.MockTransport(lambda _: response)) as releases:
        with pytest.raises(ProviderError) as error:
            await releases.fetch()
    assert error.value.transient is transient


async def test_an_unreachable_feed_is_transient() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with feed(httpx.MockTransport(fail)) as releases:
        with pytest.raises(ProviderError) as error:
            await releases.fetch()
    assert error.value.transient


async def test_it_closes_the_client_it_makes(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[httpx.AsyncClient] = []

    class Recorded(httpx.AsyncClient):
        def __init__(self, **options: Any) -> None:
            super().__init__(**options)
            made.append(self)

    monkeypatch.setattr(httpx, "AsyncClient", Recorded)
    async with HttpReleaseFeed(URL):
        assert [client.is_closed for client in made] == [False]
    assert [client.is_closed for client in made] == [True]
