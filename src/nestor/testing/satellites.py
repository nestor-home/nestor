"""Conformance of a satellite to the wire protocol, whatever carries the messages.

`ProtocolProbe` plays the core on one link of the satellite under test, once the gateway accepted its
`hello`: it answers `welcome`, sends one intent of each kind the device may receive
(`intent.identify` only to a device allowed `device.identify`, `intent.text` only to one allowed
`text.display`, `intent.update` for a version it never reported only to one allowed `device.update`)
and expects each to be acknowledged in time, and checks that every message it receives, observations
and typed text included, follows the contract and what the device was allowed. A device allowed
`device.update` must also report where its software stands, and never install a version it did not
report. Each finding is a `Message` (catalogue `conformance.ftl`), so whoever shows it renders it in
the reader's language. The link only has to implement `SatelliteSession`; the black-box core lives
with the gateway (`nestor.adapters.channels.satellites.conformance`).
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from nestor.core import Capability, ContractError, PersonId
from nestor.core.i18n import Message
from nestor.modules.behavior import EXPRESSION, HEAD_MOTION, Behavior, Expression
from nestor.modules.satellites import (
    IDENTIFY,
    TEXT_DISPLAY,
    UPDATE,
    Manifest,
    Online,
    Pairing,
    Satellite,
    Software,
    UpdateState,
    wire,
)

SOFTWARE = Software("nestor-test-satellite", "1.0.0")  # what test devices declare they run


class RecordingDevice(Online):
    """A connected device as the pairing service reaches it: it notes what it is asked."""

    def __init__(self) -> None:
        self.identified = 0
        self.updates: list[str] = []  # the versions it was asked to install

    def identify(self) -> None:
        self.identified += 1

    def update(self, version: str) -> None:
        self.updates.append(version)


UNREPORTED = "0.0.0"  # the version `intent.update` asks for: never reported, older than any (U2)


class SatelliteSession(ABC):
    """One connection of the satellite under test, as the fake core sees it."""

    @abstractmethod
    async def receive(self) -> Any:
        """The next message the satellite sent, as parsed JSON (waits for it)."""

    @abstractmethod
    def send(self, data: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class Finding:
    """One check: what was checked (its id names the check, whatever the language), whether it held,
    and, when it did not, what was seen instead."""

    check: Message
    passed: bool
    detail: Message | None = None


@dataclass(slots=True)
class Findings:
    items: list[Finding] = field(default_factory=list)

    def add(self, check: Message, passed: bool, detail: Message | None = None) -> bool:
        self.items.append(Finding(check, passed, detail))
        return passed

    @property
    def passed(self) -> bool:
        return all(f.passed for f in self.items)

    def failures(self) -> list[Finding]:
        return [f for f in self.items if not f.passed]


class ProtocolProbe:
    def __init__(self, *, ack_deadline_s: float = 1.0, listen_s: float = 1.0) -> None:
        self.ack_deadline_s = ack_deadline_s
        self.listen_s = listen_s
        self._allowed: dict[int, frozenset[Capability]] = {}

    def welcome(self, session: SatelliteSession, satellite: Satellite, allowed: frozenset[Capability]) -> None:
        """Answer the link's accepted `hello`: where the device is and what it may do."""
        self._allowed[id(session)] = allowed
        session.send(wire.encode(wire.Welcome(device_id=satellite.id, room=satellite.room,
                                              capabilities=tuple(sorted(allowed)))))  # fmt: skip

    async def run(
        self, session: SatelliteSession, satellite: Satellite, findings: Findings, *, connection: str = "paired"
    ) -> None:
        """Check one welcomed link. `connection` says which one it is in the findings: `paired` (the
        first after pairing with a device code), `reconnected` or `enrolled` (after pairing with an
        enrollment code)."""
        allowed = self._allowed.get(id(session), satellite.capabilities)
        reader = _Reader(session, allowed, findings, connection)
        for intent in _intents_for(allowed):
            sent = wire.encode(intent)
            session.send(sent)
            ack = await reader.ack_of(sent["id"], self.ack_deadline_s)
            findings.add(
                Message.of("conformance-acknowledges", connection=connection, intent=intent.message_type,
                           seconds=self.ack_deadline_s),
                ack,
                Message.of("conformance-no-ack"),
            )  # fmt: skip
        await reader.listen(self.listen_s)
        if UPDATE in allowed:
            findings.add(Message.of("conformance-reports-update", connection=connection), bool(reader.updates),
                         Message.of("conformance-no-update-status"))  # fmt: skip
            installed = any(u.state is not UpdateState.CURRENT and u.version == UNREPORTED for u in reader.updates)
            findings.add(Message.of("conformance-installs-only-found", connection=connection), not installed,
                         Message.of("conformance-installed-unreported", version=UNREPORTED))  # fmt: skip
        reader.conclude()


def _intents_for(capabilities: frozenset[Capability]) -> list[wire.Message]:
    intents: list[wire.Message] = [wire.BehaviorIntent(behavior=Behavior.SPEAKING)]
    if EXPRESSION in capabilities:
        intents.append(wire.ExpressionIntent(expression=Expression.JOY, intensity=0.8))
    if HEAD_MOTION in capabilities:
        intents.append(wire.BeatIntent())
    if IDENTIFY in capabilities:
        intents.append(wire.IdentifyIntent())
    if TEXT_DISPLAY in capabilities:
        intents.append(wire.TextIntent(text="Hello."))
    if UPDATE in capabilities:
        intents.append(wire.UpdateIntent(version=UNREPORTED))
    intents.append(wire.BehaviorIntent(behavior=Behavior.IDLE))
    return intents


class _Reader:
    """Reads the satellite's messages, judging each one, and keeps the acks it sees."""

    def __init__(
        self, session: SatelliteSession, allowed: frozenset[Capability], findings: Findings, connection: str
    ) -> None:
        self._session, self._allowed, self._findings, self._connection = session, allowed, findings, connection
        self._acks: set[str] = set()
        self._invalid: list[str] = []
        self.updates: list[wire.UpdateStatusReport] = []  # what it reported about its software

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
            Message.of("conformance-follows-schema", connection=self._connection),
            not self._invalid,
            Message.of("conformance-off-schema", errors="; ".join(self._invalid)),
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
        elif isinstance(message, wire.UpdateStatusReport) and UPDATE in self._allowed:
            self.updates.append(message)
        elif isinstance(message, wire.Hello):
            self._invalid.append("hello is only the first message of a link")
        elif (needed := wire.NEEDS.get(type(message))) and needed not in self._allowed:
            self._invalid.append(f"{message.message_type} needs the {needed} capability")


async def pair_by_code(pairing: Pairing, manifest: Manifest, *, by: PersonId | None = None) -> Satellite:
    """Pair `manifest`'s device the way a person does with its device code: it asks, they type the code."""
    ticket = await pairing.request(manifest)
    assert ticket.device_code is not None
    return await pairing.approve(ticket.device_code, pairing_id=ticket.id, by=by)
