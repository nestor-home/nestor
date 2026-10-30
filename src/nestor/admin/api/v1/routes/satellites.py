"""Satellites: devices waiting to be paired (never with their code) and the paired ones.

Approving needs the code the device shows — it proves the person approving can see the device — and,
from the front, the pairing id the code was typed on, so that a code shown by another device is
refused. The local command line reaches these routes with the bearer token of `admin.token`.
"""

import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.models import Input, People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState, state
from nestor.core import Capability, ContractError, utc_now
from nestor.modules.accounts import Scope
from nestor.modules.channels import Medium
from nestor.modules.satellites import (
    PairingRefused,
    Satellite,
    SatelliteConnected,
    SatelliteDisconnected,
    SatellitePaired,
)

router = APIRouter(tags=["satellites"])
Pairer = Annotated[Caller, Depends(allowed(Scope.SATELLITES_MANAGE, local=True))]

CODE = re.compile(r"^\d{6}$")


class CapabilityOut(BaseModel):
    name: str
    label: str  # rendered in the reader's language; its technical name when no catalogue names it


class DeviceOut(BaseModel):
    id: str
    model: str
    room: str
    brand: str | None  # its maker, as the device declares it


class PendingOut(BaseModel):
    pairing_id: str
    device: DeviceOut
    capabilities: list[CapabilityOut]  # what it declares; all are offered, checked by default
    sdk: str | None  # the software it declares
    sdk_version: str | None
    expires_in_s: int


class SatelliteOut(BaseModel):
    id: str
    model: str
    room: str
    brand: str | None
    sdk: str | None  # the software it declared
    sdk_version: str | None
    capabilities: list[CapabilityOut]  # what it may use
    paired_at: datetime
    last_seen_at: datetime | None  # when it last connected or disconnected; None: never since pairing
    approved_by: PersonRef | None
    connected: bool | None  # its room can be heard right now; None without a spoken channel to tell


class SatellitesOut(BaseModel):
    pending: list[PendingOut]
    paired: list[SatelliteOut]


class ApprovalIn(Input):
    code: str  # the 6 digits the device shows (spaces ignored)
    pairing_id: str | None = None  # the request the code was typed on; the front always sends it
    capabilities: list[str] | None = None  # what to grant, a subset of what it declared; all when absent


@router.get("/satellites")
async def list_satellites(request: Request, caller: Pairer) -> SatellitesOut:
    admin = state(request)
    pairing = admin.nestor.pairing
    approvals = {e.device.id: e for e in await admin.nestor.journal.history(SatellitePaired)}  # the latest wins
    now = utc_now()
    live = live_rooms(admin)
    people = People(admin.nestor.household)
    seen = await last_seen(admin)
    return SatellitesOut(
        pending=[
            PendingOut(
                pairing_id=p.id,
                device=DeviceOut(id=p.device.id, model=p.device.model, room=p.device.room, brand=p.device.brand),
                capabilities=_capabilities(p.capabilities, caller.phrasebook),
                sdk=p.sdk.name if p.sdk else None,
                sdk_version=p.sdk.version if p.sdk else None,
                expires_in_s=max(0, int((p.expires_at - now).total_seconds())),
            )
            for p in pairing.pending()
        ],
        paired=[
            _satellite(
                s,
                people.ref(approvals[s.id].approved_by) if s.id in approvals else None,
                live,
                caller.phrasebook,
                seen.get(s.id),
            )
            for s in pairing.satellites()
        ],
    )


@router.post("/satellites/approvals", status_code=201)
async def approve_satellite(request: Request, caller: Pairer, body: ApprovalIn) -> SatelliteOut:
    admin = state(request)
    code = re.sub(r"\s", "", body.code)
    if not CODE.match(code):
        raise ApiError(400, "invalid_code")
    try:
        satellite = await admin.nestor.pairing.approve(
            code,
            by=caller.person,
            capabilities=[Capability(c) for c in body.capabilities] if body.capabilities is not None else None,
            pairing_id=body.pairing_id,
        )
    except PairingRefused:
        raise ApiError(400, "pairing_refused") from None
    return _satellite(
        satellite, People(admin.nestor.household).ref(caller.person), live_rooms(admin), caller.phrasebook
    )


@router.delete("/satellites/{device_id}", status_code=204)
async def revoke_satellite(request: Request, caller: Pairer, device_id: str) -> Response:
    """The device can no longer connect; pairing it again needs a new code."""
    try:
        await state(request).nestor.pairing.revoke(device_id, by=caller.person)
    except ContractError:
        raise not_found("satellite_unknown") from None
    return Response(status_code=204)


async def last_seen(admin: AdminState) -> dict[str, datetime]:
    """When each device last connected or disconnected (the latest wins)."""
    events = await admin.nestor.journal.history(SatelliteConnected, SatelliteDisconnected)
    return {e.device_id: e.at for e in events}


def _satellite(
    satellite: Satellite,
    approved_by: PersonRef | None,
    live: frozenset[str] | None,
    words: Phrasebook,
    seen: datetime | None = None,
) -> SatelliteOut:
    return SatelliteOut(
        id=satellite.id,
        model=satellite.model,
        room=satellite.room,
        brand=satellite.brand,
        sdk=satellite.sdk,
        sdk_version=satellite.sdk_version,
        capabilities=_capabilities(satellite.capabilities, words),
        paired_at=satellite.paired_at,
        last_seen_at=seen,
        approved_by=approved_by,
        connected=satellite.room in live if live is not None else None,
    )


def _capabilities(names: frozenset[Capability] | tuple[Capability, ...], words: Phrasebook) -> list[CapabilityOut]:
    return [CapabilityOut(name=n, label=words.capability(n)) for n in sorted(names)]


def live_rooms(admin: AdminState) -> frozenset[str] | None:
    """Rooms a spoken channel can be heard in right now; `None` without any spoken channel."""
    spoken = [c.rooms for c in admin.nestor.channels if c.medium is Medium.SPOKEN]
    return frozenset().union(*spoken) if spoken else None
