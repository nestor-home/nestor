"""Keenable through the contract every web search passes, its API mocked as it answers: its public search with no
key, its keyed search with one; either way the app names itself."""

import json

import httpx
import pytest
import respx

from nestor.adapters.tools.keenable.search import KeenableSearch
from nestor.modules.web import WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, OTHER_KEY, refusing


def keenable(request: httpx.Request) -> httpx.Response:
    if request.headers.get("X-Keenable-Title") != "nestor":  # it asks each app to name itself
        return httpx.Response(400, json={"error": "X-Keenable-Title is required"})
    keyed = request.url.path == "/v1/search"
    if keyed and (key := request.headers.get("Authorization", "")[7:]) != KEY:
        return refusing(key)
    asked = json.loads(request.content)
    found = [] if asked["query"] == NOTHING else PAGES[: asked["max_results"]]
    results = [{"title": p.title, "url": p.url, "description": "", "snippet": p.snippet} for p in found]
    return httpx.Response(200, json={"query": asked["query"], "mode": "pro", "results": results})


class TestKeenable(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _api(self, api: respx.MockRouter) -> None:
        api.post(url__regex=r"https://api\.keenable\.ai/v1/search(/public)?$").mock(side_effect=keenable)

    def search(self) -> WebSearch:
        return KeenableSearch()

    def unavailable_search(self) -> WebSearch:
        return KeenableSearch(api_key=OTHER_KEY)

    def secret(self) -> str:
        return OTHER_KEY


async def test_with_a_key_it_searches_with_it_and_is_not_a_free_tier(api: respx.MockRouter) -> None:
    api.post(url__regex=r"https://api\.keenable\.ai/v1/search(/public)?$").mock(side_effect=keenable)
    keyed = KeenableSearch(api_key=KEY)
    assert (KeenableSearch().free_tier, keyed.free_tier) == (True, False)
    async with keyed:
        assert list(await keyed.search("majordome", limit=1)) == [PAGES[0]]
