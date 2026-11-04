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
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.models import Input, People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState, state
from nestor.core import Capability, ContractError, utc_now
from nestor.core.i18n import Message
from nestor.modules.accounts import Scope
from nestor.modules.satellites import (
    IDENTIFY,
    RECOMMENDED,
    UPDATE,
    Addition,
    AdditionStatus,
    DeviceUnavailable,
    Pairing,
    PairingMethod,
    PairingRefused,
    PendingPairing,
    Satellite,
    SatellitePaired,
    Software,
    UpdateState,
    group,
    pairing_uri,
    recommended,
)
from nestor.modules.satellites.codes import DEVICE_CODE
from nestor.modules.satellites.service import MAX_ADDITION_TTL_S, MIN_ADDITION_TTL_S
from nestor.modules.satellites.types import MAX_NAME, check_capability, check_room

router = APIRouter(tags=["satellites"])
Pairer = Annotated[Caller, Depends(allowed(Scope.SATELLITES_MANAGE, local=True))]


class CapabilityOut(BaseModel):
    name: str
    label: str  # rendered in the reader's language; its technical name when no catalogue names it


class MethodOut(BaseModel):
    """A pairing method, in the reader's language."""

    id: PairingMethod
    proof: str  # device_code: the device presents a code to type here; enrollment_code: a code made here
    label: str
    hint: str  # what the person does, in one sentence


class MethodsOut(BaseModel):
    methods: list[MethodOut]  # every method, the recommended order
    recommended: PairingMethod  # for a device that has not contacted Nestor yet


class DeviceOut(BaseModel):
    id: str
    model: str
    room: str
    brand: str | None  # its maker, as the device declares it


class SoftwareOut(BaseModel):
    name: str  # its package, where it is installed from
    version: str


class UpdateOut(BaseModel):
    """What a connected device last reported about its software."""

    state: UpdateState
    version: str | None  # the newer version, for every state but `current`
    notes: str | None  # an https address of what it changes, as the device found it: a link, never fetched


class PendingOut(BaseModel):
    pairing_id: str
    device: DeviceOut
    capabilities: list[CapabilityOut]  # what it declares; all are offered, checked by default
    methods: list[MethodOut]  # how it can be paired, the recommended one first
    recommended_method: PairingMethod
    can_identify: bool  # it declared device.identify: `POST /satellites/pending/{pairing_id}/identify`
    software: SoftwareOut  # what it declares it runs
    expires_in_s: int


class SatelliteOut(BaseModel):
    id: str
    name: str | None  # what the household calls it, given when it was added
    model: str
    room: str
    brand: str | None
    software: SoftwareOut  # what it runs, as it last declared
    protocol: str  # the protocol version it speaks
    capabilities: list[CapabilityOut]  # what it may use
    can_identify: bool  # allowed device.identify: `POST /satellites/{device_id}/identify` while connected
    can_update: bool  # allowed device.update: `POST /satellites/{device_id}/update` once it reports a version
    update: UpdateOut | None  # what it reported about its software; None while offline or before it reports
    paired_at: datetime
    last_seen_at: datetime | None  # when it last connected or disconnected; None: never since pairing
    approved_by: PersonRef | None
    connected: bool | None  # its room can be heard right now; None without a spoken channel to tell


class Stage(StrEnum):
    """Where an addition stands, for the front's progress."""

    WAITING = "waiting"  # no device yet
    DEVICE_SEEN = "device_seen"  # device code methods: devices wait (`candidates`), type the code one presents
    PAIRED = "paired"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AdditionOut(BaseModel):
    id: str
    method: MethodOut
    stage: Stage
    name: str | None
    room: str | None  # where the device is paired; None: the room it declares
    capabilities: list[CapabilityOut] | None  # allowed at most; None: all it declares
    candidates: list[str]  # pairing ids of the pending devices that may be this one (device code methods)
    device_id: str | None  # the paired device, once `paired`
    created_by: PersonRef | None
    created_at: datetime
    expires_at: datetime
    expires_in_s: int


class StartedOut(BaseModel):
    addition: AdditionOut
    code: str | None  # enrollment methods: the code, grouped (`K7QF-2M9X`), only in this answer
    uri: str | None  # enrollment methods: the pairing URI, render it as a QR code; None when no host serves satellites


class SatellitesOut(BaseModel):
    pending: list[PendingOut]
    paired: list[SatelliteOut]
    additions: list[AdditionOut]  # in progress


class AdditionsOut(BaseModel):
    additions: list[AdditionOut]


class AdditionIn(Input):
    method: PairingMethod
    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME)
    room: str | None = None  # a slug; None: the room the device declares
    capabilities: list[str] | None = None  # allowed at most; None: all it declares
    ttl_s: int | None = Field(default=None, ge=int(MIN_ADDITION_TTL_S), le=int(MAX_ADDITION_TTL_S))  # default 15 min


class ApprovalIn(Input):
    code: str  # the 6 digits the device presents (spaces ignored)
    pairing_id: str | None = None  # the pending device the code was typed for; the front always sends it
    addition_id: str | None = None  # the addition this completes: its method, name, room and capabilities apply
    method: PairingMethod | None = None  # how the person got the code, without an addition
    capabilities: list[str] | None = None  # what to grant, a subset of what it declared; all when absent


@router.get("/satellites")
async def list_satellites(request: Request, caller: Pairer) -> SatellitesOut:
    admin = state(request)
    pairing = admin.nestor.pairing
    additions = await pairing.expire_additions()
    approvals = {e.device.id: e for e in await admin.nestor.journal.history(SatellitePaired)}  # the latest wins
    now = utc_now()
    live = live_rooms(admin)
    people = People(admin.nestor.household)
    pending = pairing.pending()
    words = caller.phrasebook
    return SatellitesOut(
        pending=[_pending(p, words, now) for p in pending],
        paired=[
            _satellite(s, pairing, people.ref(approvals[s.id].approved_by) if s.id in approvals else None, live, words)
            for s in pairing.satellites()
        ],
        additions=[_addition(a, pending, people, words) for a in additions],
    )


@router.get("/satellites/pairing-methods")
async def pairing_methods(caller: Pairer) -> MethodsOut:
    """Every pairing method, for a device that has not contacted Nestor yet."""
    return MethodsOut(
        methods=[_method(m, caller.phrasebook) for m in RECOMMENDED], recommended=recommended(RECOMMENDED)
    )


@router.post("/satellites/additions", status_code=201)
async def start_addition(request: Request, caller: Pairer, body: AdditionIn) -> StartedOut:
    admin = state(request)
    try:
        started = await admin.nestor.pairing.start_addition(
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
        addition=_addition(started.addition, admin.nestor.pairing.pending(), People(admin.nestor.household),
                           caller.phrasebook),
        code=group(code) if code else None,
        uri=pairing_uri(core, code) if code and core else None,
    )  # fmt: skip


@router.get("/satellites/additions")
async def list_additions(request: Request, caller: Pairer) -> AdditionsOut:
    """The additions in progress."""
    admin = state(request)
    additions = await admin.nestor.pairing.expire_additions()
    pending, people = admin.nestor.pairing.pending(), People(admin.nestor.household)
    return AdditionsOut(additions=[_addition(a, pending, people, caller.phrasebook) for a in additions])


@router.get("/satellites/additions/{addition_id}")
async def get_addition(request: Request, caller: Pairer, addition_id: str) -> AdditionOut:
    """One addition, in progress or over: poll it to follow its `stage`."""
    admin = state(request)
    addition = await admin.nestor.pairing.addition(addition_id)
    if addition is None:
        raise not_found("addition_unknown")
    pending, people = admin.nestor.pairing.pending(), People(admin.nestor.household)
    return _addition(addition, pending, people, caller.phrasebook)


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
    except DeviceUnavailable as unavailable:
        raise _unavailable(unavailable, "pending_unknown") from None
    return Response(status_code=204)


@router.get("/satellites/{device_id}")
async def get_satellite(request: Request, caller: Pairer, device_id: str) -> SatelliteOut:
    """One paired satellite; 404 when it is not (or no longer) paired."""
    admin = state(request)
    satellite = next((s for s in admin.nestor.pairing.satellites() if s.id == device_id), None)
    if satellite is None:
        raise not_found("satellite_unknown")
    approvals = {e.device.id: e for e in await admin.nestor.journal.history(SatellitePaired)}
    approved = approvals[device_id].approved_by if device_id in approvals else None
    people = People(admin.nestor.household)
    return _satellite(satellite, admin.nestor.pairing, people.ref(approved), live_rooms(admin), caller.phrasebook)


@router.post("/satellites/{device_id}/identify", status_code=204)
async def identify_satellite(request: Request, caller: Pairer, device_id: str) -> Response:
    """Ask a paired, connected satellite to make itself noticed."""
    try:
        await state(request).nestor.pairing.identify(device_id, by=caller.person)
    except DeviceUnavailable as unavailable:
        raise _unavailable(unavailable, "satellite_unknown") from None
    return Response(status_code=204)


class UpdateRequestedOut(BaseModel):
    version: str  # what it was asked to install; its next connection shows it running


@router.post("/satellites/{device_id}/update", status_code=202)
async def update_satellite(request: Request, caller: Pairer, device_id: str) -> UpdateRequestedOut:
    """Ask a connected satellite to install the newer version of its software it reported. It fetches it
    from its own source, starts again on it, and goes back to the version it ran if that fails."""
    try:
        version = await state(request).nestor.pairing.update(device_id, by=caller.person)
    except DeviceUnavailable as unavailable:
        if unavailable.reason == "current":
            raise ApiError(409, "update_unavailable") from None
        raise _unavailable(unavailable, "satellite_unknown", unsupported="update_unsupported") from None
    return UpdateRequestedOut(version=version)


@router.post("/satellites/approvals", status_code=201)
async def approve_satellite(request: Request, caller: Pairer, body: ApprovalIn) -> SatelliteOut:
    """Type the device code a pending device presents; the first proof accepted wins."""
    admin = state(request)
    code = re.sub(r"\s", "", body.code)
    if not DEVICE_CODE.match(code):
        raise ApiError(400, "invalid_code")
    if body.method is not None and body.method.proof.value != "device_code":
        raise ApiError(400, "not_a_device_code_method")
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
        over = refused.reason == "addition_over"
        raise ApiError(409 if over else 400, "addition_over" if over else "pairing_refused") from None
    except ContractError:
        raise ApiError(400, "not_a_device_code_method") from None
    return _satellite(
        satellite,
        admin.nestor.pairing,
        People(admin.nestor.household).ref(caller.person),
        live_rooms(admin),
        caller.phrasebook,
    )


@router.delete("/satellites/{device_id}", status_code=204)
async def revoke_satellite(request: Request, caller: Pairer, device_id: str) -> Response:
    """The device can no longer connect; pairing it again needs a new proof."""
    try:
        await state(request).nestor.pairing.revoke(device_id, by=caller.person)
    except ContractError:
        raise not_found("satellite_unknown") from None
    return Response(status_code=204)


def _unavailable(
    unavailable: DeviceUnavailable, unknown: str, *, unsupported: str = "identify_unsupported"
) -> ApiError:
    if unavailable.reason == "unknown":
        return not_found(unknown)
    return ApiError(409, unsupported if unavailable.reason == "unsupported" else "satellite_offline")


def _method(method: PairingMethod, words: Phrasebook) -> MethodOut:
    key = method.value.replace(".", "-")
    return MethodOut(
        id=method,
        proof=method.proof.value,
        label=words.text(Message.of(f"pairing-method-{key}")),
        hint=words.text(Message.of(f"pairing-method-{key}-hint")),
    )


def _pending(pending: PendingPairing, words: Phrasebook, now: datetime) -> PendingOut:
    best = recommended(pending.methods)
    ordered = sorted(pending.methods, key=lambda m: (m is not best, RECOMMENDED.index(m)))
    return PendingOut(
        pairing_id=pending.id,
        device=DeviceOut(id=pending.device.id, model=pending.device.model, room=pending.device.room,
                         brand=pending.device.brand),
        capabilities=_capabilities(pending.capabilities, words),
        methods=[_method(m, words) for m in ordered],
        recommended_method=best,
        can_identify=pending.can_identify,
        software=_software(pending.software),
        expires_in_s=max(0, int((pending.expires_at - now).total_seconds())),
    )  # fmt: skip


def _addition(addition: Addition, pending: list[PendingPairing], people: People, words: Phrasebook) -> AdditionOut:
    device_code = addition.method.proof.value == "device_code"
    active = addition.status is AdditionStatus.ACTIVE
    candidates = [p.id for p in pending] if device_code and active else []
    stage = {
        AdditionStatus.COMPLETED: Stage.PAIRED,
        AdditionStatus.CANCELLED: Stage.CANCELLED,
        AdditionStatus.EXPIRED: Stage.EXPIRED,
    }.get(addition.status, Stage.DEVICE_SEEN if candidates else Stage.WAITING)
    return AdditionOut(
        id=addition.id,
        method=_method(addition.method, words),
        stage=stage,
        name=addition.name,
        room=addition.room,
        capabilities=_capabilities(addition.capabilities, words) if addition.capabilities is not None else None,
        candidates=candidates,
        device_id=addition.device_id,
        created_by=people.ref(addition.created_by),
        created_at=addition.created_at,
        expires_at=addition.expires_at,
        expires_in_s=max(0, int((addition.expires_at - utc_now()).total_seconds())) if active else 0,
    )


def _satellite(
    satellite: Satellite,
    pairing: Pairing,
    approved_by: PersonRef | None,
    live: frozenset[str] | None,
    words: Phrasebook,
) -> SatelliteOut:
    status = pairing.update_status(satellite.id)
    return SatelliteOut(
        id=satellite.id,
        name=satellite.name,
        model=satellite.model,
        room=satellite.room,
        brand=satellite.brand,
        software=_software(satellite.software),
        protocol=satellite.protocol,
        capabilities=_capabilities(satellite.capabilities, words),
        can_identify=IDENTIFY in satellite.capabilities,
        can_update=UPDATE in satellite.capabilities,
        update=UpdateOut(state=status.state, version=status.version, notes=status.notes) if status else None,
        paired_at=satellite.paired_at,
        last_seen_at=pairing.last_seen(satellite.id),
        approved_by=approved_by,
        connected=satellite.room in live if live is not None else None,
    )


def _software(software: Software) -> SoftwareOut:
    return SoftwareOut(name=software.name, version=software.version)


def _capabilities(names: frozenset[Capability] | tuple[Capability, ...], words: Phrasebook) -> list[CapabilityOut]:
    return [CapabilityOut(name=n, label=words.capability(n)) for n in sorted(names)]


def live_rooms(admin: AdminState) -> frozenset[str] | None:
    """Rooms a spoken channel can be heard in right now; `None` without any spoken channel."""
    spoken = [c.rooms for c in admin.nestor.channels if c.spoken]
    return frozenset().union(*spoken) if spoken else None
