"""Configuration of a SearXNG instance, and how it is built."""

from pydantic import SecretStr

from nestor.adapters.tools.searxng.search import SearxngSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class SearxngSettings(AdapterSettings):
    url: str  # the instance, e.g. http://searxng:8080
    token: SecretStr | None = None  # sent as `Authorization: Bearer …`, for an instance behind a proxy that asks


def build(settings: SearxngSettings, name: str, services: Services) -> SearxngSearch:
    token = settings.token.get_secret_value() if settings.token else None
    search = SearxngSearch(settings.url, token=token, language=services.locale)
    search.name = name
    return search
