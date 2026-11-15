"""One `web_search` over every engine the household plugged: those with a key first, then the free tiers in turn, each
search going on to the next engine when one cannot answer; the agent is told when it searches on free tiers only."""

from collections.abc import Sequence

import pytest

from nestor.core import ProviderError
from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.web import Found, WebSearch, WebSearchTools
from nestor.modules.web.service import EXCERPT

PAGE = Found(title="Majordome", url="https://example.org/majordome", snippet="Le majordome dirige la maison.")
BUSY = ProviderError("engine", "HTTP 429: slow down", transient=True)
REFUSED = ProviderError("engine", "HTTP 401: invalid key", transient=False)


class Engine(WebSearch):
    def __init__(self, name: str, asked: list[str], *, free: bool = False, fails: ProviderError | None = None) -> None:
        self.name, self.free_tier, self._asked, self._fails = name, free, asked, fails

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        self._asked.append(self.name)
        if self._fails:
            raise self._fails
        return [PAGE] * 3


async def test_engines_with_a_key_come_first_then_each_search_starts_with_the_next_free_tier() -> None:
    asked: list[str] = []
    free = ["exa", "parallel", "keenable"]
    tools = WebSearchTools(
        [Engine(n, asked, free=True) for n in free[:2]]
        + [Engine("brave", asked)]
        + [Engine("keenable", asked, free=True)]
    )
    await tools.search("majordome", limit=1)
    assert asked == ["brave"]

    asked.clear()
    tools = WebSearchTools([Engine(n, asked, free=True) for n in free])
    for _ in range(4):
        await tools.search("majordome", limit=1)
    start = free.index(asked[0])
    assert asked == [free[(start + i) % 3] for i in range(4)]


@pytest.mark.parametrize("failure", [BUSY, REFUSED], ids=["busy", "refused key"])
async def test_an_engine_that_cannot_answer_hands_over_to_the_next(failure: ProviderError) -> None:
    asked: list[str] = []
    tools = WebSearchTools([Engine("brave", asked, fails=failure), Engine("exa", asked, free=True)])
    assert list(await tools.search("majordome", limit=2)) == [PAGE, PAGE]
    assert asked == ["brave", "exa"]


async def test_when_no_engine_answers_the_tool_fails_naming_each_one() -> None:
    tools = WebSearchTools([Engine("brave", [], fails=REFUSED), Engine("exa", [], free=True, fails=BUSY)])
    [tool] = tools.tools()
    with pytest.raises(ToolFailed) as failed:
        await tool.run({"query": "majordome"}, ToolContext(address=Address("web", "chat")))
    assert "brave: " in str(failed.value) and "exa: " in str(failed.value)


async def test_the_agent_reads_the_pages_asked_for_with_their_excerpt_cut_short() -> None:
    long = Found(title="Marées", url="https://example.org/marees", snippet="| 09h54 | 10,05 m |\n" * 200)

    class Tables(Engine):
        async def search(self, query: str, *, limit: int) -> Sequence[Found]:
            return [long, PAGE, PAGE]

    [tool] = WebSearchTools([Tables("exa", [], free=True)]).tools()
    found = await tool.run({"query": "marée", "max_results": 2}, ToolContext(address=Address("web", "chat")))
    assert isinstance(found, dict)
    pages = found["pages"]
    assert isinstance(pages, list)
    first, second = pages
    assert len(first["excerpt"]) <= EXCERPT + 1 and first["excerpt"].endswith("…") and "\n" not in first["excerpt"]
    assert second == {"title": PAGE.title, "url": PAGE.url, "excerpt": PAGE.snippet}


def test_the_agent_is_told_when_it_searches_on_free_tiers_only() -> None:
    [note] = WebSearchTools([Engine("exa", [], free=True), Engine("keenable", [], free=True)]).notes()
    assert "free tiers (exa, keenable)" in note and "API key" in note
    assert WebSearchTools([Engine("brave", []), Engine("exa", [], free=True)]).notes() == (), "free tiers back it up"
    assert WebSearchTools([]).tools() == () and WebSearchTools([]).notes() == ()
