"""Configuration of Parallel, and how it is built."""

from pydantic import SecretStr

from nestor.adapters.tools.parallel.search import URL, ParallelSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class ParallelSettings(AdapterSettings):
    api_key: SecretStr | None = None  # without one, Parallel's free tier
    url: str = URL


def build(settings: ParallelSettings, name: str, services: Services) -> ParallelSearch:
    search = ParallelSearch(settings.url, api_key=settings.api_key.get_secret_value() if settings.api_key else None)
    search.name = name
    return search
