"""Satellites: adding one, the devices waiting for a proof (never with their code), and the paired ones.

A person adds a satellite by starting an *addition* with the pairing method they pick
(`GET /satellites/pairing-methods` lists them all, a pending device says which it supports). An
enrollment method answers the enrollment code and its pairing URI, once: the device presenting it is
paired at once. A device code method waits for a device to ask: the person tells the pending devices
apart (identify) and types the code the right one presents (`POST /satellites/approvals`), which
proves they can see or hear it. Progress shows in the addition's `stage`; poll
`GET /satellites/additions/{id}` (or follow `GET /journal/stream?kind=satellite`). The local command
line reaches these routes with the bearer token of `admin.token`.
"""

import re
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.satellites.pairing import approvers, unavailable
from nestor.admin.api.v1.satellites.schemas import (
    AdditionIn,
    AdditionOut,
    AdditionsOut,
    ApprovalIn,
    MethodOut,
    MethodsOut,
    PendingOut,
    SatelliteOut,
    SatellitesOut,
    StartedOut,
    UpdateRequestedOut,
)
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.core import Capability, ContractError, utc_now
from nestor.modules.accounts import Scope
from nestor.modules.satellites import (
    RECOMMENDED,
    DeviceUnavailable,
    PairingRefused,
    group,
    pairing_uri,
    recommended,
)
from nestor.modules.satellites.codes import DEVICE_CODE
from nestor.modules.satellites.types import check_capability, check_room

router = APIRouter(tags=["satellites"])
Pairer = Annotated[Caller, Depends(allowed(Scope.SATELLITES_MANAGE, local=True))]


@router.get("/satellites")
async def list_satellites(request: Request, caller: Pairer) -> SatellitesOut:
    admin = state(request)
    pairing, words = admin.nestor.pairing, caller.phrasebook
    additions = await pairing.expire_additions()
    approved, people, heard = await approvers(admin), People(admin.nestor.household), admin.nestor.heard_rooms()
    pending, now = pairing.pending(), utc_now()
    return SatellitesOut(
        pending=[PendingOut.of(p, words, now) for p in pending],
        paired=[
            SatelliteOut.of(s, pairing, people.ref(approved.get(s.id)), heard, words) for s in pairing.satellites()
        ],
        additions=[AdditionOut.of(a, pending, people, words) for a in additions],
    )


@router.get("/satellites/pairing-methods")
async def pairing_methods(caller: Pairer) -> MethodsOut:
    """Every pairing method, for a device that has not contacted Nestor yet."""
    return MethodsOut(
        methods=[MethodOut.of(m, caller.phrasebook) for m in RECOMMENDED], recommended=recommended(RECOMMENDED)
    )


@router.post("/satellites/additions", status_code=201)
async def start_addition(request: Request, caller: Pairer, body: AdditionIn) -> StartedOut:
    admin = state(request)
    pairing = admin.nestor.pairing
    try:
        started = await pairing.start_addition(
            body.method,
            by=caller.person,
            name=body.name,
            room=check_room(body.room) if body.room is not None else None,
            capabilities=[check_capability(c) for c in body.capabilities] if body.capabilities is not None else None,
            ttl_s=body.ttl_s,
        )
    except PairingRefused:
        raise ApiError(409, "too_many_additions") from None
    core = admin.nestor.satellite_url(urllib.parse.urlsplit(admin.base_url(request)).hostname or "localhost")
    code = started.code
    return StartedOut(
        addition=AdditionOut.of(started.addition, pairing.pending(), People(admin.nestor.household), caller.phrasebook),
        code=group(code) if code else None,
        uri=pairing_uri(core, code) if code and core else None,
    )


@router.get("/satellites/additions")
async def list_additions(request: Request, caller: Pairer) -> AdditionsOut:
    """The additions in progress."""
    admin = state(request)
    pairing = admin.nestor.pairing
    additions = await pairing.expire_additions()
    pending, people = pairing.pending(), People(admin.nestor.household)
    return AdditionsOut(additions=[AdditionOut.of(a, pending, people, caller.phrasebook) for a in additions])


@router.get("/satellites/additions/{addition_id}")
async def get_addition(request: Request, caller: Pairer, addition_id: str) -> AdditionOut:
    """One addition, in progress or over: poll it to follow its `stage`."""
    admin = state(request)
    pairing = admin.nestor.pairing
    addition = await pairing.addition(addition_id)
    if addition is None:
        raise not_found("addition_unknown")
    return AdditionOut.of(addition, pairing.pending(), People(admin.nestor.household), caller.phrasebook)


@router.delete("/satellites/additions/{addition_id}", status_code=204)
async def cancel_addition(request: Request, caller: Pairer, addition_id: str) -> Response:
    """Cancel an addition in progress: its enrollment code no longer pairs anything."""
    try:
        await state(request).nestor.pairing.cancel_addition(addition_id, by=caller.person)
    except ContractError:
        raise not_found("addition_unknown") from None
    return Response(status_code=204)


@router.post("/satellites/pending/{pairing_id}/identify", status_code=204)
async def identify_pending(request: Request, caller: Pairer, pairing_id: str) -> Response:
    """Ask a pending device to make itself noticed (it hears it within a second or so)."""
    try:
        await state(request).nestor.pairing.identify_pending(pairing_id, by=caller.person)
    except DeviceUnavailable as error:
        raise unavailable(error, "pending_unknown") from None
    return Response(status_code=204)


@router.get("/satellites/{device_id}")
async def get_satellite(request: Request, caller: Pairer, device_id: str) -> SatelliteOut:
    """One paired satellite; 404 when it is not (or no longer) paired."""
    admin = state(request)
    pairing = admin.nestor.pairing
    satellite = next((s for s in pairing.satellites() if s.id == device_id), None)
    if satellite is None:
        raise not_found("satellite_unknown")
    approved = People(admin.nestor.household).ref((await approvers(admin)).get(device_id))
    return SatelliteOut.of(satellite, pairing, approved, admin.nestor.heard_rooms(), caller.phrasebook)


@router.post("/satellites/{device_id}/identify", status_code=204)
async def identify_satellite(request: Request, caller: Pairer, device_id: str) -> Response:
    """Ask a paired, connected satellite to make itself noticed."""
    try:
        await state(request).nestor.pairing.identify(device_id, by=caller.person)
    except DeviceUnavailable as error:
        raise unavailable(error, "satellite_unknown") from None
    return Response(status_code=204)


@router.post("/satellites/{device_id}/update", status_code=202)
async def update_satellite(request: Request, caller: Pairer, device_id: str) -> UpdateRequestedOut:
    """Ask a connected satellite to install the newer version of its software it reported. It fetches it
    from its own source, starts again on it, and goes back to the version it ran if that fails."""
    try:
        version = await state(request).nestor.pairing.update(device_id, by=caller.person)
    except DeviceUnavailable as error:
        if error.reason == "current":
            raise ApiError(409, "update_unavailable") from None
        raise unavailable(error, "satellite_unknown", unsupported="update_unsupported") from None
    return UpdateRequestedOut(version=version)


@router.post("/satellites/approvals", status_code=201)
async def approve_satellite(request: Request, caller: Pairer, body: ApprovalIn) -> SatelliteOut:
    """Type the device code a pending device presents; the first proof accepted wins."""
    admin = state(request)
    code = re.sub(r"\s", "", body.code)
    if not DEVICE_CODE.match(code):
        raise ApiError(400, "invalid_code")
    try:
        satellite = await admin.nestor.pairing.approve(
            code,
            by=caller.person,
            capabilities=[Capability(c) for c in body.capabilities] if body.capabilities is not None else None,
            pairing_id=body.pairing_id,
            method=body.method,
            addition_id=body.addition_id,
        )
    except PairingRefused as refused:
        if refused.reason == "addition_over":
            raise ApiError(409, "addition_over") from None
        if refused.reason == "not_a_device_code_method":
            raise ApiError(400, "not_a_device_code_method") from None
        raise ApiError(400, "pairing_refused") from None
    approved = People(admin.nestor.household).ref(caller.person)
    return SatelliteOut.of(satellite, admin.nestor.pairing, approved, admin.nestor.heard_rooms(), caller.phrasebook)


@router.delete("/satellites/{device_id}", status_code=204)
async def revoke_satellite(request: Request, caller: Pairer, device_id: str) -> Response:
    """The device can no longer connect; pairing it again needs a new proof."""
    try:
        await state(request).nestor.pairing.revoke(device_id, by=caller.person)
    except ContractError:
        raise not_found("satellite_unknown") from None
    return Response(status_code=204)
