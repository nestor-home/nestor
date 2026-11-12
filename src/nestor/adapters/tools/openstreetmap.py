"""OpenStreetMap for places and journeys (`find_place`, `route`): Nominatim finds places, OSRM computes routes by
car, bike or on foot. No key. The public servers of the OpenStreetMap community serve a household's use, one search a
second at most; an instance of one's own replaces them by address. No public transport, no traffic: OpenStreetMap
knows neither."""

import asyncio
import time
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from nestor.adapters.common.http import JsonApi
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolOutput, ToolProvider, bounded
from nestor.runtime import Family, Plugin, Services
from nestor.runtime.plugins import AdapterSettings

NOMINATIM = "https://nominatim.openstreetmap.org"
ROUTING = "https://routing.openstreetmap.de"  # the routing behind openstreetmap.org: one server per profile
SEARCH_INTERVAL_S = 1.0  # Nominatim's usage policy
MAX_PLACES = 10
PLACES_KEPT = 256
SNAP_M = 5_000  # past this, OSRM moved a place to a road far away: it lies outside the server's map


class Mode(StrEnum):
    CAR = "car"
    BIKE = "bike"
    FOOT = "foot"


FIND = ToolSpec(
    "find_place",
    "Find places by name, address or kind (a shop, a station, a street): their full address and coordinates.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "e.g. 'boulangerie near Place Bellecour, Lyon'"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_PLACES, "default": 5},
        },
        "required": ["query"],
    },
)
ROUTE = ToolSpec(
    "route",
    "Distance and travel time between two places by car, bike or on foot, from home unless another start is given. "
    "Without traffic, and no public transport.",
    {
        "type": "object",
        "properties": {
            "destination": {"type": "string", "description": "an address or a place's name"},
            "origin": {"type": "string", "description": "where from; leave out for home"},
            "mode": {"type": "string", "enum": [m.value for m in Mode], "default": Mode.CAR.value},
        },
        "required": ["destination"],
    },
)


class OpenStreetMap(ToolProvider):
    brand = "openstreetmap"

    def __init__(
        self,
        *,
        home: str | None = None,
        language: str | None = None,
        nominatim_url: str = NOMINATIM,
        routing_url: str = ROUTING,
    ) -> None:
        self._home, self._language = home, language or "en"
        self._nominatim = JsonApi("nominatim", nominatim_url.rstrip("/"))
        self._routing = JsonApi("osrm", routing_url.rstrip("/"))
        self._paced = asyncio.Lock()
        self._last_search = 0.0
        self._places: dict[str, Mapping[str, Any]] = {}  # journeys' ends found, as Nominatim asks to cache

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=FIND, run=self.find, risk=Risk.READ, timeout_s=20.0),
            Tool(spec=ROUTE, run=self.route, risk=Risk.READ, timeout_s=30.0),
        )

    async def close(self) -> None:
        await self._nominatim.aclose()
        await self._routing.aclose()

    async def find(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolFailed("give what to look for")
        limit = bounded(arguments.get("max_results"), default=5, maximum=MAX_PLACES)
        try:
            found = await self._search(query, limit)
        except ProviderError as error:
            raise ToolFailed(f"places could not be searched: {error}") from None
        return {"query": query, "places": [_place(p) for p in found]}

    async def route(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        destination = str(arguments.get("destination", "")).strip()
        origin = str(arguments.get("origin") or "").strip()
        if not destination:
            raise ToolFailed("give where to go")
        if not origin and not self._home:
            raise ToolFailed("no start given, and the home's address is not set: ask where from")
        try:
            mode = Mode(str(arguments.get("mode") or Mode.CAR))
        except ValueError:
            raise ToolFailed(f"mode is one of {', '.join(Mode)}") from None
        try:
            start = await self._one(origin or str(self._home))
            end = await self._one(destination)
            answer = await self._routing.get(
                f"/routed-{mode}/route/v1/driving/{start['lon']},{start['lat']};{end['lon']},{end['lat']}",
                {"overview": "false", "alternatives": "false", "steps": "false"},
                answers={400},  # OSRM's no route (`NoRoute`, `NoSegment`)
            )
        except ProviderError as error:
            raise ToolFailed(f"the route could not be computed: {error}") from None
        routes = answer.get("routes") or []
        if answer.get("code") != "Ok" or not routes:
            raise ToolFailed(f"no {mode} route was found between these places")
        for place, waypoint in zip((start, end), answer.get("waypoints") or [], strict=False):
            if waypoint.get("distance", 0) > SNAP_M:
                raise ToolFailed(f"no road near {place.get('display_name')} on this routing server's map")
        best = routes[0]
        via = ", ".join(leg["summary"] for leg in best.get("legs", []) if leg.get("summary"))
        return {
            "from": start.get("display_name"),
            "to": end.get("display_name"),
            "mode": mode.value,
            "distance_km": round(best["distance"] / 1000, 1),
            "duration_min": round(best["duration"] / 60),
            **({"via": via} if via else {}),
        }

    async def _one(self, query: str) -> Mapping[str, Any]:
        key = query.casefold()
        if key not in self._places:
            found = await self._search(query, 1)
            if not found:
                raise ToolFailed(f"no place matches {query!r}: try a fuller address")
            if len(self._places) >= PLACES_KEPT:
                del self._places[next(iter(self._places))]  # the oldest
            self._places[key] = found[0]
        return self._places[key]

    async def _search(self, query: str, limit: int) -> list[Mapping[str, Any]]:
        async with self._paced:
            if (wait := self._last_search + SEARCH_INTERVAL_S - time.monotonic()) > 0:
                await asyncio.sleep(wait)
            try:
                return await self._nominatim.get(
                    "/search", {"q": query, "format": "jsonv2", "limit": limit, "accept-language": self._language}
                )
            finally:
                self._last_search = time.monotonic()


def _place(found: Mapping[str, Any]) -> dict[str, object]:
    return {
        "name": found.get("name") or found.get("display_name"),
        "address": found.get("display_name"),
        "kind": found.get("type"),
        "latitude": float(found["lat"]),
        "longitude": float(found["lon"]),
    }


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


plugin = Plugin(Family.TOOLS, "openstreetmap", OpenStreetMapSettings, build)
