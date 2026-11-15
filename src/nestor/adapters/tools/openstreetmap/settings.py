"""Configuration of OpenStreetMap, and how it is built."""

from nestor.adapters.tools.openstreetmap.tools import NOMINATIM, ROUTING, OpenStreetMap
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class OpenStreetMapSettings(AdapterSettings):
    home: str | None = None  # the home's address, where journeys start when no start is asked
    nominatim_url: str = NOMINATIM
    routing_url: str = ROUTING  # serves `/routed-car`, `/routed-bike` and `/routed-foot`


def build(settings: OpenStreetMapSettings, name: str, services: Services) -> OpenStreetMap:
    maps = OpenStreetMap(
        home=settings.home,
        language=services.locale,
        nominatim_url=settings.nominatim_url,
        routing_url=settings.routing_url,
    )
    maps.name = name
    return maps
