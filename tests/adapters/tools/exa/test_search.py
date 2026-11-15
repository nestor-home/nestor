"""Exa through the contract every web search passes, its public MCP server mocked as it answers: free with no key, the
key in the server's address otherwise."""

import httpx
import pytest
import respx

from nestor.adapters.tools.exa.search import ExaSearch
from nestor.modules.web import Found, WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

from ..conftest import KEY, OTHER_KEY, refusing
from ..mcp_answers import called, events


def exa(request: httpx.Request) -> httpx.Response:
    key = request.url.params.get("exaApiKey")
    if key not in (None, KEY):
        return refusing(key)
    tool, arguments = called(request)
    assert tool == "web_search_exa"
    found = [] if arguments["query"] == NOTHING else PAGES[: arguments["numResults"]]
    blocks = [f"Title: {p.title}\nURL: {p.url}\nPublished: N/A\nAuthor: N/A\nHighlights:\n{p.snippet}" for p in found]
    return events("\n---\n".join(blocks) or "No results")


@pytest.fixture(autouse=True)
def _server(api: respx.MockRouter) -> None:
    api.post(url__startswith="https://mcp.exa.ai/mcp").mock(side_effect=exa)


class TestExa(WebSearchContract):
    def search(self) -> WebSearch:
        return ExaSearch()

    def unavailable_search(self) -> WebSearch:
        return ExaSearch(api_key=OTHER_KEY)

    def secret(self) -> str:
        return OTHER_KEY


async def test_with_no_key_it_is_a_free_tier_and_with_one_it_is_not() -> None:
    free, keyed = ExaSearch(), ExaSearch(api_key=KEY)
    assert (free.free_tier, keyed.free_tier) == (True, False)
    async with keyed:
        assert list(await keyed.search("majordome", limit=1)) == [PAGES[0]]


async def test_a_page_s_date_is_kept_and_its_text_whole_across_unicode_line_separators(api: respx.MockRouter) -> None:
    text = "Title: 東京\nURL: https://example.jp/\nPublished: 2026-01-06\nAuthor: N/A\nHighlights:\nline" + chr(0x2028)
    api.post(url__startswith="https://mcp.exa.ai/mcp").mock(side_effect=lambda r: events(text + "same line"))
    async with ExaSearch() as exa_search:
        found = list(await exa_search.search("東京", limit=1))
    assert found == [
        Found(title="東京", url="https://example.jp/", snippet=f"line{chr(0x2028)}same line", published="2026-01-06")
    ]
