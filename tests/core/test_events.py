"""The event log contract: every event type survives a JSON round trip; invalid records are refused."""

import dataclasses
import enum
import json
import types
import typing
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any, get_args, get_origin, get_type_hints

import pytest

import nestor.modules.behavior
import nestor.modules.cognition
import nestor.modules.cognition.tools
import nestor.modules.conversation
import nestor.modules.home
import nestor.modules.identity
import nestor.modules.initiative
import nestor.modules.memory  # noqa: F401  (importing a module registers its events)
from nestor.core import ContractError, Event, Record, SessionId
from nestor.modules.cognition import TaskEnded, TaskStatus

ENVELOPE = {"source", "session", "id", "at"}


def sample(hint: Any) -> Any:
    """A non-trivial value for a payload field, so that every decoding path is exercised."""
    while hasattr(hint, "__supertype__"):
        hint = hint.__supertype__
    origin, args = get_origin(hint), get_args(hint)
    if origin in (typing.Union, types.UnionType):
        return sample(next(a for a in args if a is not type(None)))
    if origin is tuple:
        return (sample(args[0]),)
    if origin in (dict, typing.Mapping, __import__("collections.abc").abc.Mapping):
        return {"pièce": "salon", "niveaux": [1, 2]}
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return list(hint)[-1]
    if dataclasses.is_dataclass(hint):
        hints = get_type_hints(hint)
        return hint(**{f.name: sample(hints[f.name]) for f in dataclasses.fields(hint)})
    samples: dict[Any, Any] = {
        str: "texte accentué",
        float: 1.25,
        int: 3,
        bool: True,
        datetime: datetime(2026, 10, 30, 18, 30, tzinfo=UTC),
    }
    return samples[hint]


@pytest.mark.parametrize("cls", sorted(Event.types().values(), key=lambda c: c.event_type), ids=lambda c: c.event_type)
def test_every_event_type_survives_the_log(cls: type[Event]) -> None:
    hints = get_type_hints(cls)
    payload = {f.name: sample(hints[f.name]) for f in fields(cls) if f.name not in ENVELOPE}
    event = cls(source="test", session=SessionId("s1"), **payload)

    record = json.loads(json.dumps(event.to_record()))

    assert record["type"] == cls.event_type
    assert Event.from_record(record) == event


def task_ended_record(**overrides: Any) -> dict[str, Any]:
    event = TaskEnded(source="test", task_id="t1", status=TaskStatus.COMPLETED, result="ok", duration_s=2.0)
    return {**json.loads(json.dumps(event.to_record())), **overrides}


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"type": "task.unknown"}, "unknown event type"),
        ({"version": 99}, "migrate the log"),
        ({"payload": {"task_id": "t1", "colour": "red"}}, "invalid payload"),
        ({"payload": {"task_id": "t1", "status": "exploded", "duration_s": 1}}, "exploded"),
        ({"payload": {"task_id": ["t1"], "status": "completed", "duration_s": 1}}, "cannot decode"),
    ],
    ids=["unknown-type", "newer-version", "unknown-field", "invalid-enum", "corrupted-value"],
)
def test_an_invalid_record_is_refused_with_its_reason(overrides: dict[str, Any], reason: str) -> None:
    with pytest.raises(ContractError, match=reason):
        Event.from_record(task_ended_record(**overrides))


def test_an_event_type_can_only_be_defined_once() -> None:
    with pytest.raises(ContractError, match="already defined by TaskEnded"):

        class Duplicate(Event, event_type="task.ended"):
            task_id: str


def test_a_payload_that_is_not_plain_data_cannot_be_logged() -> None:
    class Opaque(Event, event_type="test.opaque"):
        value: object

    with pytest.raises(ContractError, match="cannot encode set"):
        Opaque(source="test", value={1, 2}).to_record()


def test_a_rich_payload_survives_the_log() -> None:
    from dataclasses import dataclass
    from datetime import UTC, datetime

    @dataclass(frozen=True)
    class Call:
        name: str
        arguments: dict[str, object]

    class Scheduled(Event, event_type="test.scheduled"):
        call: Call
        due: datetime
        attempts: tuple[int, ...]
        context: object = None

    event = Scheduled(
        source="test",
        call=Call("set_light", {"room": "salon", "levels": [1, 2]}),
        due=datetime(2026, 10, 29, 18, 30, tzinfo=UTC),
        attempts=(1, 2),
        context={"free": "form"},
    )

    assert Event.from_record(json.loads(json.dumps(event.to_record()))) == event


def test_an_older_record_is_upgraded_as_it_is_read_and_a_too_new_one_refused() -> None:
    from nestor.core import Event
    from nestor.core.i18n import Message
    from nestor.modules.connectors import ConnectionChanged
    from nestor.modules.initiative import DeliveryConsidered

    def v1(type: str, payload: dict) -> dict:
        return {
            "type": type,
            "version": 1,
            "id": type,
            "at": "2026-10-30T10:00:00+00:00",
            "source": "s",
            "session": None,
            "payload": payload,
        }

    changed = {"connection_id": "c1", "status": "needs_reauth"}
    empty = Event.from_record(v1("connection.changed", {**changed, "reason": ""}))
    assert isinstance(empty, ConnectionChanged) and empty.reason is None and empty.status == "needs_reauth"
    refused = Event.from_record(v1("connection.changed", {**changed, "reason": "refresh refused by the provider"}))
    assert isinstance(refused, ConnectionChanged) and refused.reason == Message.of("connection-refresh-refused")
    odd = Event.from_record(v1("connection.changed", {**changed, "reason": "bad gateway"}))
    assert isinstance(odd, ConnectionChanged) and odd.reason == Message.of(
        "connection-reason-other", detail="bad gateway"
    )
    for text, expected in (
        ("Mathis is in the salon", Message.of("delivery-in-room", person="Mathis", room="salon")),
        ("Mathis is away", Message.of("delivery-away", person="Mathis")),
        ("quiet hours: nothing spoken", Message.of("delivery-quiet-hours")),
        (
            "Mathis is home, room unknown: main satellite",
            Message.of("delivery-other", reason="Mathis is home, room unknown: main satellite"),
        ),
    ):
        considered = Event.from_record(v1("initiative.considered", {"about": "watch w1", "reason": text}))
        assert isinstance(considered, DeliveryConsidered) and considered.reason == expected, text


class Bumped(Event, event_type="testing.bumped", version=2):
    note: str


def test_an_event_that_bumped_its_version_without_upgrading_refuses_its_older_records() -> None:
    record: Record = {
        "type": "testing.bumped",
        "version": 1,
        "id": "b",
        "at": "2026-10-30T10:00:00+00:00",
        "source": "s",
        "session": None,
        "payload": {"note": "x"},
    }
    with pytest.raises(ContractError, match="cannot be upgraded"):
        Event.from_record(record)
    with pytest.raises(ContractError, match="invalid payload"):
        Event.from_record({**record, "type": "connection.changed", "payload": "garbled"})
