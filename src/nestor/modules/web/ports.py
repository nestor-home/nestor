"""The web search port: an engine that answers a query with pages, offered to the agent as `web_search`."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolOutput, ToolProvider, bounded
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
    """Contract: `search` returns pages, the most relevant first, none for a query nothing matches (the tool keeps the
    first `limit`, which the engine may also ask for); a provider that cannot answer raises `ProviderError`. One
    engine per household: the tool's name is unique."""

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> Sequence[Found]: ...

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=SEARCH, run=self._run, risk=Risk.READ, timeout_s=20.0),)

    async def _run(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolFailed("give what to search for")
        limit = bounded(arguments.get("max_results"), default=5, maximum=MAX_RESULTS)
        try:
            found = await self.search(query, limit=limit)
        except ProviderError as error:
            raise ToolFailed(f"the web search failed: {error}") from None
        pages = [
            {"title": f.title, "url": f.url, "excerpt": f.snippet} | ({"published": f.published} if f.published else {})
            for f in found[:limit]
        ]
        return {"query": query, "pages": pages, "note": UNTRUSTED}
