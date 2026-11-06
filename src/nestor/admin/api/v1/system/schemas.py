"""What is plugged in and its health, the releases since the running version, and restarting."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from nestor import __version__
from nestor.admin.api.v1.agent.schemas import AgentOut
from nestor.admin.api.v1.shared import Input
from nestor.admin.presentation import Phrasebook
from nestor.core import Component, Health, Model, ModelType
from nestor.core.i18n import Message
from nestor.modules.connectors import Connector
from nestor.modules.satellites import Satellite
from nestor.modules.system import ChangeKind, InstallKind, Release
from nestor.runtime import Nestor, Plugged
from nestor.runtime.plugins import Family


class ComponentOut(BaseModel):
    slot: Family | Literal["satellite"]  # a plugin's family, or a paired satellite
    name: str  # the configured instance (`telegram`, `triage-model`), or a satellite's device id
    adapter: str  # the plugin's id (`telegram`, `openai-compatible-language`), or a satellite's model
    model_type: ModelType | None  # what a model serves (None for any other component)
    brand: str | None  # the vendor or protocol, as a slug ("openrouter", "homeassistant")
    version: str | None  # the plugin's package version, or the version of the software a satellite runs
    distribution: str | None  # the package it comes from (`nestor-home` for built-ins), or a satellite's software
    capabilities: list[str]
    health: Health | None  # None: it cannot tell (a satellite without a spoken channel to hear it)
    health_detail: str | None  # why it is degraded or unavailable, in the reader's language
    details: dict[str, str]  # what else it says about itself: its model, its speech service, its room

    @classmethod
    def of(cls, plugged: Plugged, words: Phrasebook) -> "ComponentOut":
        built = plugged.component
        component = built if isinstance(built, Component) else None
        brand = built.info.brand if isinstance(built, Connector) else None
        detail = component.health_detail() if component else None
        return cls(
            slot=plugged.family,
            name=plugged.name,
            adapter=plugged.id,
            model_type=built.type if isinstance(built, Model) else None,
            brand=brand or (component.brand if component else None),
            version=plugged.origin.version if plugged.origin else None,
            distribution=plugged.origin.name if plugged.origin else None,
            capabilities=sorted(component.capabilities.items) if component else [],
            health=component.health() if component else Health.STARTED,
            health_detail=words.text(detail) if detail else None,
            details=dict(component.details()) if component else {},
        )

    @classmethod
    def satellite(cls, satellite: Satellite, heard: frozenset[str] | None, words: Phrasebook) -> "ComponentOut":
        """`heard`: the rooms a spoken channel hears now; None when no channel can tell."""
        offline = heard is not None and satellite.room not in heard
        return cls(
            slot="satellite",
            name=satellite.id,
            adapter=satellite.model,
            model_type=None,
            brand=satellite.brand,
            version=satellite.software.version,
            distribution=satellite.software.name,
            capabilities=sorted(satellite.capabilities),
            health=None if heard is None else Health.UNAVAILABLE if offline else Health.STARTED,
            health_detail=words.text(Message.of("health-satellite-offline", room=satellite.room)) if offline else None,
            details={"room": satellite.room},
        )


class NestorOut(BaseModel):
    version: str


class SystemOut(BaseModel):
    nestor: NestorOut
    agent: AgentOut
    restart_required: bool  # the configuration was written since it started: a restart applies it
    pending_changes: list[str]
    components: list[ComponentOut]


class ReleaseChangeOut(BaseModel):
    kind: ChangeKind
    text: str  # one line of the changelog, in English


class ReleaseOut(BaseModel):
    version: str
    date: date
    url: str  # its notes, for people
    breaking: bool  # the data or the configuration must be redone, or a contract changed
    changes: list[ReleaseChangeOut]

    @classmethod
    def of(cls, release: Release) -> "ReleaseOut":
        return cls(
            version=release.version,
            date=release.date,
            url=release.url,
            breaking=release.breaking,
            changes=[ReleaseChangeOut(kind=c.kind, text=c.text) for c in release.changes],
        )


class LeftBehindOut(BaseModel):
    id: str
    name: str | None  # what the household calls it


class UpdatesOut(BaseModel):
    """What was released since the running version, and how this Nestor gets it."""

    running: str
    releases: list[ReleaseOut]  # newer than the running version, newest first; empty: up to date (or not checked)
    left_behind: list[LeftBehindOut]  # paired satellites the newest release no longer speaks to
    installation: InstallKind | None  # how Nestor is installed; None when `updates.check` is off
    commands: list[str]  # what to run to update it by hand (none for a developer's checkout)
    installable: bool  # `POST /system/updates/install` can install the newest release here
    installing: str | None  # the version being installed; a restart follows
    failed: str | None  # the version that last failed to install (the running one stayed)

    @classmethod
    def of(cls, nestor: Nestor) -> "UpdatesOut":
        updates = nestor.updates
        if updates is None:
            return cls(running=__version__, releases=[], left_behind=[], installation=None, commands=[],
                       installable=False, installing=None, failed=None)  # fmt: skip
        return cls(
            running=updates.running,
            releases=[ReleaseOut.of(r) for r in updates.newer()],
            left_behind=[LeftBehindOut(id=s.id, name=s.name) for s in updates.left_behind(nestor.pairing.satellites())],
            installation=updates.installation.kind,
            commands=list(updates.installation.commands),
            installable=updates.installer is not None,
            installing=updates.installing,
            failed=updates.failed,
        )


class InstallIn(Input):
    version: str  # the newest release, as `GET /system/updates` says
    confirm: bool  # must be true: once installed, Nestor restarts and every conversation is interrupted


class RestartIn(Input):
    confirm: bool  # must be true: a restart interrupts every conversation


class RestartOut(BaseModel):
    restarting: bool
