"""Open-Meteo for the weather (`weather`): forecasts from the national weather services, free for a household, no
key. Places are found by Open-Meteo's own geocoding; the home's place is used when none is asked."""

from collections.abc import Mapping, Sequence
from typing import Any

from nestor.adapters.common.http import JsonApi
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, ToolProvider
from nestor.modules.cognition.tools.types import ToolOutput
from nestor.runtime import Family, Plugin, Services
from nestor.runtime.plugins import AdapterSettings

FORECAST = "https://api.open-meteo.com/v1"
GEOCODING = "https://geocoding-api.open-meteo.com/v1"
MAX_DAYS = 16
HOURS = 24  # how far `next_hours` looks
HOURS_STEP = 3

CURRENT = "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
HOURLY = "temperature_2m,precipitation_probability,precipitation,weather_code"
DAILY = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
    "wind_speed_10m_max,sunrise,sunset"
)
SKY = {  # WMO weather interpretation codes, as Open-Meteo documents them
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    85: "light snow showers",
    86: "snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}

WEATHER = ToolSpec(
    "weather",
    "The weather now, over the next hours and for the coming days, at home or at a place. Temperatures in °C, wind "
    "in km/h, precipitation in mm.",
    {
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "a town or place; leave out for home"},
            "days": {"type": "integer", "minimum": 1, "maximum": MAX_DAYS, "default": 3},
        },
    },
)


class OpenMeteo(ToolProvider):
    brand = "open-meteo"

    def __init__(self, *, home: str | None = None, language: str | None = None) -> None:
        self._home, self._language = home, (language or "en").split("-")[0].lower()
        self._forecast = JsonApi("open-meteo", FORECAST)
        self._geocoding = JsonApi("open-meteo", GEOCODING)
        self._places: dict[str, Mapping[str, Any]] = {}

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=WEATHER, run=self.weather, risk=Risk.READ, timeout_s=20.0),)

    async def close(self) -> None:
        await self._forecast.aclose()
        await self._geocoding.aclose()

    async def weather(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        name = str(arguments.get("place") or "").strip() or self._home
        if not name:
            raise ToolFailed("no place given, and the home's place is not set: ask where")
        days = arguments.get("days")
        days = days if isinstance(days, int) and not isinstance(days, bool) and 0 < days <= MAX_DAYS else 3
        try:
            place = await self._place(name)
            forecast = await self._forecast.get(
                "/forecast",
                {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "timezone": "auto",
                    "forecast_days": days,
                    "current": CURRENT,
                    "hourly": HOURLY,
                    "daily": DAILY,
                },
            )
        except ProviderError as error:
            raise ToolFailed(f"the weather could not be read: {error}") from None
        return {"place": _named(place), **_forecast(forecast)}

    async def _place(self, name: str) -> Mapping[str, Any]:
        key = name.casefold()
        if key not in self._places:
            found = await self._geocoding.get(
                "/search", {"name": name, "count": 1, "language": self._language, "format": "json"}
            )
            if not found.get("results"):
                raise ToolFailed(f"no place called {name!r} was found: try a town's name")
            self._places[key] = found["results"][0]
        return self._places[key]


def _named(place: Mapping[str, Any]) -> str:
    return ", ".join(str(place[k]) for k in ("name", "admin1", "country") if place.get(k))


def _forecast(answer: Mapping[str, Any]) -> dict[str, object]:
    current = answer.get("current") or {}
    hourly = answer.get("hourly") or {}
    daily = answer.get("daily") or {}
    now = current.get("time", "")
    times = hourly.get("time", [])
    first = next((i for i, t in enumerate(times) if t >= now[:13]), 0)
    return {
        "now": {
            "time": now,
            "sky": SKY.get(current.get("weather_code"), "unknown"),
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "wind": current.get("wind_speed_10m"),
        },
        "next_hours": [
            {
                "time": times[i],
                "sky": SKY.get(_at(hourly, "weather_code", i), "unknown"),
                "temperature": _at(hourly, "temperature_2m", i),
                "precipitation_chance_percent": _at(hourly, "precipitation_probability", i),
                "precipitation": _at(hourly, "precipitation", i),
            }
            for i in range(first, min(first + HOURS, len(times)), HOURS_STEP)
        ],
        "days": [
            {
                "date": date,
                "sky": SKY.get(_at(daily, "weather_code", i), "unknown"),
                "min": _at(daily, "temperature_2m_min", i),
                "max": _at(daily, "temperature_2m_max", i),
                "precipitation": _at(daily, "precipitation_sum", i),
                "precipitation_chance_percent": _at(daily, "precipitation_probability_max", i),
                "wind_max": _at(daily, "wind_speed_10m_max", i),
                "sunrise": _at(daily, "sunrise", i),
                "sunset": _at(daily, "sunset", i),
            }
            for i, date in enumerate(daily.get("time", []))
        ],
    }


def _at(series: Mapping[str, Any], key: str, index: int) -> object:
    values = series.get(key) or []
    return values[index] if index < len(values) else None


class OpenMeteoSettings(AdapterSettings):
    home: str | None = None  # the home's town, for the weather when no place is asked: "Lyon"


def build(settings: OpenMeteoSettings, name: str, services: Services) -> OpenMeteo:
    weather = OpenMeteo(home=settings.home, language=services.locale)
    weather.name = name
    return weather


plugin = Plugin(Family.TOOLS, "open-meteo", OpenMeteoSettings, build)
