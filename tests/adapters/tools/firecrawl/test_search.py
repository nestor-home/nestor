"""Firecrawl through the contract every web search passes, its API mocked as it answers: free with no key, the key as
a bearer token otherwise, or an instance of one's own."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from nestor.adapters.tools.firecrawl.settings import FirecrawlSettings, build
from nestor.core.i18n import Locale
from nestor.modules.web import WebSearch
from nestor.runtime import Services
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, OTHER_KEY, refusing


def firecrawl(request: httpx.Request) -> httpx.Response:
    if "Authorization" in request.headers and (key := request.headers["Authorization"][7:]) != KEY:
        return refusing(key)
    asked = json.loads(request.content)
    found = [] if asked["query"] == NOTHING else PAGES[: asked["limit"]]
    web = [{"url": p.url, "title": p.title, "description": p.snippet, "position": i + 1} for i, p in enumerate(found)]
    return httpx.Response(200, json={"success": True, "data": {"web": web}})


def firecrawl_of(**settings: object) -> WebSearch:
    return build(
        FirecrawlSettings.model_validate(settings),
        "firecrawl",
        Services(data_dir=Path("."), localizer=EchoLocalizer(), locale=Locale("en")),
    )


class TestFirecrawl(WebSearchContract):
    @pytest.fixture(autouse=True)
    def _api(self, api: respx.MockRouter) -> None:
        api.post("https://api.firecrawl.dev/v2/search").mock(side_effect=firecrawl)

    def search(self) -> WebSearch:
        return firecrawl_of()

    def unavailable_search(self) -> WebSearch:
        return firecrawl_of(api_key=OTHER_KEY)

    def secret(self) -> str:
        return OTHER_KEY


def test_only_firecrawl_s_own_service_with_no_key_is_a_free_tier() -> None:
    assert [
        e.free_tier for e in (firecrawl_of(), firecrawl_of(api_key=KEY), firecrawl_of(url="http://firecrawl:3002"))
    ] == [
        True,
        False,
        False,
    ]
