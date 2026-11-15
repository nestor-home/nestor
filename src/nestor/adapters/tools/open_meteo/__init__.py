"""Open-Meteo for the weather (`weather`): forecasts from the national weather services, free for a household, no
key. Places are found by Open-Meteo's own geocoding; the home's place is used when none is asked."""

from nestor.adapters.tools.open_meteo.settings import OpenMeteoSettings, build
from nestor.runtime import Family, Plugin

plugin = Plugin(Family.TOOLS, "open-meteo", OpenMeteoSettings, build)

__all__ = ["plugin"]
