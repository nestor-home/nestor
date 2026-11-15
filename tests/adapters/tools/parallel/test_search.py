"""Parallel through the contract every web search passes, its public MCP server mocked as it answers: free with no
key, the key as a bearer token otherwise."""

import json

import httpx
import pytest
import respx

from nestor.adapters.tools.parallel.search import ParallelSearch
from nestor.modules.web import WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, OTHER_KEY, refusing
from ..mcp_answers import answered, called


def parallel(request: httpx.Request) -> httpx.Response:
    if "Authorization" in request.headers and (key := request.headers["Authorization"][7:]) != KEY:
        return refusing(key)
    tool, arguments = called(request)
    assert tool == "web_search" and arguments["session_id"], "a random id per process, nothing of the household"
    found = [] if arguments["objective"] == NOTHING else PAGES  # it takes no count: all come back
    results = [{"url": p.url, "title": p.title, "publish_date": None, "excerpts": [p.snippet]} for p in found]
    return answered(json.dumps({"search_id": "search_1", "results": results}, indent=2))


class TestParallel(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _server(self, api: respx.MockRouter) -> None:
        api.post("https://search.parallel.ai/mcp").mock(side_effect=parallel)

    def search(self) -> WebSearch:
        return ParallelSearch()

    def unavailable_search(self) -> WebSearch:
        return ParallelSearch(api_key=OTHER_KEY)

    def secret(self) -> str:
        return OTHER_KEY


def test_with_no_key_it_is_a_free_tier_and_with_one_it_is_not() -> None:
    assert (ParallelSearch().free_tier, ParallelSearch(api_key=KEY).free_tier) == (True, False)
