"""Each free tier, mocked in the format it answers (recorded from the real ones), through the contract every web
search passes: Exa and Parallel over their public MCP servers, Firecrawl and Keenable over their public APIs."""

import json
from collections.abc import Callable, Iterator

import httpx
import pytest
import respx

from nestor.adapters.tools.free_web_search.exa import Exa
from nestor.adapters.tools.free_web_search.firecrawl import Firecrawl
from nestor.adapters.tools.free_web_search.keenable import Keenable
from nestor.adapters.tools.free_web_search.parallel import Parallel
from nestor.adapters.tools.free_web_search.search import FreeWebSearch
from nestor.modules.web import Found, WebSearch
from nestor.testing.web import NOTHING, PAGES, WebSearchContract

type Answer = Callable[[httpx.Request], httpx.Response]
type Tier = type[Exa] | type[Parallel] | type[Firecrawl] | type[Keenable]


@pytest.fixture(autouse=True)
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def turned_away(request: httpx.Request) -> httpx.Response:
    return httpx.Response(403, json={"error": "your IP address looks suspicious"})


def rpc(request: httpx.Request) -> tuple[str, dict]:
    call = json.loads(request.content)
    assert call["method"] == "tools/call"
    assert "text/event-stream" in request.headers["Accept"], "MCP servers may answer in events"
    return call["params"]["name"], call["params"]["arguments"]


def exa(request: httpx.Request) -> httpx.Response:
    tool, arguments = rpc(request)
    assert tool == "web_search_exa"
    found = [] if arguments["query"] == NOTHING else PAGES[: arguments["numResults"]]
    blocks = [f"Title: {p.title}\nURL: {p.url}\nPublished: N/A\nAuthor: N/A\nHighlights:\n{p.snippet}" for p in found]
    envelope = {"result": {"content": [{"type": "text", "text": "\n---\n".join(blocks) or "No results"}]}}
    return httpx.Response(
        200, text=f"event: message\ndata: {json.dumps(envelope)}\n\n", headers={"Content-Type": "text/event-stream"}
    )


def parallel(request: httpx.Request) -> httpx.Response:
    tool, arguments = rpc(request)
    assert tool == "web_search" and arguments["session_id"], "a random id per process, nothing of the household"
    found = [] if arguments["objective"] == NOTHING else PAGES  # it takes no count: all come back
    results = [{"url": p.url, "title": p.title, "publish_date": None, "excerpts": [p.snippet]} for p in found]
    text = json.dumps({"search_id": "search_1", "results": results}, indent=2)
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": text}]}})


def firecrawl(request: httpx.Request) -> httpx.Response:
    asked = json.loads(request.content)
    assert "Authorization" not in request.headers
    found = [] if asked["query"] == NOTHING else PAGES[: asked["limit"]]
    web = [{"url": p.url, "title": p.title, "description": p.snippet, "position": i + 1} for i, p in enumerate(found)]
    return httpx.Response(200, json={"success": True, "data": {"web": web}})


def keenable(request: httpx.Request) -> httpx.Response:
    if request.headers.get("X-Keenable-Title") != "nestor":  # its public endpoints ask each app to name itself
        return httpx.Response(400, json={"error": "X-Keenable-Title is required"})
    asked = json.loads(request.content)
    found = [] if asked["query"] == NOTHING else PAGES[: asked["max_results"]]
    results = [{"title": p.title, "url": p.url, "description": "", "snippet": p.snippet} for p in found]
    return httpx.Response(200, json={"query": asked["query"], "mode": "pro", "results": results})


# each tier: where it is reached (what its class takes), the address it is called at, and how it answers
TIERS: dict[Tier, tuple[str, str, Answer]] = {
    Exa: ("https://mcp.exa.ai/mcp", "", exa),
    Parallel: ("https://search.parallel.ai/mcp", "", parallel),
    Firecrawl: ("https://api.firecrawl.dev", "/v2/search", firecrawl),
    Keenable: ("https://api.keenable.ai", "/v1/search/public", keenable),
}


def down(url: str) -> str:
    return url.replace("://", "://down.")


class FreeTier(WebSearchContract):
    tier: Tier

    @pytest.fixture(autouse=True)
    def _engine(self, api: respx.MockRouter) -> None:
        url, path, answer = TIERS[self.tier]
        api.post(url + path).mock(side_effect=answer)
        api.post(down(url) + path).mock(side_effect=turned_away)

    def search(self) -> WebSearch:
        return FreeWebSearch([self.tier()])

    def unavailable_search(self) -> WebSearch:
        return FreeWebSearch([self.tier(down(TIERS[self.tier][0]))])

    def secret(self) -> str:
        return "a free tier has no key"


class TestExa(FreeTier):
    tier = Exa


class TestParallel(FreeTier):
    tier = Parallel


class TestFirecrawl(FreeTier):
    tier = Firecrawl


class TestKeenable(FreeTier):
    tier = Keenable


async def test_a_free_tier_s_limit_told_as_a_tool_error_goes_on_to_the_next(api: respx.MockRouter) -> None:
    limited = {
        "result": {"content": [{"type": "text", "text": "Rate limit exceeded, try again later"}], "isError": True}
    }
    api.post("https://mcp.exa.ai/mcp").respond(200, text=f"data: {json.dumps(limited)}\n\n")
    api.post("https://api.keenable.ai/v1/search/public").mock(side_effect=keenable)
    async with FreeWebSearch([Exa(), Keenable()]) as search:  # one of the two searches starts with Exa
        assert [list(await search.search("majordome", limit=1)) for _ in range(2)] == [[PAGES[0]]] * 2


async def test_page_text_with_unicode_line_separators_stays_whole(api: respx.MockRouter) -> None:
    text = (
        "Title: 東京\nURL: https://example.jp/\nPublished: 2026-01-06\nAuthor: N/A\nHighlights:\nline"
        + chr(0x2028)
        + "same line"
    )
    envelope = {"result": {"content": [{"type": "text", "text": text}]}}
    api.post("https://mcp.exa.ai/mcp").respond(
        200, content=f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n".encode()
    )
    exa_tier = Exa()
    assert list(await exa_tier.search("東京", limit=1)) == [
        Found(title="東京", url="https://example.jp/", snippet="line same line", published="2026-01-06")
    ]
    await exa_tier.aclose()
