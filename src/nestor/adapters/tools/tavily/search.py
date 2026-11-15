"""Tavily as the household's web search: a search API made for agents, an API key from tavily.com."""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.modules.web import Found, WebSearch

API = "https://api.tavily.com"


class TavilySearch(WebSearch):
    brand = "tavily"

    def __init__(self, api_key: str) -> None:
        self._api = JsonApi("tavily", API, headers={"Authorization": f"Bearer {api_key}"}, secret=api_key)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        answer = await self._api.post("/search", {"query": query, "max_results": limit})
        return [
            Found(
                title=r.get("title") or r["url"],
                url=r["url"],
                snippet=r.get("content") or "",
                published=r.get("published_date"),
            )
            for r in answer.get("results", [])
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._api.aclose()
