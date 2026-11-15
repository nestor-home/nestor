"""Tavily through the contract every web search passes, its API mocked in its own format."""

import json

import httpx
import pytest
import respx

from nestor.adapters.tools.tavily.search import TavilySearch
from nestor.modules.web import WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, OTHER_KEY, refusing


class TestTavily(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if (key := request.headers["Authorization"].removeprefix("Bearer ")) != KEY:
                return refusing(key)
            body = json.loads(request.content)
            found = [] if body["query"] == NOTHING else PAGES[: body["max_results"]]
            results = [{"title": p.title, "url": p.url, "content": p.snippet, "score": 0.9} for p in found]
            return httpx.Response(200, json={"query": body["query"], "results": results})

        api.post("https://api.tavily.com/search").mock(side_effect=answer)

    def search(self) -> WebSearch:
        return TavilySearch(KEY)

    def unavailable_search(self) -> WebSearch:
        return TavilySearch(OTHER_KEY)

    def secret(self) -> str:
        return OTHER_KEY
