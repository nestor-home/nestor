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

from nestor.core import Capability, ContractError

PROTOCOL = "nestor.satellite/1"

AUDIO_CAPTURE = Capability("audio.capture")
AUDIO_PLAYBACK = Capability("audio.playback")
PERSON_DETECTION = Capability("vision.person_detection")
SPEECH_ACTIVITY = Capability("audio.speech_activity")

_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")  # device ids and rooms end up in addresses (`voice:salon`)
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MAX_CAPABILITIES = 32
MAX_SDK = 64


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
class DeclaredCapability:
    """A capability the device claims, with its own parameters (`{"name": "audio.capture", "formats": [...]}`)."""

    name: Capability
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Manifest:
    """What a device says about itself when it pairs and when it connects."""

    device: Device
    capabilities: tuple[DeclaredCapability, ...] = ()
    protocol: str = PROTOCOL
    sdk: str | None = None  # the software it runs, as it names it ("nestor-satellite-python 0.2.0"); optional

    @property
    def names(self) -> frozenset[Capability]:
        return frozenset(c.name for c in self.capabilities)

    def to_json(self) -> dict[str, Any]:
        device = {"id": self.device.id, "model": self.device.model, "room": self.device.room}
        data: dict[str, Any] = {
            "protocol": self.protocol,
            "device": device | ({"brand": self.device.brand} if self.device.brand else {}),
            "capabilities": [{"name": c.name, **c.params} for c in self.capabilities],
        }
        return data | ({"sdk": self.sdk} if self.sdk else {})

    @classmethod
    def from_json(cls, data: object) -> "Manifest":
        """Validate a manifest received from a device; anything unexpected is a `ContractError`."""
        if not isinstance(data, dict) or set(data) - {"protocol", "device", "capabilities", "sdk"}:
            raise ContractError("a manifest is an object with protocol, device, capabilities and an optional sdk")
        if data.get("protocol") != PROTOCOL:
            raise ContractError(f"unsupported protocol {data.get('protocol')!r}, expected {PROTOCOL!r}")
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
        sdk = data.get("sdk")
        if sdk is not None and (not isinstance(sdk, str) or not 0 < len(sdk) <= MAX_SDK):
            raise ContractError(f"sdk must be a non-empty string of at most {MAX_SDK} characters")
        return cls(device, tuple(declared), sdk=sdk)

    @staticmethod
    def json_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "protocol": {"const": PROTOCOL},
                "device": Device.json_schema(),
                "sdk": {"type": "string", "minLength": 1, "maxLength": MAX_SDK},
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
            "required": ["protocol", "device"],
            "additionalProperties": False,
        }


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


class PairingStatus(StrEnum):
    PENDING = "pending"  # waiting for a household member to confirm the code
    APPROVED = "approved"  # the token is handed out with this status, once
    CLAIMED = "claimed"  # the device already received its token
    EXPIRED = "expired"  # too late, unknown or superseded: ask again


@dataclass(frozen=True, slots=True, kw_only=True)
class PairingTicket:
    """What the device gets when it asks to pair: it shows `code` and polls `id`."""

    id: str
    code: str
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class PairingState:
    status: PairingStatus
    token: str | None = None  # only with the first APPROVED answer
    satellite: Satellite | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingPairing:
    """A device waiting for approval, as the admin shows it — never with its code, which proves the
    approver can see the device."""

    id: str
    device: Device
    capabilities: frozenset[Capability]
    expires_at: datetime
    sdk: str | None = None
