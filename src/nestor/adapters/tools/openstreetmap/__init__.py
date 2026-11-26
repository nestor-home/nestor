"""OpenStreetMap for places and journeys (`find_place`, `route`): Nominatim finds places, OSRM computes routes by
car, bike or on foot. No key. The public servers of the OpenStreetMap community serve a household's use, one search a
second at most; an instance of one's own replaces them by address. No public transport, no traffic: OpenStreetMap
knows neither."""

from nestor.adapters.tools.openstreetmap.settings import OpenStreetMapSettings, build
from nestor.modules.system.selfmap import Card
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "openstreetmap",
    OpenStreetMapSettings,
    build,
    card=Card(
        summary="Finds places with their opening hours and plans journeys by car, bike or on foot, from OpenStreetMap "
        "(find_place, route).",
        docs="tools#pages-places-and-journeys",
    ),
)

__all__ = ["plugin"]
