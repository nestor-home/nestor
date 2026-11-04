"""The core's side of a satellite's link, and the body it drives."""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from fastapi import WebSocket

from nestor.adapters.channels.satellites.link import RemoteBody, SatelliteLink
from nestor.core import Capability, Event, utc_now
from nestor.modules.behavior import EXPRESSION, HEAD_MOTION, Behavior, Body, Expression
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    PERSON_DETECTION,
    SPEECH_ACTIVITY,
    TEXT_INPUT,
    UPDATE,
    Device,
    Manifest,
    PersonDetected,
    Satellite,
    SatelliteConnected,
    SatelliteDisconnected,
    SatelliteUpdateReported,
    Software,
    SpeechActivityObserved,
    UpdateState,
    UpdateStatus,
    wire,
)
from nestor.testing.behavior import BodyContract
from nestor.testing.journal import MemoryEventLog
from nestor.testing.satellites import SOFTWARE

from .voice.doubles import FakeLink

ALLOWED = frozenset({Capability("audio.capture"), EXPRESSION, PERSON_DETECTION, SPEECH_ACTIVITY, TEXT_INPUT})
CUISINE = Satellite(
    id="enceinte-cuisine",
    model="raspberry-pi-4",
    room="cuisine",
    capabilities=ALLOWED,
    token_hash="unused",
    paired_at=utc_now(),
    software=SOFTWARE,
)
MANIFEST = Manifest(Device(CUISINE.id, CUISINE.model, "cuisine"), software=Software("nestor-satellite", "0.5.0"))


class Socket:
    """A WebSocket whose device side is the test: what the core sends is kept, what the device sends
    is delivered by the test."""

    def __init__(self) -> None:
        self.sent: list[wire.Envelope] = []
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def receive(self) -> dict[str, Any]:
        return await self._inbox.get()

    async def send_text(self, text: str) -> None:
        self.sent.append(wire.decode(json.loads(text)))

    def deliver(self, data: Any) -> None:
        self._inbox.put_nowait(
            {"type": "websocket.receive", "text": data if isinstance(data, str) else json.dumps(data)}
        )

    def leave(self) -> None:
        self._inbox.put_nowait({"type": "websocket.disconnect"})

    def messages(self) -> list[wire.Message]:
        return [e.message for e in self.sent]


@pytest.fixture
def journal() -> Journal:
    return Journal(MemoryEventLog())


@asynccontextmanager
async def linked(
    journal: Journal, allowed: frozenset[Capability] = ALLOWED, typed: list[str] | None = None, **options: Any
) -> AsyncGenerator[tuple[SatelliteLink, Socket]]:
    """A running link; `typed` collects the texts it answers. It ends when the device leaves."""
    socket = Socket()
    link = SatelliteLink(cast(WebSocket, socket), CUISINE, MANIFEST, journal, allowed=allowed, **options)

    async def answer(_link: SatelliteLink, text: str) -> None:
        if typed is not None:
            typed.append(text)

    running = asyncio.create_task(link.run(answer))
    await settle()
    try:
        yield link, socket
    finally:
        socket.leave()
        await asyncio.wait_for(running, 5)


async def logged(journal: Journal, *types: type[Event]) -> list[Event]:
    return list(await journal.history(*types))


async def settle() -> None:
    """Let the link read and write what is waiting."""
    for _ in range(10):
        await asyncio.sleep(0)


async def test_the_device_is_welcomed_with_its_paired_room_and_what_it_may_do(journal: Journal) -> None:
    async with linked(journal, frozenset({EXPRESSION})) as (_, socket):
        pass
    assert socket.messages() == [wire.Welcome(device_id=CUISINE.id, room="cuisine", capabilities=(EXPRESSION,))]
    connected, disconnected = await logged(journal, SatelliteConnected, SatelliteDisconnected)
    assert isinstance(connected, SatelliteConnected) and isinstance(disconnected, SatelliteDisconnected)
    assert (connected.room, disconnected.room) == ("cuisine", "cuisine")
    assert (connected.software, connected.protocol) == (MANIFEST.software, "nestor.satellite/1")


async def test_a_second_hello_on_a_link_is_ignored(journal: Journal) -> None:
    hello = wire.Hello(manifest=Manifest(Device("reachy-salon", "x", "salon"), software=SOFTWARE), token="nst1_x")
    async with linked(journal) as (_, socket):
        socket.deliver(wire.encode(hello))
        await settle()
    assert [type(m) for m in socket.messages()] == [wire.Welcome]


async def test_observations_are_journaled_as_coming_from_the_paired_device_and_room(journal: Journal) -> None:
    async with linked(journal) as (_, socket):
        socket.deliver(wire.encode(wire.PersonObservation(count=2, confidence=0.8)))
        socket.deliver(wire.encode(wire.SpeechActivityObservation(active=True)))
        await settle()

    person, speech = await logged(journal, PersonDetected, SpeechActivityObserved)
    assert isinstance(person, PersonDetected) and isinstance(speech, SpeechActivityObserved)
    assert (person.device_id, person.room, person.count, person.confidence) == (CUISINE.id, "cuisine", 2, 0.8)
    assert (speech.room, speech.active) == ("cuisine", True)


async def test_typed_text_becomes_turns_in_order_when_allowed(journal: Journal) -> None:
    typed: list[str] = []
    async with linked(journal, typed=typed) as (_, socket):
        socket.deliver(wire.encode(wire.TextInput(text="Allume la cuisine")))
        socket.deliver(wire.encode(wire.TextInput(text="Et le salon")))
        await settle()
    assert typed == ["Allume la cuisine", "Et le salon"]

    silent: list[str] = []
    async with linked(journal, ALLOWED - {TEXT_INPUT}, typed=silent) as (_, socket):
        socket.deliver(wire.encode(wire.TextInput(text="Allume la cuisine")))
        await settle()
    assert not silent, "a device not allowed to type is not heard"


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
    async with linked(journal) as (_, socket):
        socket.deliver(data)
        await settle()
    assert [type(m) for m in socket.messages()] == [wire.Welcome]
    assert not await logged(journal, PersonDetected, SpeechActivityObserved)


async def test_an_observation_the_device_was_not_allowed_is_ignored(journal: Journal) -> None:
    async with linked(journal, frozenset({EXPRESSION})) as (_, socket):
        socket.deliver(wire.encode(wire.PersonObservation(count=1, confidence=0.9)))
        await settle()
    assert not await logged(journal, PersonDetected)


async def test_acknowledged_intents_are_settled_and_overdue_ones_forgotten(journal: Journal) -> None:
    async with linked(journal, ack_timeout_s=60) as (link, socket):
        link.send(wire.BehaviorIntent(behavior=Behavior.SPEAKING))
        link.send(wire.BeatIntent())
        await settle()
        socket.deliver(wire.encode(wire.Ack(of=socket.sent[1].id)))
        await settle()
        assert link.unacknowledged == ["intent.beat"]

    impatient = SatelliteLink(cast(WebSocket, Socket()), CUISINE, MANIFEST, journal, allowed=ALLOWED, ack_timeout_s=0)
    impatient.send(wire.BeatIntent())
    impatient.send(wire.BeatIntent())
    assert impatient.unacknowledged == ["intent.beat"], "the first beat was given up on"


class BrokenLink(FakeLink):
    def send(self, message: wire.Message) -> None:
        raise ConnectionError("the device is gone")


def body_for(capabilities: frozenset[Capability], link: FakeLink | None = None) -> tuple[RemoteBody, FakeLink]:
    link = link or FakeLink(*capabilities)
    return RemoteBody(cast(SatelliteLink, link)), link


class TestRemoteBody(BodyContract):
    def body(self) -> Body:
        return body_for(frozenset({EXPRESSION, HEAD_MOTION}))[0]


async def test_a_body_sends_what_the_device_was_allowed_and_rests_when_closed() -> None:
    expressive, link = body_for(frozenset({EXPRESSION}))
    expressive.set_behavior(Behavior.SPEAKING)
    expressive.set_behavior(Behavior.SPEAKING)
    expressive.express(Expression.JOY)
    expressive.beat()  # no head to nod with
    await expressive.close()
    expressive.express(Expression.JOY)

    assert [m.message_type for m in link.sent] == ["intent.behavior", "intent.expression", "intent.behavior"]
    assert link.sent[-1] == wire.BehaviorIntent(behavior=Behavior.IDLE)

    nodding, link = body_for(frozenset({HEAD_MOTION}))
    nodding.express(Expression.JOY)
    nodding.beat()
    assert [m.message_type for m in link.sent] == ["intent.beat"]


async def test_a_lost_device_never_breaks_the_conversation() -> None:
    body, _ = body_for(frozenset({EXPRESSION, HEAD_MOTION}), BrokenLink(EXPRESSION, HEAD_MOTION))
    body.set_behavior(Behavior.LISTENING)
    body.express(Expression.SIGH)
    body.beat()


async def test_a_long_answer_is_shown_in_messages_the_protocol_allows(journal: Journal) -> None:
    words = ("mot " * (wire.SHOWN_MAX // 4 + 10)).strip()
    async with linked(journal) as (link, socket):
        link.show(words)
        link.show("  Court.  ")
        await settle()
    shown = [m for m in socket.messages() if isinstance(m, wire.TextIntent)]
    assert [m.final for m in shown] == [False, True, True]
    assert all(len(m.text) <= wire.SHOWN_MAX for m in shown)
    assert " ".join(m.text for m in shown[:2]) == words, "cut between words, nothing lost"
    assert shown[2].text == "Court."


async def test_what_a_device_reports_about_its_software_is_kept_and_journaled_when_it_changes(
    journal: Journal,
) -> None:
    available = wire.UpdateStatusReport(state=UpdateState.AVAILABLE, version="0.6.0", notes="https://x.org/0.6.0")
    async with linked(journal, ALLOWED | {UPDATE}) as (link, socket):
        socket.deliver(wire.encode(available))
        socket.deliver(wire.encode(available))
        await settle()
        assert link.update_status == UpdateStatus(UpdateState.AVAILABLE, "0.6.0", "https://x.org/0.6.0")
        link.update("0.6.0")
        socket.deliver(wire.encode(wire.UpdateStatusReport(state=UpdateState.INSTALLING, version="0.6.0")))
        await settle()
    assert wire.UpdateIntent(version="0.6.0") in socket.messages()
    reported = await logged(journal, SatelliteUpdateReported)
    assert [(e.device_id, e.state, e.target) for e in reported if isinstance(e, SatelliteUpdateReported)] == [
        (CUISINE.id, UpdateState.AVAILABLE, "0.6.0"),
        (CUISINE.id, UpdateState.INSTALLING, "0.6.0"),
    ]


async def test_a_device_not_allowed_to_update_is_not_heard_about_its_software(journal: Journal) -> None:
    async with linked(journal) as (link, socket):
        socket.deliver(wire.encode(wire.UpdateStatusReport(state=UpdateState.AVAILABLE, version="0.6.0")))
        await settle()
        assert link.update_status is None
    assert not await logged(journal, SatelliteUpdateReported)
