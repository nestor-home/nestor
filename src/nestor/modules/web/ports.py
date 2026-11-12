"""The web search port: an engine that answers a query with pages, offered to the agent as `web_search`."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.cognition.tools.types import ToolOutput
from nestor.modules.web.types import UNTRUSTED, Found

MAX_RESULTS = 10

SEARCH = ToolSpec(
    "web_search",
    "Search the web. Returns the title, address and an excerpt of each page found, the most relevant first; "
    f"read a page in full with read_page when one is offered. {UNTRUSTED}",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "what to search for, as you would type it in a search engine"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 5},
        },
        "required": ["query"],
    },
)


class WebSearch(ToolProvider, ABC):
    """Contract: `search` returns at most `limit` pages, the most relevant first, none for a query nothing matches;
    a provider that cannot answer raises `ProviderError`. `language` is the household's (BCP 47), a hint the engine
    may ignore. One engine per household: the tool's name is unique."""

    def __init__(self, *, language: str | None = None) -> None:
        self._language = language

    @abstractmethod
    async def search(self, query: str, *, limit: int, language: str | None) -> Sequence[Found]: ...

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=SEARCH, run=self._run, risk=Risk.READ, timeout_s=20.0),)

    async def _run(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolFailed("give what to search for")
        limit = arguments.get("max_results")
        limit = limit if isinstance(limit, int) and not isinstance(limit, bool) and 0 < limit <= MAX_RESULTS else 5
        try:
            found = await self.search(query, limit=limit, language=self._language)
        except ProviderError as error:
            raise ToolFailed(f"the web search failed: {error}") from None
        pages = [
            {"title": f.title, "url": f.url, "excerpt": f.snippet} | ({"published": f.published} if f.published else {})
            for f in found[:limit]
        ]
        return {"query": query, "pages": pages, "note": UNTRUSTED}
