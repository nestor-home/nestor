"""Satellites: devices that pair with the core, declare what they can do, observe and act.

A satellite never holds a second brain: it streams audio, reports observations made on the device
and carries out the intents the core sends it. Its manifest is the only thing it claims about
itself; what it may do is decided when a household member approves the pairing.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from nestor.core import Capability, ContractError, PersonId

PROTOCOL = "nestor.satellite/2"
_PROTOCOL = re.compile(r"^nestor\.satellite/\d+$")

AUDIO_CAPTURE = Capability("audio.capture")
AUDIO_PLAYBACK = Capability("audio.playback")
PERSON_DETECTION = Capability("vision.person_detection")
SPEECH_ACTIVITY = Capability("audio.speech_activity")
IDENTIFY = Capability("device.identify")  # it can make itself noticed (blink, wiggle, chime): an aid, never a proof

_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")  # device ids and rooms end up in addresses (`voice:salon`)
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MAX_CAPABILITIES = 32
MAX_NAME = 64


def check_room(room: str) -> str:
    if not _SLUG.match(room):
        raise ContractError(f"room {room!r} must be a lowercase slug (a-z, 0-9, - and _)")
    return room


def check_capability(name: str) -> Capability:
    if not _CAPABILITY.match(name):
        raise ContractError(f"invalid capability {name!r}: expected 'family.feature'")
    return Capability(name)


MAX_SDK = 64


class ProtocolUnsupported(ContractError):
    """The device speaks another version of the satellite protocol: it must be updated."""


class Proof(StrEnum):
    """Which way the pairing proof travelled."""

    DEVICE_CODE = "device_code"  # the device presented a code, a person typed it in the admin
    ENROLLMENT_CODE = "enrollment_code"  # a person made a code in the admin and gave it to the device


class PairingMethod(StrEnum):
    """How a person can pair this device; it declares those it supports, the person picks one."""

    DISPLAY = "device_code.display"  # it shows its device code on a screen
    SPEECH = "device_code.speech"  # it says its device code aloud
    INPUT = "enrollment.input"  # an enrollment code can be typed on it
    PROVISIONING = "enrollment.provisioning"  # an enrollment code or URI can be set in its configuration
    QR = "enrollment.qr"  # it scans the QR code of a pairing URI

    @property
    def proof(self) -> Proof:
        return Proof.DEVICE_CODE if self.value.startswith("device_code.") else Proof.ENROLLMENT_CODE


# The order the admin recommends them in: what asks the least of the person first.
RECOMMENDED = (
    PairingMethod.DISPLAY,
    PairingMethod.SPEECH,
    PairingMethod.QR,
    PairingMethod.INPUT,
    PairingMethod.PROVISIONING,
)


def recommended(methods: "frozenset[PairingMethod] | tuple[PairingMethod, ...]") -> PairingMethod:
    """The method to highlight among those a device supports (all of them for an unknown device)."""
    return next((m for m in RECOMMENDED if m in methods), PairingMethod.PROVISIONING)


@dataclass(frozen=True, slots=True)
class Device:
    id: str
    model: str
    room: str
    brand: str | None = None  # its maker, as a slug ("pollen-robotics"); optional

    @classmethod
    def from_json(cls, data: object) -> "Device":
        if not isinstance(data, dict) or not {"id", "model", "room"} <= set(data) <= {"id", "model", "room", "brand"}:
            raise ContractError("device must have id, model and room, and may have a brand")
        for name in ("id", "room"):
            if not isinstance(data[name], str) or not _SLUG.match(data[name]):
                raise ContractError(f"device {name} {data[name]!r} must be a lowercase slug (a-z, 0-9, - and _)")
        if not isinstance(data["model"], str) or not 0 < len(data["model"]) <= 64:
            raise ContractError("device model must be a non-empty string of at most 64 characters")
        brand = data.get("brand")
        if brand is not None and (not isinstance(brand, str) or not _SLUG.match(brand)):
            raise ContractError(f"device brand {brand!r} must be a lowercase slug (a-z, 0-9, - and _)")
        return cls(data["id"], data["model"], data["room"], brand)

    @staticmethod
    def json_schema() -> dict[str, Any]:
        slug = {"type": "string", "pattern": _SLUG.pattern}
        return {
            "type": "object",
            "properties": {
                "id": slug,
                "model": {"type": "string", "minLength": 1, "maxLength": 64},
                "room": slug,
                "brand": slug,
            },
            "required": ["id", "model", "room"],
            "additionalProperties": False,
        }


@dataclass(frozen=True, slots=True)
class Sdk:
    """The software a device runs, as it names it: `nestor-satellite-python` `0.2.0`."""

    name: str
    version: str

    @classmethod
    def from_json(cls, data: object) -> "Sdk":
        if not isinstance(data, dict) or set(data) != {"name", "version"}:
            raise ContractError("sdk must have exactly a name and a version")
        for key in ("name", "version"):
            if not isinstance(data[key], str) or not 0 < len(data[key]) <= MAX_SDK:
                raise ContractError(f"sdk {key} must be a non-empty string of at most {MAX_SDK} characters")
        return cls(data["name"], data["version"])

    @staticmethod
    def json_schema() -> dict[str, Any]:
        text = {"type": "string", "minLength": 1, "maxLength": MAX_SDK}
        return {
            "type": "object",
            "properties": {"name": text, "version": text},
            "required": ["name", "version"],
            "additionalProperties": False,
        }


@dataclass(frozen=True, slots=True)
class DeclaredCapability:
    """A capability the device claims, with its own parameters (`{"name": "audio.capture", "formats": [...]}`)."""

    name: Capability
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Manifest:
    """What a device says about itself when it pairs and when it connects."""

    device: Device
    capabilities: tuple[DeclaredCapability, ...] = ()
    pairing_methods: tuple[PairingMethod, ...] = (PairingMethod.PROVISIONING,)
    protocol: str = PROTOCOL
    sdk: Sdk | None = None  # the software it runs; optional

    @property
    def names(self) -> frozenset[Capability]:
        return frozenset(c.name for c in self.capabilities)

    def to_json(self) -> dict[str, Any]:
        device = {"id": self.device.id, "model": self.device.model, "room": self.device.room}
        data: dict[str, Any] = {
            "protocol": self.protocol,
            "device": device | ({"brand": self.device.brand} if self.device.brand else {}),
            "capabilities": [{"name": c.name, **c.params} for c in self.capabilities],
            "pairing_methods": [m.value for m in self.pairing_methods],
        }
        return data | ({"sdk": {"name": self.sdk.name, "version": self.sdk.version}} if self.sdk else {})

    @classmethod
    def from_json(cls, data: object) -> "Manifest":
        """Validate a manifest received from a device; anything unexpected is a `ContractError`."""
        if not isinstance(data, dict) or set(data) - _MANIFEST_KEYS:
            raise ContractError(
                "a manifest is an object with protocol, device, capabilities, pairing_methods and an optional sdk"
            )
        protocol = data.get("protocol")
        if isinstance(protocol, str) and _PROTOCOL.match(protocol) and protocol != PROTOCOL:
            raise ProtocolUnsupported(f"the device speaks {protocol}, this core only {PROTOCOL}: update the device")
        if protocol != PROTOCOL:
            raise ContractError(f"unsupported protocol {protocol!r}, expected {PROTOCOL!r}")
        device = Device.from_json(data.get("device"))
        capabilities = data.get("capabilities", [])
        if not isinstance(capabilities, list) or len(capabilities) > MAX_CAPABILITIES:
            raise ContractError(f"capabilities must be a list of at most {MAX_CAPABILITIES} entries")
        declared = []
        for entry in capabilities:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not _CAPABILITY.match(name):
                raise ContractError(f"invalid capability {entry!r}: expected {{'name': 'family.feature', ...}}")
            declared.append(DeclaredCapability(Capability(name), {k: v for k, v in entry.items() if k != "name"}))
        if len({c.name for c in declared}) != len(declared):
            raise ContractError("a capability is declared twice")
        sdk = Sdk.from_json(data["sdk"]) if "sdk" in data else None
        return cls(device, tuple(declared), _methods(data.get("pairing_methods")), sdk=sdk)

    @staticmethod
    def json_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "protocol": {"const": PROTOCOL},
                "device": Device.json_schema(),
                "sdk": Sdk.json_schema(),
                "pairing_methods": {
                    "type": "array",
                    "items": {"enum": [m.value for m in PairingMethod]},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "capabilities": {
                    "type": "array",
                    "maxItems": MAX_CAPABILITIES,
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "pattern": _CAPABILITY.pattern}},
                        "required": ["name"],
                    },
                },
            },
            "required": ["protocol", "device", "pairing_methods"],
            "additionalProperties": False,
        }


_MANIFEST_KEYS = {"protocol", "device", "capabilities", "pairing_methods", "sdk"}


def _methods(data: object) -> tuple[PairingMethod, ...]:
    values = {m.value for m in PairingMethod}
    if not isinstance(data, list) or not data or any(not isinstance(m, str) or m not in values for m in data):
        raise ContractError(f"pairing_methods must list at least one of {', '.join(sorted(values))}")
    if len(set(data)) != len(data):
        raise ContractError("a pairing method is declared twice")
    return tuple(PairingMethod(m) for m in data)


@dataclass(frozen=True, slots=True, kw_only=True)
class Satellite:
    """A paired device: where it is and what it was allowed to do. Only its token's hash is kept."""

    id: str
    model: str
    room: str
    capabilities: frozenset[Capability]
    token_hash: str
    paired_at: datetime
    brand: str | None = None
    sdk: str | None = None
    sdk_version: str | None = None
    name: str | None = None  # what the household calls it, given when it was added


class PairingStatus(StrEnum):
    PENDING = "pending"  # waiting for a proof: the device code typed in the admin, or an enrollment code
    APPROVED = "approved"  # a proof was accepted; the token is handed out with this status, once
    CLAIMED = "claimed"  # the device already received its token
    EXPIRED = "expired"  # too late, unknown or superseded: ask again


@dataclass(frozen=True, slots=True, kw_only=True)
class PairingTicket:
    """What the device gets when it asks to pair: it polls `id`, and presents `device_code` while pending
    (an approved ticket, paired with an enrollment code, has none)."""

    id: str
    status: PairingStatus
    expires_at: datetime
    device_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PairingState:
    status: PairingStatus
    token: str | None = None  # only with the first APPROVED answer
    satellite: Satellite | None = None
    identify: bool = False  # a person asked a pending device to make itself noticed, once


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingPairing:
    """A device waiting for a proof, as the admin shows it: never with its code, which proves the
    approver can see or hear the device."""

    id: str
    device: Device
    capabilities: frozenset[Capability]
    methods: tuple[PairingMethod, ...]
    expires_at: datetime
    sdk: Sdk | None = None

    @property
    def can_identify(self) -> bool:
        return IDENTIFY in self.capabilities


class AdditionStatus(StrEnum):
    ACTIVE = "active"  # waiting for its device
    COMPLETED = "completed"  # its device is paired
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True, kw_only=True)
class Addition:
    """A person adding a satellite from the admin, with the method they chose. With an enrollment
    method it holds the enrollment code, by its hash only, which pairs one device; with a device code
    method it waits for the person to type the code a device presents. Either way the device is paired
    named `name`, into `room` when set, allowed `capabilities` at most when set."""

    id: str
    method: PairingMethod
    created_at: datetime
    expires_at: datetime
    status: AdditionStatus = AdditionStatus.ACTIVE
    code_hash: str | None = None  # enrollment methods only
    name: str | None = None
    room: str | None = None
    capabilities: frozenset[Capability] | None = None
    created_by: PersonId | None = None
    device_id: str | None = None  # the device it paired, once completed


@dataclass(frozen=True, slots=True, kw_only=True)
class StartedAddition:
    """A new addition and, for an enrollment method, its code in clear this once."""

    addition: Addition
    code: str | None = None
