"""Brave Search through the contract every web search passes, its API mocked in its own format."""

import httpx
import pytest
import respx

from nestor.adapters.tools.brave.search import BraveSearch
from nestor.modules.web import WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, OTHER_KEY, refusing


class TestBrave(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if (key := request.headers["X-Subscription-Token"]) != KEY:
                return refusing(key)
            if request.headers.get("Accept") != "application/json":  # required by Brave's API
                return httpx.Response(406, json={"error": {"message": "Accept must be application/json"}})
            found = [] if request.url.params["q"] == NOTHING else PAGES[: int(request.url.params["count"])]
            results = [  # Brave marks the words found
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
