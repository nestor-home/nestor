import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from nestor.core import Capability, ContractError
from nestor.modules.behavior import Behavior, Expression
from nestor.modules.satellites import Device, Manifest, Sdk, wire
from nestor.modules.satellites.types import DeclaredCapability

MANIFEST = Manifest(
    Device("reachy-salon", "reachy-mini", "salon"),
    (DeclaredCapability(Capability("audio.capture"), {"formats": ["opus/48000"]}),),
)
MESSAGES: list[wire.Message] = [
    wire.Hello(manifest=MANIFEST),
    wire.Ack(of="intent-1"),
    wire.PersonObservation(count=2, confidence=0.9),
    wire.SpeechActivityObservation(active=True),
    wire.Welcome(device_id="reachy-salon", room="salon", capabilities=("audio.capture",)),
    wire.BehaviorIntent(behavior=Behavior.LISTENING),
    wire.ExpressionIntent(expression=Expression.JOY, intensity=0.7),
    wire.BeatIntent(),
]


def validator(message_type: str) -> Any:
    published = wire.schemas()
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in published.values()
    )
    return Draft202012Validator(published[f"{message_type}.json"], registry=registry)


def test_every_message_type_is_covered_here() -> None:
    assert {m.message_type for m in MESSAGES} == set(wire.Message.types())


@pytest.mark.parametrize("message", MESSAGES, ids=lambda m: m.message_type)
def test_a_message_survives_the_wire_and_matches_its_published_schema(message: wire.Message) -> None:
    sent = json.loads(json.dumps(wire.encode(message, id="m-1")))
    received = wire.decode(sent)
    assert (received.message, received.id) == (message, "m-1")
    validator(message.message_type).validate(sent)


def test_a_manifest_keeps_the_parameters_of_its_capabilities() -> None:
    sent = wire.encode(wire.Hello(manifest=MANIFEST))
    assert sent["payload"]["manifest"]["capabilities"] == [{"name": "audio.capture", "formats": ["opus/48000"]}]


def test_a_manifest_may_name_its_maker_and_its_software() -> None:
    manifest = Manifest(
        Device("reachy", "reachy-mini", "salon", brand="pollen-robotics"), sdk=Sdk("nestor-reachy", "0.1.0")
    )
    data = wire.encode(wire.Hello(manifest=manifest))
    assert validator("hello").is_valid(data)
    decoded = wire.decode(data).message
    assert isinstance(decoded, wire.Hello) and decoded.manifest == manifest


def _with(message: wire.Message, **payload: Any) -> dict[str, Any]:
    data = wire.encode(message)
    data["payload"] = {**data["payload"], **payload}
    return data


def _manifest(**changes: Any) -> dict[str, Any]:
    data = wire.encode(wire.Hello(manifest=MANIFEST))
    data["payload"]["manifest"] = {**data["payload"]["manifest"], **changes}
    return data


OFF_CONTRACT = {
    "out of bounds": _with(wire.ExpressionIntent(expression=Expression.JOY), intensity=1.5),
    "negative count": _with(wire.PersonObservation(count=1, confidence=0.5), count=-1),
    "boolean as a number": _with(wire.PersonObservation(count=1, confidence=0.5), count=True),
    "fractional count": _with(wire.PersonObservation(count=1, confidence=0.5), count=1.5),
    "text as a number": _with(wire.PersonObservation(count=1, confidence=0.5), confidence="high"),
    "unknown expression": _with(wire.ExpressionIntent(expression=Expression.JOY), expression="anger"),
    "unexpected field": _with(wire.Ack(of="x"), extra=1),
    "missing field": {**wire.encode(wire.Ack(of="x")), "payload": {}},
    "other protocol": _manifest(protocol="nestor.satellite/2"),
    "device id with a colon": _manifest(device={"id": "voice:salon", "model": "m", "room": "salon"}),
    "capability without a family": _manifest(capabilities=[{"name": "camera"}]),
    "unexpected manifest key": _manifest(firmware="1.2"),
    "sdk as text": _manifest(sdk="nestor-reachy 0.1.0"),
    "sdk without a version": _manifest(sdk={"name": "nestor-reachy"}),
    "empty sdk version": _manifest(sdk={"name": "nestor-reachy", "version": ""}),
    "brand that is not a slug": _manifest(
        device={"id": "d", "model": "m", "room": "salon", "brand": "Pollen Robotics"}
    ),
}


@pytest.mark.parametrize("data", OFF_CONTRACT.values(), ids=OFF_CONTRACT.keys())
def test_off_contract_payloads_are_refused_by_the_code_and_by_the_schema(data: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        wire.decode(data)
    assert not validator(data["type"]).is_valid(data)


@pytest.mark.parametrize(
    "data",
    [
        {"type": "intent.dance", "id": "1", "at": "2026-10-30T12:00:00+00:00", "payload": {}},
        {"type": "ack", "id": "", "at": "2026-10-30T12:00:00+00:00", "payload": {"of": "x"}},
        {"type": "ack", "id": "1", "at": "yesterday", "payload": {"of": "x"}},
        {"type": "ack", "id": "1", "at": "2026-10-30T12:00:00+00:00", "payload": {"of": "x"}, "from": "me"},
        ["not", "an", "object"],
    ],
    ids=["unknown type", "empty id", "bad time", "extra envelope key", "not an object"],
)
def test_malformed_envelopes_are_refused(data: object) -> None:
    with pytest.raises(ContractError):
        wire.decode(data)


@pytest.mark.parametrize(
    "manifest",
    [
        {"protocol": "nestor.satellite/1", "device": {"id": "a", "model": "", "room": "salon"}},
        {"protocol": "nestor.satellite/1", "device": {"id": "a", "model": "m"}},
        {"protocol": "nestor.satellite/1", "device": {"id": "a", "model": "m", "room": "s"}, "capabilities": "all"},
        {
            "protocol": "nestor.satellite/1",
            "device": {"id": "a", "model": "m", "room": "s"},
            "capabilities": [{"name": "audio.capture"}, {"name": "audio.capture"}],
        },
    ],
    ids=["empty model", "no room", "capabilities not a list", "declared twice"],
)
def test_invalid_manifests_are_refused(manifest: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        Manifest.from_json(manifest)


def test_the_committed_schemas_are_up_to_date() -> None:
    committed = {p.name: json.loads(p.read_text()) for p in wire.SCHEMAS.glob("*.json")}
    assert committed == wire.schemas(), "run `nestor satellites schemas` (wire.write_schemas()) and commit"


def test_schemas_are_written_where_asked(tmp_path: Any) -> None:
    written = wire.write_schemas(tmp_path)
    assert {p.name for p in written} == set(wire.schemas())


def test_a_message_type_is_defined_once() -> None:
    with pytest.raises(ContractError):

        class _Again(wire.Message, message_type="ack", direction=wire.Direction.TO_CORE):
            of: str
