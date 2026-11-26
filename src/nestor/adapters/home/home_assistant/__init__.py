"""Home Assistant as the household's home: its presence over the WebSocket API, its actions through an MCP server:
by default its own (Assist's tools, at `<url>/api/mcp`, with the same token), another one, or none.

Configuration (`home`, kind `home-assistant`):

    url: http://homeassistant.local:8123   # http(s) base, reverse-proxy prefix allowed
    token: ${HOME_ASSISTANT_TOKEN}        # a long-lived access token
    people: {alice: person.alice}         # household person id → person entity
    rooms: {alice: sensor.alice_phone_area}  # optional room trackers (Bermuda, ESPresense…)
    occupancy_sensors: [binary_sensor.kitchen_motion]  # optional: overrides discovery
    sensitive: {domains: [lock], device_classes: [garage, door], names: [porte]}  # confirmed by the person first
    mcp: {url: https://mcp.example/mcp, token: ${HOME_MCP_TOKEN}}  # optional: another server, as under `tools:`;
                                                                   # `false`: presence only, no actions
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator, model_validator

from nestor.adapters.home.home_assistant.client import websocket_url
from nestor.adapters.home.home_assistant.home import HomeAssistant
from nestor.adapters.home.home_assistant.installation import PresenceMapping
from nestor.adapters.home.home_assistant.presence import HomeAssistantPresence
from nestor.adapters.tools.mcp.provider import BearerToken, McpToolProvider
from nestor.adapters.tools.mcp.settings import McpSettings
from nestor.adapters.tools.mcp.settings import build as mcp_provider
from nestor.core import ContractError, PersonId
from nestor.modules.cognition.tools import SensitiveWhen
from nestor.modules.system.selfmap import Card, Need
from nestor.runtime import AdapterSettings, Family, Plugin, RequiredSecret, Services
from nestor.runtime.editing import Suggest

__all__ = ["HomeAssistant", "HomeAssistantPresence", "HomeAssistantSettings", "PresenceMapping", "plugin"]


class SensitiveTargets(BaseModel):
    """What an action of Home Assistant acts on that makes it need the person's go-ahead, whatever the tool: one of
    these values in the call's `domain`, `device_class` or `name`, ignoring case. Lights, heating and media are not."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    domains: tuple[str, ...] = ("lock", "alarm_control_panel")
    device_classes: tuple[str, ...] = ("garage", "gate", "door")
    names: tuple[str, ...] = ("lock", "alarm", "garage", "gate", "door")

    def rule(self) -> SensitiveWhen:
        targets = {"domain": self.domains, "device_class": self.device_classes, "name": self.names}
        return SensitiveWhen(None, {key: values for key, values in targets.items() if values})


class HomeAssistantSettings(AdapterSettings):
    url: str
    token: RequiredSecret
    people: dict[str, str] = Field(  # household person id → person entity
        default_factory=dict, json_schema_extra={"suggest_keys": Suggest.PEOPLE, "suggest_values": Suggest.RESIDENTS}
    )
    rooms: dict[str, str] = Field(  # household person id → room tracker entity
        default_factory=dict, json_schema_extra={"suggest_keys": Suggest.PEOPLE}
    )
    occupancy_sensors: list[str] | None = None  # `None`: every occupancy, presence or motion sensor with an area
    sensitive: SensitiveTargets = SensitiveTargets()
    sync_timeout_s: PositiveFloat = Field(default=30.0, json_schema_extra={"advanced": True})
    reconnect_min_s: PositiveFloat = Field(default=1.0, json_schema_extra={"advanced": True})
    reconnect_max_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})
    tool_timeout_s: PositiveFloat = Field(default=10.0, json_schema_extra={"advanced": True})  # its own server's
    # the server of its actions: unset, Home Assistant's own; another one; `False`, none (presence only)
    mcp: McpSettings | Literal[False] | None = None

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
    return HomeAssistant(name, presence, _actions(settings, name, services))


def _actions(settings: HomeAssistantSettings, name: str, services: Services) -> McpToolProvider | None:
    """The server of the home's actions, the household's sensitive targets applying to whichever it is."""
    rule = settings.sensitive.rule()
    if settings.mcp is False:
        return None
    if settings.mcp is not None:
        return mcp_provider(settings.mcp, name, services, sensitive=[rule])
    return McpToolProvider(
        f"{settings.url.rstrip('/')}/api/mcp",
        name=name,
        auth=BearerToken(settings.token.get_secret_value()),
        timeout_s=settings.tool_timeout_s,
        sensitive=[rule],
        negotiation="legacy",  # Home Assistant's server answers the classic handshake only
    )


plugin = Plugin(
    Family.HOME,
    "home-assistant",
    HomeAssistantSettings,
    build,
    card=Card(
        summary="Connects Home Assistant: who is home and in which room, and the devices it exposes and their state "
        "(lights, heating, appliances such as the dishwasher, locks).",
        docs="home#set-up",
        needs=(Need.SERVER, Need.KEY),
    ),
)
