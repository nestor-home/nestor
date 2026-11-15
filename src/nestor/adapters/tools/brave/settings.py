"""Configuration of Brave Search, and how it is built."""

from nestor.adapters.tools.brave.search import BraveSearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings, RequiredSecret


class BraveSettings(AdapterSettings):
    api_key: RequiredSecret


def build(settings: BraveSettings, name: str, services: Services) -> BraveSearch:
    search = BraveSearch(settings.api_key.get_secret_value(), language=services.locale)
    search.name = name
    return search
