"""Brave Search as the household's web search: its own index, an API key from api-search.brave.com."""

from collections.abc import Sequence

from nestor.adapters.common.http import JsonApi
from nestor.adapters.common.text import html_to_text
from nestor.modules.web import Found, WebSearch

API = "https://api.search.brave.com/res/v1"


class BraveSearch(WebSearch):
    brand = "brave"

    def __init__(self, api_key: str, *, language: str | None = None) -> None:
        self._language = language
        self._api = JsonApi("brave", API, headers={"X-Subscription-Token": api_key}, secret=api_key)

    async def search(self, query: str, *, limit: int) -> Sequence[Found]:
        params: dict[str, str | int | float] = {"q": query, "count": limit}
        if self._language:
            params["search_lang"] = self._language.split("-")[0].lower()
        answer = await self._api.get("/web/search", params)
        return [
            Found(
                title=html_to_text(r.get("title", "")),
                url=r["url"],
                snippet=html_to_text(r.get("description", "")),  # Brave marks the words found in <strong>
                published=r.get("page_age") or r.get("age"),
            )
            for r in (answer.get("web") or {}).get("results", [])
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._api.aclose()
