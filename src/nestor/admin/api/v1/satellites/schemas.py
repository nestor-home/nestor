"""Satellites as the admin shows them: pairing methods, devices waiting, additions in progress, paired ones."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from nestor.admin.api.v1.shared import Input, People, PersonRef
from nestor.admin.presentation import Phrasebook
from nestor.core import Capability, utc_now
from nestor.core.i18n import Message
from nestor.modules.satellites import (
    IDENTIFY,
    RECOMMENDED,
    UPDATE,
    Addition,
    AdditionStatus,
    Pairing,
    PairingMethod,
    PendingPairing,
    Proof,
    Satellite,
    Software,
    UpdateState,
    recommended,
)
from nestor.modules.satellites.service import MAX_ADDITION_TTL_S, MIN_ADDITION_TTL_S
from nestor.modules.satellites.types import MAX_NAME


class CapabilityOut(BaseModel):
    name: str
    label: str  # rendered in the reader's language; its technical name when no catalogue names it

    @classmethod
    def all(cls, names: frozenset[Capability] | tuple[Capability, ...], words: Phrasebook) -> list["CapabilityOut"]:
        return [cls(name=n, label=words.capability(n)) for n in sorted(names)]


class MethodOut(BaseModel):
    """A pairing method, in the reader's language."""

    id: PairingMethod
    proof: Proof  # device_code: the device presents a code to type here; enrollment_code: a code made here
    label: str
    hint: str  # what the person does, in one sentence

    @classmethod
    def of(cls, method: PairingMethod, words: Phrasebook) -> "MethodOut":
        key = method.value.replace(".", "-")
        return cls(
            id=method,
            proof=method.proof,
            label=words.text(Message.of(f"pairing-method-{key}")),
            hint=words.text(Message.of(f"pairing-method-{key}-hint")),
        )


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

    @classmethod
    def of(cls, software: Software) -> "SoftwareOut":
        return cls(name=software.name, version=software.version)


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

    @classmethod
    def of(cls, pending: PendingPairing, words: Phrasebook, now: datetime) -> "PendingOut":
        best = recommended(pending.methods)
        ordered = sorted(pending.methods, key=lambda m: (m is not best, RECOMMENDED.index(m)))
        device = pending.device
        return cls(
            pairing_id=pending.id,
            device=DeviceOut(id=device.id, model=device.model, room=device.room, brand=device.brand),
            capabilities=CapabilityOut.all(pending.capabilities, words),
            methods=[MethodOut.of(m, words) for m in ordered],
            recommended_method=best,
            can_identify=pending.can_identify,
            software=SoftwareOut.of(pending.software),
            expires_in_s=max(0, int((pending.expires_at - now).total_seconds())),
        )


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

    @classmethod
    def of(
        cls,
        satellite: Satellite,
        pairing: Pairing,
        approved_by: PersonRef | None,
        heard: frozenset[str] | None,
        words: Phrasebook,
    ) -> "SatelliteOut":
        status = pairing.update_status(satellite.id)
        return cls(
            id=satellite.id,
            name=satellite.name,
            model=satellite.model,
            room=satellite.room,
            brand=satellite.brand,
            software=SoftwareOut.of(satellite.software),
            protocol=satellite.protocol,
            capabilities=CapabilityOut.all(satellite.capabilities, words),
            can_identify=IDENTIFY in satellite.capabilities,
            can_update=UPDATE in satellite.capabilities,
            update=UpdateOut(state=status.state, version=status.version, notes=status.notes) if status else None,
            paired_at=satellite.paired_at,
            last_seen_at=pairing.last_seen(satellite.id),
            approved_by=approved_by,
            connected=satellite.room in heard if heard is not None else None,
        )


class Stage(StrEnum):
    """Where an addition stands, for the front's progress."""

    WAITING = "waiting"  # no device yet
    DEVICE_SEEN = "device_seen"  # device code methods: devices wait (`candidates`), type the code one presents
    PAIRED = "paired"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


_OVER = {
    AdditionStatus.COMPLETED: Stage.PAIRED,
    AdditionStatus.CANCELLED: Stage.CANCELLED,
    AdditionStatus.EXPIRED: Stage.EXPIRED,
}


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

    @classmethod
    def of(cls, addition: Addition, pending: list[PendingPairing], people: People, words: Phrasebook) -> "AdditionOut":
        active = addition.status is AdditionStatus.ACTIVE
        candidates = [p.id for p in pending] if addition.method.proof is Proof.DEVICE_CODE and active else []
        return cls(
            id=addition.id,
            method=MethodOut.of(addition.method, words),
            stage=_OVER.get(addition.status, Stage.DEVICE_SEEN if candidates else Stage.WAITING),
            name=addition.name,
            room=addition.room,
            capabilities=CapabilityOut.all(addition.capabilities, words) if addition.capabilities is not None else None,
            candidates=candidates,
            device_id=addition.device_id,
            created_by=people.ref(addition.created_by),
            created_at=addition.created_at,
            expires_at=addition.expires_at,
            expires_in_s=max(0, int((addition.expires_at - utc_now()).total_seconds())) if active else 0,
        )


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


class UpdateRequestedOut(BaseModel):
    version: str  # what it was asked to install; its next connection shows it running
