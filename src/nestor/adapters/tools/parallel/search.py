"""The engine: `web_search`, which answers a JSON document of results with excerpts."""

import json
import uuid
from collections.abc import Sequence

from nestor.adapters.tools.public_mcp import PublicMcpServer
from nestor.core import ProviderError
from nestor.modules.web import Found, WebSearch

URL = "https://search.parallel.ai/mcp"


class ParallelSearch(WebSearch):
    brand = "parallel"

    def __init__(self, url: str = URL, *, api_key: str | None = None) -> None:
        self.free_tier = api_key is None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._server = PublicMcpServer("parallel", url, headers=headers, secret=api_key, timeout_s=30.0)
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
                snippet=" ".join(r.get("excerpts") or []),
                published=r.get("publish_date"),
            )
            for r in results
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._server.aclose()
