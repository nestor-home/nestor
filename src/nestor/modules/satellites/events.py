"""Satellite events: pairings, connections and the observations devices report. Never a token."""

from datetime import datetime

from nestor.core import Capability, Event, PersonId
from nestor.modules.satellites.types import Device


class SatellitePairingRequested(Event, event_type="satellite.pairing.requested"):
    pairing_id: str
    device: Device
    capabilities: tuple[Capability, ...]
    expires_at: datetime


class SatellitePaired(Event, event_type="satellite.paired"):
    """A household member approved the device; pairing the same device again replaces its token."""

    pairing_id: str
    device: Device
    capabilities: tuple[Capability, ...]  # what it may do, a subset of what it declared
    token_hash: str  # SHA-256 of a 256-bit random token: enough to check it, useless to forge it
    approved_by: PersonId | None = None


class SatelliteRevoked(Event, event_type="satellite.revoked"):
    device_id: str
    revoked_by: PersonId | None = None


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
