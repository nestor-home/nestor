"""Configuration of Firecrawl, and how it is built."""

from pydantic import SecretStr

from nestor.adapters.tools.firecrawl.search import URL, FirecrawlSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class FirecrawlSettings(AdapterSettings):
    api_key: SecretStr | None = None  # without one, Firecrawl's free tier
    url: str = URL  # or an instance of one's own


def build(settings: FirecrawlSettings, name: str, services: Services) -> FirecrawlSearch:
    key = settings.api_key.get_secret_value() if settings.api_key else None
    search = FirecrawlSearch(settings.url, api_key=key, free_tier=key is None and settings.url == URL)
    search.name = name
    return search
