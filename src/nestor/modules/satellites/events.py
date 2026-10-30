"""Satellite events: pairings, enrollment codes, connections and the observations devices report.
Never a token, never a code in clear: only their hashes."""

from datetime import datetime

from nestor.core import Capability, Event, PersonId
from nestor.core.events import codec
from nestor.modules.satellites.types import Device, PairingMethod, Proof


class SatellitePairingRequested(Event, event_type="satellite.pairing.requested", version=2):
    """A device asked to pair, declaring how a person can pair it (`methods`)."""

    pairing_id: str
    device: Device
    capabilities: tuple[Capability, ...]
    expires_at: datetime
    methods: tuple[PairingMethod, ...] = ()

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, codec.JSON]) -> dict[str, codec.JSON]:
        return payload | {"methods": []}  # version 1: nestor.satellite/1 declared no method


class SatellitePaired(Event, event_type="satellite.paired", version=2):
    """A proof was accepted; pairing the same device again replaces its token. Only pairings made with
    the current `protocol` let a device connect: older ones must pair again."""

    pairing_id: str
    device: Device  # its room is where it was paired: an enrollment code may have chosen it
    capabilities: tuple[Capability, ...]  # what it may do, a subset of what it declared
    token_hash: str  # SHA-256 of a 256-bit random token: enough to check it, useless to forge it
    protocol: str
    proof: Proof
    method: PairingMethod | None = None  # how the person paired it, when known
    addition_id: str | None = None  # the addition it completed
    name: str | None = None  # what the household calls it
    approved_by: PersonId | None = None  # who typed its code, or made the enrollment code
    sdk: str | None = None  # the software it declared at pairing, and its version
    sdk_version: str | None = None

    @classmethod
    def upgrade(cls, version: int, payload: dict[str, codec.JSON]) -> dict[str, codec.JSON]:
        return payload | {"protocol": "nestor.satellite/1", "proof": Proof.DEVICE_CODE.value}


class SatelliteRevoked(Event, event_type="satellite.revoked"):
    device_id: str
    revoked_by: PersonId | None = None


class SatelliteIdentifyRequested(Event, event_type="satellite.identify.requested"):
    """A person asked a device to make itself noticed: a paired one (`device_id`) or a pending one."""

    device_id: str
    pairing_id: str | None = None  # set for a device still waiting to be paired
    requested_by: PersonId | None = None


class SatelliteAdditionStarted(Event, event_type="satellite.addition.started"):
    """A person started adding a satellite with `method`; an enrollment method makes a code."""

    addition_id: str
    method: PairingMethod
    expires_at: datetime
    code_hash: str | None = None  # SHA-256 of the enrollment code
    name: str | None = None
    room: str | None = None  # the room the device will be paired into, instead of the one it declares
    capabilities: tuple[Capability, ...] | None = None  # at most these; all it declares when None
    created_by: PersonId | None = None


class SatelliteAdditionCompleted(Event, event_type="satellite.addition.completed"):
    addition_id: str
    pairing_id: str
    device_id: str


class SatelliteAdditionCancelled(Event, event_type="satellite.addition.cancelled"):
    addition_id: str
    cancelled_by: PersonId | None = None


class SatelliteAdditionExpired(Event, event_type="satellite.addition.expired"):
    addition_id: str


class SatelliteEnrollmentRefused(Event, event_type="satellite.enrollment.refused"):
    """A device presented an enrollment code that pairs nothing (attempts are rate-limited)."""

    device_id: str
    reason: str  # unknown, expired, used or cancelled
    addition_id: str | None = None  # the addition the code belonged to, when it was one
    address: str | None = None  # the network address it came from


class SatelliteConnected(Event, event_type="satellite.connected"):
    device_id: str
    room: str


class SatelliteDisconnected(Event, event_type="satellite.disconnected"):
    device_id: str
    room: str


class PersonDetected(Event, event_type="observation.person.detected"):
    """People seen by a satellite's own detector (no image leaves the device)."""

    device_id: str
    room: str
    count: int
    confidence: float


class SpeechActivityObserved(Event, event_type="observation.speech.activity"):
    """Voice activity detected on the device: someone started or stopped speaking near it."""

    device_id: str
    room: str
    active: bool
