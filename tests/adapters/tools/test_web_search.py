"""Web search engines: the contract suite against each one's API, mocked in its own format, plus what each sends
that its API requires."""

import json
from collections.abc import Iterator

import httpx
import pytest
import respx

from nestor.adapters.tools.brave import BraveSearch
from nestor.adapters.tools.searxng import SearxngSearch
from nestor.adapters.tools.tavily import TavilySearch
from nestor.modules.web import WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

KEY = "key-0123456789abcdef"
OTHER_KEY = "revoked-key-fedcba9876543210"


@pytest.fixture(autouse=True)
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def refusing(request: httpx.Request) -> httpx.Response:
    key = request.headers.get("X-Subscription-Token") or request.headers.get("Authorization", "").removeprefix(
        "Bearer "
    )
    return httpx.Response(401, json={"error": {"message": f"invalid key {key}"}})


class TestBrave(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.headers["X-Subscription-Token"] != KEY:
                return refusing(request)
            if request.headers.get("Accept") != "application/json":  # required by Brave's API
                return httpx.Response(406, json={"error": {"message": "Accept must be application/json"}})
            found = [] if request.url.params["q"] == NOTHING else PAGES[: int(request.url.params["count"])]
            results = [
                # Brave marks the words found
                {
                    "title": p.title,
                    "url": p.url,
                    "description": p.snippet.replace("majordome", "<strong>majordome</strong>"),
                }
                for p in found
            ]
            return httpx.Response(200, json={"web": {"results": results}} if results else {"query": {}})

        api.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=answer)

    def search(self) -> WebSearch:
        return BraveSearch(KEY, language="fr-FR")

    def unavailable_search(self) -> WebSearch:
        return BraveSearch(OTHER_KEY)

    def secret(self) -> str:
        return OTHER_KEY


class TestSearxng(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            assert request.url.params["format"] == "json"
            found = [] if request.url.params["q"] == NOTHING else PAGES  # SearXNG takes no count: all come back
            results = [{"title": p.title, "url": p.url, "content": p.snippet, "engine": "duckduckgo"} for p in found]
            return httpx.Response(200, json={"query": request.url.params["q"], "results": results})

        api.get("http://searxng.test:8080/search").mock(side_effect=answer)
        api.get("http://down.test/search").mock(side_effect=refusing)

    def search(self) -> WebSearch:
        return SearxngSearch("http://searxng.test:8080/", language="fr-FR")

    def unavailable_search(self) -> WebSearch:
        return SearxngSearch("http://down.test", token=KEY)

    def secret(self) -> str:
        return KEY


class TestTavily(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] != f"Bearer {KEY}":
                return refusing(request)
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
