"""What is plugged in: every configured adapter and paired satellite, its brand, version and health."""

from importlib import metadata
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nestor.admin.api.v1.models import AgentOut
from nestor.admin.api.v1.routes.satellites import live_rooms
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import state
from nestor.core import Component, Health
from nestor.core.i18n import Message
from nestor.modules.accounts import Scope
from nestor.modules.connectors import Connector
from nestor.runtime import Plugged

router = APIRouter(tags=["system"])
Reader = Annotated[Caller, Depends(allowed(Scope.SYSTEM_READ))]
DISTRIBUTION = "nestor-home"


class ComponentOut(BaseModel):
    slot: str  # model, executor, channel, presence, tools, inbound, connector, satellite
    name: str  # the configured instance (`telegram`, `triage-model`), or a satellite's device id
    adapter: str  # the plugin's kind (`openai-compatible`), or a satellite's model
    brand: str | None  # the vendor or protocol, as a slug ("openrouter", "homeassistant")
    version: str | None  # the plugin's package version, or the version of the software a satellite runs
    distribution: str | None  # the package it comes from (`nestor-home` for built-ins), or a satellite's software
    capabilities: list[str]
    health: Health | None  # None: it cannot tell (a satellite without a spoken channel to hear it)
    health_detail: str | None  # why it is degraded or unavailable, in the reader's language
    details: dict[str, str]  # what else it says about itself: its model, its speech service, its room


class NestorOut(BaseModel):
    version: str


class SystemOut(BaseModel):
    nestor: NestorOut
    agent: AgentOut
    components: list[ComponentOut]


@router.get("/system")
async def get_system(request: Request, caller: Reader) -> SystemOut:
    nestor = state(request).nestor
    live = live_rooms(state(request))
    words = caller.phrasebook
    satellites = []
    for s in nestor.pairing.satellites():
        offline = live is not None and s.room not in live
        satellites.append(
            ComponentOut(
                slot="satellite",
                name=s.id,
                adapter=s.model,
                brand=s.brand,
                version=s.sdk_version,
                distribution=s.sdk,
                capabilities=sorted(s.capabilities),
                health=None if live is None else Health.UNAVAILABLE if offline else Health.STARTED,
                health_detail=words.text(Message.of("health-satellite-offline", room=s.room)) if offline else None,
                details={"room": s.room},
            )
        )
    return SystemOut(
        nestor=NestorOut(version=metadata.version(DISTRIBUTION)),
        agent=AgentOut.of(nestor),
        components=[_component(p, words) for p in nestor.plugged] + satellites,
    )


def _component(plugged: Plugged, words: Phrasebook) -> ComponentOut:
    built = plugged.component
    component = built if isinstance(built, Component) else None
    brand = built.info.brand if isinstance(built, Connector) else None
    detail = component.health_detail() if component else None
    return ComponentOut(
        slot=plugged.family.value,
        name=plugged.name,
        adapter=plugged.kind,
        brand=brand or (component.brand if component else None),
        version=plugged.origin.version if plugged.origin else None,
        distribution=plugged.origin.name if plugged.origin else None,
        capabilities=sorted(component.capabilities.items) if component else [],
        health=component.health() if component else Health.STARTED,
        health_detail=words.text(detail) if detail else None,
        details=dict(component.details()) if component else {},
    )
