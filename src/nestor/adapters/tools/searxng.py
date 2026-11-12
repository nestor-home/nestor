"""SearXNG as the household's web search: a metasearch engine it hosts itself, no key, nothing sent to a search
company under its name. The instance must allow the JSON format (`search.formats: [html, json]` in its settings)."""

from collections.abc import Sequence

from pydantic import SecretStr

from nestor.adapters.common.http import JsonApi
from nestor.modules.web import Found, WebSearch
from nestor.runtime import Family, Plugin, Services
from nestor.runtime.plugins import AdapterSettings


class SearxngSearch(WebSearch):
    brand = "searxng"

    def __init__(self, url: str, *, token: str | None = None, language: str | None = None) -> None:
        super().__init__(language=language)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        self._api = JsonApi("searxng", url.rstrip("/"), headers=headers, secret=token)

    async def search(self, query: str, *, limit: int, language: str | None) -> Sequence[Found]:
        params: dict[str, str | int | float] = {"q": query, "format": "json"}
        if language:
            params["language"] = language
        answer = await self._api.get("/search", params)
        return [
            Found(
                title=r.get("title") or r["url"],
                url=r["url"],
                snippet=r.get("content") or "",
                published=r.get("publishedDate"),
            )
            for r in answer.get("results", [])[:limit]
            if r.get("url")
        ]

    async def close(self) -> None:
        await self._api.aclose()


class SearxngSettings(AdapterSettings):
    url: str  # the instance, e.g. http://searxng:8080
    token: SecretStr | None = None  # sent as `Authorization: Bearer …`, for an instance behind a proxy that asks


def build(settings: SearxngSettings, name: str, services: Services) -> SearxngSearch:
    token = settings.token.get_secret_value() if settings.token else None
    search = SearxngSearch(settings.url, token=token, language=services.locale)
    search.name = name
    return search


plugin = Plugin(Family.TOOLS, "searxng", SearxngSettings, build)
