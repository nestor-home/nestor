"""The contract suite every web search adapter must pass, through the `web_search` tool the agent calls."""

from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext, ToolFailed
from nestor.modules.web import Found, WebSearch

CONTEXT = ToolContext(address=Address("web", "chat"))
# what the engine knows for any query but `NOTHING`, most relevant first
PAGES = (
    Found(title="Majordome — Wikipédia", url="https://fr.wikipedia.org/wiki/Majordome", snippet="Le majordome dirige"),
    Found(title="Nestor (Tintin)", url="https://fr.wikipedia.org/wiki/Nestor_(Tintin)", snippet="Le majordome de"),
    Found(title="Le métier", url="https://example.org/metier", snippet="Ce que fait un majordome"),
)
NOTHING = "xqzv introuvable"  # a query the engine finds nothing for


class WebSearchContract:
    """Mix into a `Test…` class. `search()` is the adapter against an engine that answers `PAGES` (in its own
    format) to any query but `NOTHING`; `unavailable_search()` against one that refuses with an error quoting the key
    `secret()`."""

    def search(self) -> WebSearch:
        raise NotImplementedError

    def unavailable_search(self) -> WebSearch:
        raise NotImplementedError

    def secret(self) -> str:
        raise NotImplementedError

    async def _web_search(self, engine: WebSearch, **arguments: object) -> dict:
        [tool] = engine.tools()
        assert tool.name == "web_search"
        async with engine:
            output = await tool.run(arguments, CONTEXT)
        assert isinstance(output, dict)
        return output

    async def test_pages_come_most_relevant_first_up_to_the_number_asked(self) -> None:
        found = await self._web_search(self.search(), query="majordome", max_results=2)
        assert found["pages"] == [{"title": p.title, "url": p.url, "excerpt": p.snippet} for p in PAGES[:2]]

    async def test_a_query_that_finds_nothing_gives_no_page(self) -> None:
        assert (await self._web_search(self.search(), query=NOTHING))["pages"] == []

    async def test_an_engine_that_refuses_fails_the_tool_without_showing_the_key(self) -> None:
        try:
            await self._web_search(self.unavailable_search(), query="majordome")
        except ToolFailed as failed:
            assert self.secret() not in str(failed)
            return
        raise AssertionError("an engine that refuses must fail the tool")
