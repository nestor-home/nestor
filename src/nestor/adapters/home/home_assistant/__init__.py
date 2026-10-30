"""Home Assistant as the household's presence source, over its WebSocket API.

Configuration (family `presence`, kind `home-assistant`):

    url: http://homeassistant.local:8123   # http(s) base, reverse-proxy prefix allowed
    token: ${HA_TOKEN}                    # a long-lived access token
    people: {alice: person.alice}         # household person id → person entity
    rooms: {alice: sensor.alice_phone_area}  # optional room trackers (Bermuda, ESPresense…)
    occupancy_sensors: [binary_sensor.kitchen_motion]  # optional: overrides discovery

Device control is not here: it goes through Home Assistant's MCP server.
"""

from typing import Self

from pydantic import Field, PositiveFloat, SecretStr, field_validator, model_validator

from nestor.adapters.home.home_assistant.client import websocket_url
from nestor.adapters.home.home_assistant.installation import PresenceMapping
from nestor.adapters.home.home_assistant.presence import HomeAssistantPresence
from nestor.core import ContractError, PersonId
from nestor.runtime import AdapterSettings, Family, Plugin, Services

__all__ = ["HomeAssistantPresence", "HomeAssistantSettings", "PresenceMapping", "plugin"]


class HomeAssistantSettings(AdapterSettings):
    url: str
    token: SecretStr
    people: dict[str, str] = Field(default_factory=dict)
    rooms: dict[str, str] = Field(default_factory=dict)
    occupancy_sensors: list[str] | None = None  # `None`: every occupancy, presence or motion sensor with an area
    sync_timeout_s: PositiveFloat = 30.0
    reconnect_min_s: PositiveFloat = 1.0
    reconnect_max_s: PositiveFloat = 60.0

    @field_validator("url")
    @classmethod
    def _http_url(cls, url: str) -> str:
        try:
            websocket_url(url)
        except ContractError as error:
            raise ValueError(str(error)) from None
        return url

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if strangers := sorted(set(self.rooms) - set(self.people)):
            raise ValueError(f"room trackers for people without a person entity: {', '.join(strangers)}")
        if self.reconnect_max_s < self.reconnect_min_s:
            raise ValueError("reconnect_max_s must not be below reconnect_min_s")
        return self


def build(settings: HomeAssistantSettings, name: str, services: Services) -> HomeAssistantPresence:
    mapping = PresenceMapping(
        people={PersonId(person): entity for person, entity in settings.people.items()},
        rooms={PersonId(person): entity for person, entity in settings.rooms.items()},
        occupancy_sensors=None if settings.occupancy_sensors is None else tuple(settings.occupancy_sensors),
    )
    source = HomeAssistantPresence(
        settings.url,
        settings.token.get_secret_value(),
        mapping,
        sync_timeout_s=settings.sync_timeout_s,
        reconnect_min_s=settings.reconnect_min_s,
        reconnect_max_s=settings.reconnect_max_s,
    )
    source.name = name
    return source


plugin = Plugin(Family.PRESENCE, "home-assistant", HomeAssistantSettings, build)
