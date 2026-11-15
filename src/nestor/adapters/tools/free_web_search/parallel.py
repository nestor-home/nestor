"""Parallel's free tier: its public MCP server's `web_search`, which answers a JSON document of results with
excerpts. A random id per process lets it limit this client, and says nothing of the household."""

import json
import uuid
from collections.abc import Sequence

from nestor.adapters.tools.free_web_search.engine import Engine, excerpt
from nestor.adapters.tools.free_web_search.mcp import McpServer
from nestor.core import ProviderError
from nestor.modules.web import Found

URL = "https://search.parallel.ai/mcp"


class Parallel(Engine):
    name, label = "parallel", "Parallel"

    def __init__(self, url: str = URL) -> None:
        self._server = McpServer("parallel", url, timeout_s=30.0)
        self._session = uuid.uuid4().hex

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        arguments = {"objective": query, "search_queries": [query], "session_id": self._session}
        text = await self._server.call("web_search", arguments)
        try:
            results = json.loads(text).get("results") or []
        except (ValueError, AttributeError):
            raise ProviderError("parallel", "web_search: an answer that is not its JSON", transient=True) from None
        return [
            Found(
                title=r.get("title") or r["url"],
                url=r["url"],
                snippet=excerpt(" ".join(r.get("excerpts") or [])),
                published=r.get("publish_date"),
            )
            for r in results[:limit]
            if r.get("url")
        ]

    async def aclose(self) -> None:
        await self._server.aclose()
