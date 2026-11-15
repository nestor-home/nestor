"""Keenable's free tier: its public search endpoint, which asks every app to name itself (`X-Keenable-Title`)."""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.adapters.tools.free_web_search.engine import Engine, excerpt
from nestor.modules.web import Found

URL = "https://api.keenable.ai"


class Keenable(Engine):
    name, label = "keenable", "Keenable"

    def __init__(self, url: str = URL) -> None:
        self._api = JsonApi("keenable", url, headers={"X-Keenable-Title": "nestor"}, timeout_s=30.0)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        answer = await self._api.post("/v1/search/public", {"query": query, "max_results": limit})
        return [
            Found(
                title=r.get("title") or r["url"],
                url=r["url"],
                snippet=excerpt(r.get("snippet") or r.get("description") or ""),
            )
            for r in (answer.get("results") or [])[:limit]
            if r.get("url")
        ]

    async def aclose(self) -> None:
        await self._api.aclose()
