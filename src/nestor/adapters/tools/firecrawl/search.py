"""The engine: `/v2/search`, which answers the pages found with their description."""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.modules.web import Found, WebSearch

URL = "https://api.firecrawl.dev"


class FirecrawlSearch(WebSearch):
    brand = "firecrawl"

    def __init__(self, url: str = URL, *, api_key: str | None = None, free_tier: bool = False) -> None:
        self.free_tier = free_tier
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._api = JsonApi("firecrawl", url.rstrip("/"), headers=headers, secret=api_key, timeout_s=30.0)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        answer = await self._api.post("/v2/search", {"query": query, "limit": limit})
        return [
            Found(title=r.get("title") or r["url"], url=r["url"], snippet=r.get("description") or "")
            for r in (answer.get("data") or {}).get("web") or []
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._api.aclose()
