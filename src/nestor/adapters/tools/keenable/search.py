"""The engine: `/v1/search/public` with no key, `/v1/search` with one; both answer results with a snippet."""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.modules.web import Found, WebSearch

URL = "https://api.keenable.ai"


class KeenableSearch(WebSearch):
    brand = "keenable"

    def __init__(self, url: str = URL, *, api_key: str | None = None) -> None:
        self.free_tier = api_key is None
        headers = {"X-Keenable-Title": "nestor", **({"Authorization": f"Bearer {api_key}"} if api_key else {})}
        self._api = JsonApi("keenable", url.rstrip("/"), headers=headers, secret=api_key, timeout_s=30.0)
        self._path = "/v1/search" if api_key else "/v1/search/public"

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        answer = await self._api.post(self._path, {"query": query, "max_results": limit})
        return [
            Found(
                title=r.get("title") or r["url"],
                url=r["url"],
                snippet=r.get("snippet") or r.get("description") or "",
            )
            for r in answer.get("results") or []
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._api.aclose()
