"""The `web_search` tool over every engine the household plugged: those with a key first, in the configuration's
order, then the free tiers in turn; a search goes on to the next engine when one cannot answer."""

import logging
from collections.abc import Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolOutput, ToolProvider, bounded
from nestor.modules.web.ports import WebSearch
from nestor.modules.web.types import UNTRUSTED, Found

log = logging.getLogger(__name__)

MAX_RESULTS = 10
EXCERPT = 1_500  # characters the agent reads of what an engine quotes of a page: some quote whole tables

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
FREE_TIERS = (
    "Your web search goes through free tiers ({engines}), with no key: a search may be slow, cut short or refused "
    "when they are busy. When a search fails or finds little, say so, and that an API key for one of them, or "
    "another search engine with a key in the configuration, would make it reliable."
)


class WebSearchTools(ToolProvider):
    """`web_search` once, whatever the number of engines; none without an engine."""

    name = "web-search"

    def __init__(self, engines: Sequence[WebSearch]) -> None:
        self._keyed = [e for e in engines if not e.free_tier]
        self._free = [e for e in engines if e.free_tier]
        self._turn = 0  # the free tier the next search starts with

    def tools(self) -> Sequence[Tool]:
        if not (self._keyed or self._free):
            return ()
        return (Tool(spec=SEARCH, run=self._run, risk=Risk.READ, timeout_s=30.0),)

    def notes(self) -> Sequence[str]:
        if self._keyed or not self._free:  # free tiers only back a keyed engine up
            return ()
        return (FREE_TIERS.format(engines=", ".join(e.name for e in self._free)),)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        """From the first engine that answers; `ProviderError`, transient, naming each one, when none does."""
        start = self._turn % len(self._free) if self._free else 0
        self._turn += 1
        failures = []
        for engine in (*self._keyed, *self._free[start:], *self._free[:start]):
            try:
                return (await engine.search(query, limit=limit))[:limit]
            except ProviderError as error:
                log.info("web search: %s could not answer (%s), next one", engine.name, error)
                failures.append(f"{engine.name}: {error}")
        raise ProviderError("web-search", f"no search engine could answer ({'; '.join(failures)})", transient=True)

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
            {"title": f.title, "url": f.url, "excerpt": _excerpt(f.snippet)}
            | ({"published": f.published} if f.published else {})
            for f in found
        ]
        return {"query": query, "pages": pages, "note": UNTRUSTED}


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else f"{text[:EXCERPT].rstrip()}…"
