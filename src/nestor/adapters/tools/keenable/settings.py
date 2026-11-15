"""Configuration of Keenable, and how it is built."""

from pydantic import SecretStr

from nestor.adapters.tools.keenable.search import URL, KeenableSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class KeenableSettings(AdapterSettings):
    api_key: SecretStr | None = None  # without one, Keenable's free tier
    url: str = URL


def build(settings: KeenableSettings, name: str, services: Services) -> KeenableSearch:
    search = KeenableSearch(settings.url, api_key=settings.api_key.get_secret_value() if settings.api_key else None)
    search.name = name
    return search
