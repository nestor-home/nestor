"""Open-Meteo for the weather (`weather`): forecasts from the national weather services, free for a household, no
key. Places are found by Open-Meteo's own geocoding; the home's place is used when none is asked."""

from nestor.adapters.tools.open_meteo.settings import OpenMeteoSettings, build
from nestor.modules.system.selfmap import Card
from nestor.runtime import Family, Plugin

plugin = Plugin(
    Family.TOOLS,
    "open-meteo",
    OpenMeteoSettings,
    build,
    card=Card(
        summary="The weather and forecast anywhere, from Open-Meteo (weather).", docs="tools#web-weather-and-maps"
    ),
)

__all__ = ["plugin"]
