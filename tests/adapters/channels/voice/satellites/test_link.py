"""The core's side of a satellite's data channel, and the body it drives."""

import asyncio
from typing import Any

import pytest
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from nestor.adapters.channels.voice.satellites import RemoteBody, SatelliteLink
from nestor.core import Capability, Event, utc_now
from nestor.modules.behavior import EXPRESSION, HEAD_MOTION, Behavior, Body, Expression
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    Device,
    Manifest,
    PersonDetected,
    Satellite,
    SatelliteConnected,
    SatelliteDisconnected,
    SpeechActivityObserved,
    wire,
)
from nestor.testing.behavior import BodyContract
from nestor.testing.journal import MemoryEventLog

CUISINE = Satellite(
    id="enceinte-cuisine",
    model="raspberry-pi-4",
    room="cuisine",
    capabilities=frozenset({Capability("audio.capture"), EXPRESSION}),
    token_hash="unused",
    paired_at=utc_now(),
)


class Wire(SmallWebRTCConnection):
    """A peer connection that is never negotiated: what the core sends is kept, what the device
    sends is delivered by the test."""

    def __init__(self, *, broken: bool = False) -> None:
        super().__init__()
        self.sent: list[wire.Envelope] = []
        self._broken = broken

    def send_app_message(self, message: Any) -> None:
        if self._broken:
            raise ConnectionError("the device is gone")
        self.sent.append(wire.decode(message))

    async def deliver(self, data: Any) -> None:
        await self._call_event_handler("app-message", data)

    def kinds(self) -> list[str]:
        return [e.message.message_type for e in self.sent]


def hello(device_id: str = CUISINE.id) -> dict[str, Any]:
    return wire.encode(wire.Hello(manifest=Manifest(Device(device_id, "raspberry-pi-4", "salon"))))


async def logged(journal: Journal, *types: type[Event]) -> list[Event]:
    return list(await journal.history(*types))


async def settle() -> None:
    """Let the link read what was delivered."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


async def test_a_hello_from_the_paired_device_is_welcomed_with_its_paired_room(journal: Journal) -> None:
    connection = Wire()
    link = SatelliteLink(connection, CUISINE, journal)
    await connection.deliver(hello())
    await connection.deliver(hello())  # a repeated hello is welcomed again, but it is one connection
    await settle()
    await link.close()

    welcome = connection.sent[0].message
    assert welcome == wire.Welcome(device_id=CUISINE.id, room="cuisine", capabilities=("audio.capture", EXPRESSION))
    connected, disconnected = await logged(journal, SatelliteConnected, SatelliteDisconnected)
    assert isinstance(connected, SatelliteConnected) and isinstance(disconnected, SatelliteDisconnected)
    assert (connected.room, disconnected.room) == ("cuisine", "cuisine")


async def test_a_device_claiming_another_identity_is_not_welcomed(journal: Journal) -> None:
    connection = Wire()
    link = SatelliteLink(connection, CUISINE, journal)
    await connection.deliver(hello("reachy-salon"))
    await settle()
    await link.close()
    assert not connection.sent
    assert not await logged(journal, SatelliteConnected, SatelliteDisconnected)


async def test_observations_are_journaled_as_coming_from_the_paired_device_and_room(journal: Journal) -> None:
    connection = Wire()
    SatelliteLink(connection, CUISINE, journal)
    await connection.deliver(wire.encode(wire.PersonObservation(count=2, confidence=0.8)))
    await connection.deliver(wire.encode(wire.SpeechActivityObservation(active=True)))
    await settle()

    person, speech = await logged(journal, PersonDetected, SpeechActivityObserved)
    assert isinstance(person, PersonDetected) and isinstance(speech, SpeechActivityObserved)
    assert (person.device_id, person.room, person.count, person.confidence) == (CUISINE.id, "cuisine", 2, 0.8)
    assert (speech.room, speech.active) == ("cuisine", True)


@pytest.mark.parametrize(
    "data",
    [
        {"type": "observation.mood", "id": "1", "at": "2026-10-30T12:00:00+00:00", "payload": {}},
        wire.encode(wire.BehaviorIntent(behavior=Behavior.IDLE)),  # only the core sends intents
        "ping",
    ],
    ids=["unknown observation", "an intent", "not json"],
)
async def test_off_contract_messages_are_ignored(data: Any, journal: Journal) -> None:
    connection = Wire()
    SatelliteLink(connection, CUISINE, journal)
    await connection.deliver(data)
    await settle()
    assert not connection.sent
    assert not await logged(journal, PersonDetected, SpeechActivityObserved, SatelliteConnected)


async def test_acknowledged_intents_are_settled_and_overdue_ones_forgotten(journal: Journal) -> None:
    connection = Wire()
    link = SatelliteLink(connection, CUISINE, journal, ack_timeout_s=60)
    link.send(wire.BehaviorIntent(behavior=Behavior.SPEAKING))
    link.send(wire.BeatIntent())
    await connection.deliver(wire.encode(wire.Ack(of=connection.sent[0].id)))
    await settle()
    assert link.unacknowledged == ["intent.beat"]

    impatient = SatelliteLink(Wire(), CUISINE, journal, ack_timeout_s=0)
    impatient.send(wire.BeatIntent())
    impatient.send(wire.BeatIntent())
    assert impatient.unacknowledged == ["intent.beat"], "the first beat was given up on"


def body_for(capabilities: frozenset[Capability], connection: Wire | None = None) -> tuple[RemoteBody, Wire]:
    connection = connection or Wire()
    satellite = Satellite(
        id="reachy-salon",
        model="reachy-mini",
        room="salon",
        capabilities=capabilities,
        token_hash="",
        paired_at=utc_now(),
    )
    return RemoteBody(SatelliteLink(connection, satellite, Journal(MemoryEventLog()))), connection


class TestRemoteBody(BodyContract):
    def body(self) -> Body:
        return body_for(frozenset({EXPRESSION, HEAD_MOTION}))[0]


async def test_a_body_sends_what_the_device_was_allowed_and_rests_when_closed() -> None:
    expressive, sent = body_for(frozenset({EXPRESSION}))
    expressive.set_behavior(Behavior.SPEAKING)
    expressive.set_behavior(Behavior.SPEAKING)
    expressive.express(Expression.JOY)
    expressive.beat()  # no head to nod with
    await expressive.close()
    expressive.express(Expression.JOY)

    assert sent.kinds() == ["intent.behavior", "intent.expression", "intent.behavior"]
    assert sent.sent[-1].message == wire.BehaviorIntent(behavior=Behavior.IDLE)

    nodding, sent = body_for(frozenset({HEAD_MOTION}))
    nodding.express(Expression.JOY)
    nodding.beat()
    assert sent.kinds() == ["intent.beat"]


async def test_a_lost_device_never_breaks_the_conversation() -> None:
    body, _ = body_for(frozenset({EXPRESSION, HEAD_MOTION}), Wire(broken=True))
    body.set_behavior(Behavior.LISTENING)
    body.express(Expression.SIGH)
    body.beat()
