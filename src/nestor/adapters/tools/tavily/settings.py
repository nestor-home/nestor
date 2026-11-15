"""Configuration of Tavily, and how it is built."""

from nestor.adapters.tools.tavily.search import TavilySearch
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings, RequiredSecret


class TavilySettings(AdapterSettings):
    api_key: RequiredSecret


def build(settings: TavilySettings, name: str, services: Services) -> TavilySearch:
    search = TavilySearch(settings.api_key.get_secret_value())
    search.name = name
    return search
