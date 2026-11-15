"""OpenStreetMap for places and journeys (`find_place`, `route`): Nominatim finds places, OSRM computes routes by
car, bike or on foot. No key. The public servers of the OpenStreetMap community serve a household's use, one search a
second at most; an instance of one's own replaces them by address. No public transport, no traffic: OpenStreetMap
knows neither."""

from nestor.adapters.tools.openstreetmap.settings import OpenStreetMapSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "openstreetmap", OpenStreetMapSettings, build)

__all__ = ["plugin"]
