"""The link of one paired satellite, seen from the core: a WebSocket that carries every message.

Everything the device says is checked against the wire contract and attributed to the *paired*
device and room, never to what the message claims. Observations become journal events, typed text
becomes turns of the room's conversation, intents go out (through `RemoteBody` for the body) and are
acknowledged by id. What the device was not allowed is ignored.
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

from nestor.core import Capabilities, Capability, ContractError
from nestor.modules.behavior import EXPRESSION, HEAD_MOTION, Behavior, Body, Expression
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    PersonDetected,
    Satellite,
    SatelliteConnected,
    SatelliteDisconnected,
    SpeechActivityObserved,
    wire,
)

logger = logging.getLogger(__name__)

SOURCE = "satellites"


type Typed = Callable[["SatelliteLink", str], Awaitable[None]]


class SatelliteLink:
    """A welcomed device: `run` reads it until it leaves; `send` queues a message for it.

    An intent not acknowledged within `ack_timeout_s` is logged once and forgotten: the device may
    be busy or gone, the conversation never waits for it. Typed text is answered one turn at a time,
    while the link keeps reading (acknowledgements arrive during an answer).
    """

    def __init__(
        self,
        socket: WebSocket,
        satellite: Satellite,
        journal: Journal,
        *,
        allowed: frozenset[Capability],
        ack_timeout_s: float = 2.0,
    ) -> None:
        self.satellite = satellite
        self.allowed = allowed  # what `welcome` granted: the pairing's capabilities the core can serve
        self._socket = socket
        self._journal = journal
        self._ack_timeout_s = ack_timeout_s
        self._unacknowledged: dict[str, tuple[float, str]] = {}
        self._outbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._typed: asyncio.Queue[str | None] = asyncio.Queue()
        self._closed = asyncio.Event()

    @property
    def unacknowledged(self) -> list[str]:
        """Message types of the intents still waiting for their ack."""
        return [kind for _, kind in self._unacknowledged.values()]

    def identify(self) -> None:
        """Ask the device to make itself noticed (it declared and was allowed `device.identify`)."""
        self.send(wire.IdentifyIntent())

    def send(self, message: wire.Message) -> None:
        if self._closed.is_set():
            return
        self._forget_overdue()
        data = wire.encode(message)
        if message.message_type.startswith("intent."):
            self._unacknowledged[data["id"]] = (time.monotonic(), message.message_type)
        self._outbox.put_nowait(data)

    async def run(self, typed: Typed) -> None:
        """Welcome the device, then read it until it leaves or `close` is called; `typed` answers each
        text it sends, in order."""
        satellite = self.satellite
        self.send(wire.Welcome(device_id=satellite.id, room=satellite.room, capabilities=tuple(sorted(self.allowed))))
        await self._journal.publish(SatelliteConnected(source=SOURCE, device_id=satellite.id, room=satellite.room))
        writer = asyncio.create_task(self._write(), name=f"satellite {satellite.id} out")
        answering = asyncio.create_task(self._answer(typed), name=f"satellite {satellite.id} text")
        try:
            await self._read()
        finally:
            self._closed.set()
            self._outbox.put_nowait(None)
            self._typed.put_nowait(None)
            answering.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await answering
            await writer
            await self._journal.publish(
                SatelliteDisconnected(source=SOURCE, device_id=satellite.id, room=satellite.room)
            )

    async def _read(self) -> None:
        while True:
            try:
                received = await self._socket.receive()
            except RuntimeError:  # closed from the core's side (replaced, stopping)
                return
            if received["type"] == "websocket.disconnect":
                return
            await self._received(received.get("text"))

    async def _write(self) -> None:
        while (data := await self._outbox.get()) is not None:
            try:
                await self._socket.send_text(json.dumps(data))
            except Exception:  # gone: the reader notices and ends the link
                logger.debug("satellite %s: could not send %s", self.satellite.id, data["type"])
                return

    async def _answer(self, typed: Typed) -> None:
        while (text := await self._typed.get()) is not None:
            try:
                await typed(self, text)
            except Exception:
                logger.exception("satellite %s: the typed turn failed", self.satellite.id)

    async def _received(self, text: str | None) -> None:
        try:
            message = wire.decode(json.loads(text) if text is not None else None).message
        except (ContractError, ValueError) as error:
            logger.warning("satellite %s sent an off-contract message: %s", self.satellite.id, error)
            return
        if message.direction is not wire.Direction.TO_CORE:
            logger.warning("satellite %s sent %s, which only the core sends", self.satellite.id, message.message_type)
            return
        if (needed := wire.NEEDS.get(type(message))) is not None and needed not in self.allowed:
            logger.warning("satellite %s sent %s without %s: ignored", self.satellite.id, message.message_type, needed)
            return
        satellite = self.satellite
        match message:
            case wire.Hello():
                logger.warning("satellite %s said hello twice on one link: ignored", satellite.id)
            case wire.Ack(of=intent):
                self._unacknowledged.pop(intent, None)
            case wire.TextInput(text=typed):
                self._typed.put_nowait(typed)
            case wire.PersonObservation(count=count, confidence=confidence):
                await self._journal.publish(
                    PersonDetected(source=SOURCE, device_id=satellite.id, room=satellite.room, count=count,
                                   confidence=confidence)
                )  # fmt: skip
            case wire.SpeechActivityObservation(active=active):
                await self._journal.publish(
                    SpeechActivityObserved(source=SOURCE, device_id=satellite.id, room=satellite.room, active=active)
                )

    def _forget_overdue(self) -> None:
        deadline = time.monotonic() - self._ack_timeout_s
        for intent, (sent, kind) in list(self._unacknowledged.items()):
            if sent < deadline:
                del self._unacknowledged[intent]
                logger.warning("satellite %s did not acknowledge %s %s", self.satellite.id, kind, intent)


class RemoteBody(Body):
    """A paired device's body: intents travel over its link. Expressions need `expression.emotion`,
    speech beats `motion.head`; the attitude is always sent (a speaker can show it with a light)."""

    name = "remote-body"

    def __init__(self, link: SatelliteLink) -> None:
        self._link = link
        self.capabilities = Capabilities(link.allowed & {EXPRESSION, HEAD_MOTION})
        self._behavior: Behavior | None = None
        self._closed = False

    def set_behavior(self, behavior: Behavior) -> None:
        if behavior is not self._behavior:
            self._behavior = behavior
            self._send(wire.BehaviorIntent(behavior=behavior))

    def express(self, expression: Expression) -> None:
        if EXPRESSION in self.capabilities:
            self._send(wire.ExpressionIntent(expression=expression))

    def beat(self) -> None:
        if HEAD_MOTION in self.capabilities:
            self._send(wire.BeatIntent())

    async def close(self) -> None:
        """Back to rest, then silent: intents after closing are dropped."""
        self.set_behavior(Behavior.IDLE)
        self._closed = True

    def _send(self, message: wire.Message) -> None:
        if self._closed:
            return
        try:
            self._link.send(message)
        except Exception:  # a lost device must never break the conversation
            logger.exception("could not send %s to satellite %s", message.message_type, self._link.satellite.id)
