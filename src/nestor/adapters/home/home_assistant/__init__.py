"""Home Assistant as the household's home: its presence over the WebSocket API, its actions through its MCP server
(Assist's tools, at `<url>/api/mcp`), with one address and one token.

Configuration (`home`, kind `home-assistant`):

    url: http://homeassistant.local:8123   # http(s) base, reverse-proxy prefix allowed
    token: ${HOME_ASSISTANT_TOKEN}        # a long-lived access token
    people: {alice: person.alice}         # household person id → person entity
    rooms: {alice: sensor.alice_phone_area}  # optional room trackers (Bermuda, ESPresense…)
    occupancy_sensors: [binary_sensor.kitchen_motion]  # optional: overrides discovery
    sensitive: {domains: [lock], device_classes: [garage, door], names: [porte]}  # confirmed by the person first
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator, model_validator

from nestor.adapters.home.home_assistant.client import websocket_url
from nestor.adapters.home.home_assistant.home import HomeAssistant
from nestor.adapters.home.home_assistant.installation import PresenceMapping
from nestor.adapters.home.home_assistant.presence import HomeAssistantPresence
from nestor.adapters.tools.mcp import BearerToken, McpToolProvider
from nestor.core import ContractError, PersonId
from nestor.modules.cognition.tools import SensitiveWhen
from nestor.runtime import AdapterSettings, Family, Plugin, RequiredSecret, Services

__all__ = ["HomeAssistant", "HomeAssistantPresence", "HomeAssistantSettings", "PresenceMapping", "plugin"]


class SensitiveTargets(BaseModel):
    """What an action of Home Assistant acts on that makes it need the person's go-ahead, whatever the tool: one of
    these values in the call's `domain`, `device_class` or `name`, ignoring case. Lights, heating and media are not."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    domains: list[str] = Field(default_factory=lambda: ["lock", "alarm_control_panel"])
    device_classes: list[str] = Field(default_factory=lambda: ["garage", "gate", "door"])
    names: list[str] = Field(default_factory=lambda: ["lock", "alarm", "garage", "gate", "door"])

    def rule(self) -> SensitiveWhen:
        targets = {"domain": self.domains, "device_class": self.device_classes, "name": self.names}
        return SensitiveWhen(None, {key: tuple(values) for key, values in targets.items() if values})


class HomeAssistantSettings(AdapterSettings):
    url: str
    token: RequiredSecret
    people: dict[str, str] = Field(  # household person id → person entity
        default_factory=dict, json_schema_extra={"suggest_keys": "people", "suggest_values": "residents"}
    )
    rooms: dict[str, str] = Field(  # household person id → room tracker entity
        default_factory=dict, json_schema_extra={"suggest_keys": "people"}
    )
    occupancy_sensors: list[str] | None = None  # `None`: every occupancy, presence or motion sensor with an area
    sensitive: SensitiveTargets = SensitiveTargets()
    sync_timeout_s: PositiveFloat = Field(default=30.0, json_schema_extra={"advanced": True})
    reconnect_min_s: PositiveFloat = Field(default=1.0, json_schema_extra={"advanced": True})
    reconnect_max_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})
    tool_timeout_s: PositiveFloat = Field(default=10.0, json_schema_extra={"advanced": True})

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


def build(settings: HomeAssistantSettings, name: str, services: Services) -> HomeAssistant:
    token = settings.token.get_secret_value()
    presence = HomeAssistantPresence(
        settings.url,
        token,
        PresenceMapping(
            people={PersonId(person): entity for person, entity in settings.people.items()},
            rooms={PersonId(person): entity for person, entity in settings.rooms.items()},
            occupancy_sensors=None if settings.occupancy_sensors is None else tuple(settings.occupancy_sensors),
        ),
        sync_timeout_s=settings.sync_timeout_s,
        reconnect_min_s=settings.reconnect_min_s,
        reconnect_max_s=settings.reconnect_max_s,
    )
    presence.name = f"{name}-presence"
    tools = McpToolProvider(
        f"{settings.url.rstrip('/')}/api/mcp",
        name=name,
        auth=BearerToken(token),
        timeout_s=settings.tool_timeout_s,
        sensitive=[settings.sensitive.rule()],
        negotiation="legacy",  # Home Assistant's server answers the classic handshake only
    )
    return HomeAssistant(name, presence, tools)


plugin = Plugin(Family.HOME, "home-assistant", HomeAssistantSettings, build)
