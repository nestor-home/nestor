"""The satellite wire protocol `nestor.satellite/2`: JSON messages in one envelope, whatever the transport,
and the JSON bodies of pairing over HTTP. The standard is `docs/satellite-protocol.md`.

    {"type": "intent.expression", "id": "…", "at": "2026-10-30T12:00:00+00:00",
     "payload": {"expression": "joy", "intensity": 1.0}}

The realtime profile carries them on the `nestor` WebRTC data channel; a WebSocket profile can carry
the same messages. Satellite → core: `hello` (its manifest, first), `ack` (of an intent id),
`observation.*`. Core → satellite: `welcome` (what it may do), `intent.*`, each acknowledged by id.

Pairing bodies (`PairingRequest`, `EnrollmentProof`, and the answers `ticket_json`, `state_json`,
`error_json`) are published as `pairing.*.json`.

The message classes are the source of truth: `schemas()` derives the JSON Schemas published for
drivers written in other languages, and `decode` enforces the same constraints.
"""

import dataclasses
import enum
import json
import typing
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, dataclass_transform, get_args, get_origin, get_type_hints

from nestor.core import ContractError, new_id, utc_now
from nestor.core.events import codec
from nestor.modules.behavior import Behavior, Expression
from nestor.modules.satellites.types import (
    PROTOCOL,
    Manifest,
    PairingMethod,
    PairingState,
    PairingStatus,
    PairingTicket,
    Proof,
)

SCHEMAS = Path(__file__).parent / "schemas"
SCHEMA_BASE = "https://nestor.mathislambert.fr/schemas/satellite/2/"


@dataclass(frozen=True, slots=True)
class Bounds:
    """Inclusive limits of a number field, checked on decode and published in the schema."""

    minimum: float | None = None
    maximum: float | None = None


type Unit = Annotated[float, Bounds(0.0, 1.0)]
type Count = Annotated[int, Bounds(0)]


class Direction(StrEnum):
    TO_CORE = "to_core"
    TO_SATELLITE = "to_satellite"


@dataclass_transform(frozen_default=True, kw_only_default=True)
@dataclass(frozen=True, kw_only=True)
class Message:
    message_type: ClassVar[str] = ""
    direction: ClassVar[Direction]
    _registry: ClassVar[dict[str, type["Message"]]] = {}

    def __init_subclass__(cls, *, message_type: str, direction: Direction, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if message_type in Message._registry:
            raise ContractError(f"message type {message_type!r} is defined twice")
        cls.message_type, cls.direction = message_type, direction
        dataclass(frozen=True, kw_only=True)(cls)
        Message._registry[message_type] = cls

    @staticmethod
    def types() -> dict[str, type["Message"]]:
        return dict(Message._registry)


class Hello(Message, message_type="hello", direction=Direction.TO_CORE):
    """First message of a connection: the device's manifest (its id must be the paired one)."""

    manifest: Manifest


class Ack(Message, message_type="ack", direction=Direction.TO_CORE):
    """The intent `of` was received (carrying it out is the device's business)."""

    of: str


class PersonObservation(Message, message_type="observation.person.detected", direction=Direction.TO_CORE):
    """People seen by the device's own detector, now (no image leaves the device)."""

    count: Count
    confidence: Unit


class SpeechActivityObservation(Message, message_type="observation.speech.activity", direction=Direction.TO_CORE):
    """Voice activity detected on the device started (`active`) or stopped."""

    active: bool


class Welcome(Message, message_type="welcome", direction=Direction.TO_SATELLITE):
    """Answer to `hello`: where the device is and what it was allowed to do."""

    device_id: str
    room: str
    capabilities: tuple[str, ...]


class BehaviorIntent(Message, message_type="intent.behavior", direction=Direction.TO_SATELLITE):
    """The assistant's attitude changed: show it until the next one."""

    behavior: Behavior


class ExpressionIntent(Message, message_type="intent.expression", direction=Direction.TO_SATELLITE):
    """An expression, sent as the matching audio is played (a laugh when the laugh is heard)."""

    expression: Expression
    intensity: Unit = 1.0


class BeatIntent(Message, message_type="intent.beat", direction=Direction.TO_SATELLITE):
    """A word is being played: a light speech accent."""


class IdentifyIntent(Message, message_type="intent.identify", direction=Direction.TO_SATELLITE):
    """A person asks the device to make itself noticed for a few seconds (blink, wiggle, chime)."""


# Pairing over HTTP.

ERRORS = {  # what each error answer means, by code, with its HTTP status
    "invalid_request": 422,  # the body does not follow its schema
    "protocol_unsupported": 422,  # the manifest names another version of the protocol
    "too_many_pending": 429,  # too many devices wait for a proof: retry later
    "too_many_attempts": 429,  # too many wrong enrollment codes: retry after `retry_after_s`
    "enrollment_refused": 403,  # the enrollment code pairs nothing: `reason` says why
    "not_pending": 409,  # the pairing no longer waits for a proof (the other proof won, or it expired)
}
REFUSALS = ("unknown", "expired", "used", "cancelled")


@dataclass(frozen=True, slots=True)
class PairingRequest:
    """`POST /satellites/pairings`: a device asks to pair, with its enrollment code if it has one."""

    manifest: Manifest
    enrollment_code: str | None = None
    method: PairingMethod | None = None  # how it received the code; required with it

    @classmethod
    def from_json(cls, data: object) -> "PairingRequest":
        if (
            not isinstance(data, dict)
            or "manifest" not in data
            or set(data) - {"manifest", "enrollment_code", "method"}
        ):
            raise ContractError(
                "a pairing request is an object with a manifest, and an enrollment_code with its method"
            )
        manifest = Manifest.from_json(data["manifest"])
        if ("enrollment_code" in data) != ("method" in data):
            raise ContractError("enrollment_code and method come together")
        if "enrollment_code" not in data:
            return cls(manifest)
        proof = EnrollmentProof.from_json({"enrollment_code": data["enrollment_code"], "method": data["method"]})
        return cls(manifest, proof.enrollment_code, proof.method)


@dataclass(frozen=True, slots=True)
class EnrollmentProof:
    """`POST /satellites/pairings/{pairing_id}/enrollment`: the enrollment code a pending device got."""

    enrollment_code: str
    method: PairingMethod

    @classmethod
    def from_json(cls, data: object) -> "EnrollmentProof":
        if not isinstance(data, dict) or set(data) != {"enrollment_code", "method"}:
            raise ContractError("an enrollment proof is an object with exactly enrollment_code and method")
        code, method = data["enrollment_code"], data["method"]
        if not isinstance(code, str) or not 0 < len(code) <= 32:
            raise ContractError("enrollment_code must be a string of 1 to 32 characters")
        if method not in {m.value for m in PairingMethod if m.proof is Proof.ENROLLMENT_CODE}:
            raise ContractError(f"method {method!r} is not an enrollment method")
        return cls(code, PairingMethod(method))


def ticket_json(ticket: PairingTicket) -> dict[str, Any]:
    answer = {"pairing_id": ticket.id, "status": ticket.status.value, "expires_at": ticket.expires_at.isoformat()}
    return answer | ({"device_code": ticket.device_code} if ticket.device_code is not None else {})


def state_json(state: PairingState) -> dict[str, Any]:
    answer: dict[str, Any] = {"status": state.status.value}
    if state.token is not None:
        answer["token"] = state.token
    if state.satellite is not None:
        answer |= {
            "device_id": state.satellite.id,
            "room": state.satellite.room,
            "capabilities": sorted(state.satellite.capabilities),
        }
    if state.identify:
        answer["identify"] = True
    return answer


def error_json(
    code: str, detail: str, *, reason: str | None = None, retry_after_s: float | None = None
) -> dict[str, Any]:
    answer: dict[str, Any] = {"error": code, "detail": detail}
    if reason is not None:
        answer["reason"] = reason
    if retry_after_s is not None:
        answer["retry_after_s"] = round(retry_after_s)
    return answer


def _pairing_schemas() -> dict[str, dict[str, Any]]:
    enrollment_methods = [m.value for m in PairingMethod if m.proof is Proof.ENROLLMENT_CODE]
    code = {"type": "string", "minLength": 1, "maxLength": 32}
    status = {"enum": [s.value for s in PairingStatus]}
    at = {"type": "string", "format": "date-time"}
    bodies: dict[str, tuple[str, dict[str, Any]]] = {
        "pairing.request.json": ("POST /satellites/pairings: a device asks to pair", {
            "properties": {"manifest": {"$ref": "manifest.json"}, "enrollment_code": code,
                           "method": {"enum": enrollment_methods}},
            "required": ["manifest"],
            "dependentRequired": {"enrollment_code": ["method"], "method": ["enrollment_code"]},
        }),
        "pairing.enrollment.json": ("POST /satellites/pairings/{pairing_id}/enrollment: a pending device's code", {
            "properties": {"enrollment_code": code, "method": {"enum": enrollment_methods}},
            "required": ["enrollment_code", "method"],
        }),
        "pairing.ticket.json": ("201 answer to a pairing request", {
            "properties": {"pairing_id": {"type": "string", "minLength": 1}, "status": status, "expires_at": at,
                           "device_code": {"type": "string", "pattern": "^[0-9]{6}$"}},
            "required": ["pairing_id", "status", "expires_at"],
        }),
        "pairing.state.json": ("GET /satellites/pairings/{pairing_id}: where a pairing stands", {
            "properties": {"status": status, "token": {"type": "string", "minLength": 1},
                           "device_id": {"type": "string"}, "room": {"type": "string"},
                           "capabilities": {"type": "array", "items": {"type": "string"}},
                           "identify": {"const": True}},
            "required": ["status"],
        }),
        "pairing.error.json": ("Error answer of the pairing endpoints", {
            "properties": {"error": {"enum": list(ERRORS)}, "detail": {"type": "string"},
                           "reason": {"enum": list(REFUSALS)}, "retry_after_s": {"type": "integer", "minimum": 0}},
            "required": ["error", "detail"],
        }),
    }  # fmt: skip
    return {
        name: {**_header(name, title), "type": "object", **body, "additionalProperties": False}
        for name, (title, body) in bodies.items()
    }


@dataclass(frozen=True, slots=True)
class Envelope:
    message: Message
    id: str
    at: datetime


def encode(message: Message, *, id: str | None = None, at: datetime | None = None) -> dict[str, Any]:
    payload = {f.name: _encode(getattr(message, f.name)) for f in dataclasses.fields(message)}
    return {"type": message.message_type, "id": id or new_id(), "at": (at or utc_now()).isoformat(), "payload": payload}


def decode(data: object) -> Envelope:
    """Validate and decode a received message; anything off-contract is a `ContractError`."""
    if not isinstance(data, dict) or set(data) != {"type", "id", "at", "payload"}:
        raise ContractError("a message is an object with exactly type, id, at and payload")
    cls = Message._registry.get(data["type"]) if isinstance(data["type"], str) else None
    if cls is None:
        raise ContractError(f"unknown message type {data['type']!r}")
    if not isinstance(data["id"], str) or not 0 < len(data["id"]) <= 64:
        raise ContractError("message id must be a non-empty string of at most 64 characters")
    try:
        at = datetime.fromisoformat(data["at"])
    except (TypeError, ValueError):
        raise ContractError(f"message time {data['at']!r} is not an ISO 8601 date-time") from None
    payload = data["payload"]
    hints = get_type_hints(cls, include_extras=True)
    fields = {f.name: f for f in dataclasses.fields(cls)}
    if not isinstance(payload, dict) or set(payload) - fields.keys():
        raise ContractError(f"{cls.message_type}: unexpected payload {payload!r}")
    missing = [n for n, f in fields.items() if n not in payload and _required(f)]
    if missing:
        raise ContractError(f"{cls.message_type}: missing {', '.join(missing)}")
    values = {name: _decode(value, hints[name], f"{cls.message_type}.{name}") for name, value in payload.items()}
    return Envelope(cls(**values), data["id"], at)


def write_schemas(folder: Path = SCHEMAS) -> list[Path]:
    """Regenerate the published schemas (`nestor satellites schemas`); returns the files written."""
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in schemas().items():
        path = folder / name
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
        written.append(path)
    return written


def schemas() -> dict[str, dict[str, Any]]:
    """The published JSON Schemas, by file name: one per message type, the manifest, and the pairing bodies."""
    found = {"manifest.json": {**_header("manifest.json", "Satellite manifest"), **Manifest.json_schema()}}
    found |= _pairing_schemas()
    for message_type, cls in sorted(Message._registry.items()):
        name = f"{message_type}.json"
        hints = get_type_hints(cls, include_extras=True)
        fields = dataclasses.fields(cls)
        payload = {
            "type": "object",
            "properties": {f.name: _schema(hints[f.name]) for f in fields},
            "required": [f.name for f in fields if _required(f)],
            "additionalProperties": False,
        }
        found[name] = {
            **_header(name, (cls.__doc__ or message_type).strip().splitlines()[0]),
            "x-direction": cls.direction.value,
            "type": "object",
            "properties": {
                "type": {"const": message_type},
                "id": {"type": "string", "minLength": 1, "maxLength": 64},
                "at": {"type": "string", "format": "date-time"},
                "payload": payload,
            },
            "required": ["type", "id", "at", "payload"],
            "additionalProperties": False,
        }
    return found


def _header(name: str, title: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_BASE + name,
        "title": title,
        "x-protocol": PROTOCOL,
    }


def _required(field: dataclasses.Field[Any]) -> bool:
    return field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


def _encode(value: object) -> Any:
    return value.to_json() if isinstance(value, Manifest) else codec.encode(value)


def _unwrap(hint: Any) -> tuple[Any, Bounds | None]:
    if isinstance(hint, typing.TypeAliasType):
        hint = hint.__value__
    if get_origin(hint) is Annotated:
        base, *extras = get_args(hint)
        return base, next((e for e in extras if isinstance(e, Bounds)), None)
    return hint, None


def _decode(value: object, hint: Any, where: str) -> Any:
    base, bounds = _unwrap(hint)
    if base is Manifest:
        return Manifest.from_json(value)
    if base in (int, float) and (isinstance(value, bool) or not isinstance(value, int | float)):
        raise ContractError(f"{where}: expected a number, got {value!r}")
    if base is int and not isinstance(value, int):
        raise ContractError(f"{where}: expected an integer, got {value!r}")
    try:
        decoded = codec.decode(value, base)  # ty: ignore[invalid-argument-type]
    except ContractError as error:
        raise ContractError(f"{where}: {error}") from None
    if bounds is not None and (
        (bounds.minimum is not None and decoded < bounds.minimum)
        or (bounds.maximum is not None and decoded > bounds.maximum)
    ):
        raise ContractError(f"{where}: {decoded!r} is outside [{bounds.minimum}, {bounds.maximum}]")
    return decoded


def _schema(hint: Any) -> dict[str, Any]:
    base, bounds = _unwrap(hint)
    if base is Manifest:
        return {"$ref": "manifest.json"}
    if get_origin(base) is tuple:
        return {"type": "array", "items": _schema(get_args(base)[0])}
    if isinstance(base, type) and issubclass(base, enum.Enum):
        return {"enum": [m.value for m in base]}
    schema: dict[str, Any] = {str: {"type": "string"}, bool: {"type": "boolean"}, int: {"type": "integer"},
                              float: {"type": "number"}}[base]  # fmt: skip
    if bounds is not None:
        schema |= {k: v for k, v in (("minimum", bounds.minimum), ("maximum", bounds.maximum)) if v is not None}
    return schema
