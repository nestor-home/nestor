"""Configuration of Open-Meteo, and how it is built."""

from nestor.adapters.tools.open_meteo.tools import OpenMeteo
from nestor.runtime import Services
from nestor.runtime.plugins import AdapterSettings


class OpenMeteoSettings(AdapterSettings):
    home: str | None = None  # the home's town, for the weather when no place is asked: "Lyon"


def build(settings: OpenMeteoSettings, name: str, services: Services) -> OpenMeteo:
    weather = OpenMeteo(home=settings.home, language=services.locale)
    weather.name = name
    return weather
