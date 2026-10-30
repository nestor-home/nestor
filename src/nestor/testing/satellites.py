"""Conformance of a satellite to the wire protocol, whatever carries the messages.

`ProtocolProbe` plays the core on one connection of the satellite under test: it waits for a valid
`hello` from the paired device, answers `welcome`, sends one intent of each kind the device may
receive (`intent.identify` only to a device allowed `device.identify`) and expects each to be
acknowledged in time, and checks that every message it receives,
observations included, follows the contract. The transport (WebRTC data channel, WebSocket…) only
has to implement `SatelliteSession`; the realtime profile's black-box core lives with the WebRTC
gateway (`nestor.adapters.channels.voice.satellites.conformance`).
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from nestor.core import Capability, ContractError, PersonId
from nestor.modules.behavior import EXPRESSION, HEAD_MOTION, Behavior, Expression
from nestor.modules.satellites import IDENTIFY, PERSON_DETECTION, SPEECH_ACTIVITY, Manifest, Pairing, Satellite, wire

# What a satellite must have been allowed before it reports an observation of that kind.
OBSERVATION_NEEDS: dict[type[wire.Message], Capability] = {
    wire.PersonObservation: PERSON_DETECTION,
    wire.SpeechActivityObservation: SPEECH_ACTIVITY,
}


class SatelliteSession(ABC):
    """One connection of the satellite under test, as the fake core sees it."""

    @abstractmethod
    async def receive(self) -> Any:
        """The next message the satellite sent, as parsed JSON (waits for it)."""

    @abstractmethod
    def send(self, data: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class Findings:
    items: list[Finding] = field(default_factory=list)

    def add(self, check: str, passed: bool, detail: str = "") -> bool:
        self.items.append(Finding(check, passed, detail))
        return passed

    @property
    def passed(self) -> bool:
        return all(f.passed for f in self.items)

    def failures(self) -> list[Finding]:
        return [f for f in self.items if not f.passed]


class ProtocolProbe:
    def __init__(self, *, hello_deadline_s: float = 5.0, ack_deadline_s: float = 1.0, listen_s: float = 1.0) -> None:
        self.hello_deadline_s = hello_deadline_s
        self.ack_deadline_s = ack_deadline_s
        self.listen_s = listen_s

    async def run(
        self, session: SatelliteSession, satellite: Satellite, findings: Findings, *, label: str = ""
    ) -> bool:
        """Check one connection; returns whether its `hello` was valid (the rest depends on it)."""
        reader = _Reader(session, satellite, findings, label)
        first = await reader.next(time.monotonic() + self.hello_deadline_s)
        if not isinstance(first, wire.Hello):
            detail = f"first message: {first.message_type}" if first else "no valid message in time"
            findings.add(f"{label}sends a hello first", False, detail)
            return False
        hello = first
        findings.add(f"{label}sends a hello first", True)
        findings.add(
            f"{label}introduces itself as the paired device",
            hello.manifest.device.id == satellite.id,
            f"hello says {hello.manifest.device.id!r}, paired as {satellite.id!r}",
        )
        session.send(wire.encode(wire.Welcome(device_id=satellite.id, room=satellite.room,
                                              capabilities=tuple(sorted(satellite.capabilities)))))  # fmt: skip
        for intent in _intents_for(satellite.capabilities):
            sent = wire.encode(intent)
            session.send(sent)
            ack = await reader.ack_of(sent["id"], self.ack_deadline_s)
            findings.add(
                f"{label}acknowledges {intent.message_type} within {self.ack_deadline_s:g} s",
                ack,
                "no ack with this intent's id",
            )
        await reader.listen(self.listen_s)
        reader.conclude()
        return True


def _intents_for(capabilities: frozenset[Capability]) -> list[wire.Message]:
    intents: list[wire.Message] = [wire.BehaviorIntent(behavior=Behavior.SPEAKING)]
    if EXPRESSION in capabilities:
        intents.append(wire.ExpressionIntent(expression=Expression.JOY, intensity=0.8))
    if HEAD_MOTION in capabilities:
        intents.append(wire.BeatIntent())
    if IDENTIFY in capabilities:
        intents.append(wire.IdentifyIntent())
    intents.append(wire.BehaviorIntent(behavior=Behavior.IDLE))
    return intents


class _Reader:
    """Reads the satellite's messages, judging each one, and keeps the acks it sees."""

    def __init__(self, session: SatelliteSession, satellite: Satellite, findings: Findings, label: str) -> None:
        self._session, self._satellite, self._findings, self._label = session, satellite, findings, label
        self._acks: set[str] = set()
        self._invalid: list[str] = []

    async def ack_of(self, intent_id: str, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while intent_id not in self._acks:
            if await self.next(deadline) is None:
                return False
        return True

    async def listen(self, duration_s: float) -> None:
        deadline = time.monotonic() + duration_s
        while await self.next(deadline) is not None:
            continue

    def conclude(self) -> None:
        self._findings.add(
            f"{self._label}every message follows the schema", not self._invalid, "; ".join(self._invalid)
        )

    async def next(self, deadline: float) -> wire.Message | None:
        """The next valid message before `deadline`; invalid ones are noted and skipped."""
        while True:
            try:
                data = await asyncio.wait_for(self._session.receive(), max(0.0, deadline - time.monotonic()))
            except TimeoutError:
                return None
            try:
                message = wire.decode(data).message
            except ContractError as error:
                self._invalid.append(str(error))
                continue
            self._judge(message)
            return message

    def _judge(self, message: wire.Message) -> None:
        if message.direction is not wire.Direction.TO_CORE:
            self._invalid.append(f"{message.message_type} is sent by the core, not by satellites")
        elif isinstance(message, wire.Ack):
            self._acks.add(message.of)
        elif (needed := OBSERVATION_NEEDS.get(type(message))) and needed not in self._satellite.capabilities:
            self._invalid.append(f"{message.message_type} needs the {needed} capability")


async def pair_by_code(pairing: Pairing, manifest: Manifest, *, by: PersonId | None = None) -> Satellite:
    """Pair `manifest`'s device the way a person does with its device code: it asks, they type the code."""
    ticket = await pairing.request(manifest)
    assert ticket.device_code is not None
    return await pairing.approve(ticket.device_code, pairing_id=ticket.id, by=by)
