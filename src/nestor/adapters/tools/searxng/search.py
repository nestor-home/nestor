"""SearXNG as the household's web search: a metasearch engine it hosts itself, no key, nothing sent to a search"""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.modules.web import Found, WebSearch


class SearxngSearch(WebSearch):
    brand = "searxng"

    def __init__(self, url: str, *, token: str | None = None, language: str | None = None) -> None:
        self._language = language
        headers = {"Authorization": f"Bearer {token}"} if token else None
        self._api = JsonApi("searxng", url.rstrip("/"), headers=headers, secret=token)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        params: dict[str, str | int | float] = {"q": query, "format": "json"}
        if self._language:
            params["language"] = self._language
        answer = await self._api.get("/search", params)
        return [
            Found(
                title=r.get("title") or r["url"],
                url=r["url"],
                snippet=r.get("content") or "",
                published=r.get("publishedDate"),
            )
            for r in answer.get("results", [])
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._api.aclose()
