"""Configuration of Exa, and how it is built."""

from pydantic import SecretStr

from nestor.adapters.tools.exa.search import URL, ExaSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class ExaSettings(AdapterSettings):
    api_key: SecretStr | None = None  # without one, Exa's free tier
    url: str = URL


def build(settings: ExaSettings, name: str, services: Services) -> ExaSearch:
    search = ExaSearch(settings.url, api_key=settings.api_key.get_secret_value() if settings.api_key else None)
    search.name = name
    return search
