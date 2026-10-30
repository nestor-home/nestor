"""Satellites: devices that pair with the core, declare their capabilities, send observations and
receive intents. The wire protocol (`wire`) is transport-agnostic and published as JSON Schemas."""

from nestor.modules.satellites.events import (
    PersonDetected,
    SatelliteConnected,
    SatelliteDisconnected,
    SatellitePaired,
    SatellitePairingRequested,
    SatelliteRevoked,
    SpeechActivityObserved,
)
from nestor.modules.satellites.ports import SatelliteHost
from nestor.modules.satellites.service import Pairing, PairingRefused, hash_token
from nestor.modules.satellites.types import (
    AUDIO_CAPTURE,
    AUDIO_PLAYBACK,
    PERSON_DETECTION,
    PROTOCOL,
    SPEECH_ACTIVITY,
    DeclaredCapability,
    Device,
    Manifest,
    PairingState,
    PairingStatus,
    PairingTicket,
    PendingPairing,
    Satellite,
    Sdk,
)

__all__ = [
    "AUDIO_CAPTURE",
    "AUDIO_PLAYBACK",
    "PERSON_DETECTION",
    "PROTOCOL",
    "SPEECH_ACTIVITY",
    "DeclaredCapability",
    "Device",
    "Manifest",
    "Pairing",
    "PairingRefused",
    "PairingState",
    "PairingStatus",
    "PairingTicket",
    "PendingPairing",
    "PersonDetected",
    "Satellite",
    "SatelliteConnected",
    "SatelliteDisconnected",
    "SatelliteHost",
    "SatellitePaired",
    "SatellitePairingRequested",
    "SatelliteRevoked",
    "Sdk",
    "SpeechActivityObserved",
    "hash_token",
]
