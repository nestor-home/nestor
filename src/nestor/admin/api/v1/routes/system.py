"""What is plugged in: every configured adapter and paired satellite, its brand, version and health."""

from importlib import metadata
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nestor.admin.api.v1.routes.satellites import live_rooms
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.core import Component, Health
from nestor.modules.accounts import Scope
from nestor.modules.connectors import Connector
from nestor.runtime import Plugged

router = APIRouter(tags=["system"])
Reader = Annotated[Caller, Depends(allowed(Scope.SYSTEM_READ))]
DISTRIBUTION = "nestor-home"


class ComponentOut(BaseModel):
    family: str  # model, executor, channel, presence, tools, inbound, connector, satellite
    kind: str  # the plugin's kind (`openai-compatible`), or a satellite's model
    name: str  # the configured instance (`telegram`, `triage-model`), or a satellite's device id
    brand: str | None  # the vendor or protocol, as a slug ("openrouter", "homeassistant")
    version: str | None  # the plugin's package version, or the software a satellite declared
    distribution: str | None  # the package it comes from; `nestor-home` for the built-in ones
    capabilities: list[str]
    health: Health | None  # None: it cannot tell (a satellite without a spoken channel to hear it)
    details: dict[str, str]  # what else it says about itself: its model, its speech service, its room


class SystemOut(BaseModel):
    version: str  # of Nestor itself
    components: list[ComponentOut]


@router.get("/system")
async def get_system(request: Request, caller: Reader) -> SystemOut:
    nestor = state(request).nestor
    live = live_rooms(state(request))
    satellites = [
        ComponentOut(
            family="satellite",
            kind=s.model,
            name=s.id,
            brand=s.brand,
            version=s.sdk,
            distribution=None,
            capabilities=sorted(s.capabilities),
            health=None if live is None else Health.STARTED if s.room in live else Health.UNAVAILABLE,
            details={"room": s.room},
        )
        for s in nestor.pairing.satellites()
    ]
    return SystemOut(
        version=metadata.version(DISTRIBUTION),
        components=[_component(p) for p in nestor.plugged] + satellites,
    )


def _component(plugged: Plugged) -> ComponentOut:
    built = plugged.component
    component = built if isinstance(built, Component) else None
    brand = built.info.brand if isinstance(built, Connector) else None
    return ComponentOut(
        family=plugged.family.value,
        kind=plugged.kind,
        name=plugged.name,
        brand=brand or (component.brand if component else None),
        version=plugged.origin.version if plugged.origin else None,
        distribution=plugged.origin.name if plugged.origin else None,
        capabilities=sorted(component.capabilities.items) if component else [],
        health=component.health() if component else Health.STARTED,
        details=dict(component.details()) if component else {},
    )
