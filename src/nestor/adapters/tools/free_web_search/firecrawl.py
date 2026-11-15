"""Firecrawl's free tier: its search API called without a key."""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.adapters.tools.free_web_search.engine import Engine, excerpt
from nestor.modules.web import Found

URL = "https://api.firecrawl.dev"


class Firecrawl(Engine):
    name, label = "firecrawl", "Firecrawl"

    def __init__(self, url: str = URL) -> None:
        self._api = JsonApi("firecrawl", url, timeout_s=30.0)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        answer = await self._api.post("/v2/search", {"query": query, "limit": limit})
        return [
            Found(title=r.get("title") or r["url"], url=r["url"], snippet=excerpt(r.get("description") or ""))
            for r in ((answer.get("data") or {}).get("web") or [])[:limit]
            if r.get("url")
        ]

    async def aclose(self) -> None:
        await self._api.aclose()
