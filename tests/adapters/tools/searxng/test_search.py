"""A SearXNG instance through the contract every web search passes, its API mocked in its own format."""

import httpx
import pytest
import respx

from nestor.adapters.tools.searxng.search import SearxngSearch
from nestor.modules.web import WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, refusing


class TestSearxng(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            assert request.url.params["format"] == "json"
            found = [] if request.url.params["q"] == NOTHING else PAGES  # SearXNG takes no count: all come back
            results = [{"title": p.title, "url": p.url, "content": p.snippet, "engine": "duckduckgo"} for p in found]
            return httpx.Response(200, json={"query": request.url.params["q"], "results": results})

        api.get("http://searxng.test:8080/search").mock(side_effect=answer)
        api.get("http://down.test/search").mock(side_effect=lambda r: refusing(r.headers["Authorization"][7:]))

    def search(self) -> WebSearch:
        return SearxngSearch("http://searxng.test:8080/", language="fr-FR")

    def unavailable_search(self) -> WebSearch:
        return SearxngSearch("http://down.test", token=KEY)

    def secret(self) -> str:
        return KEY
