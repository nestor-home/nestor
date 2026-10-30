"""The `nestor` data channel of one paired satellite, seen from the core.

Everything the device says is checked against the wire contract and attributed to the *paired*
device and room, never to what the message claims. Observations become journal events; intents go
out through `RemoteBody` and are acknowledged by id.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any

from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from nestor.core import Capabilities, ContractError, Event
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

SOURCE = "voice.satellites"


class SatelliteLink:
    """Answers `hello` with `welcome`, journals observations and tracks intent acknowledgements.

    An intent not acknowledged within `ack_timeout_s` is logged once and forgotten: the device may
    be busy or gone, the conversation never waits for it.
    """

    def __init__(
        self, connection: SmallWebRTCConnection, satellite: Satellite, journal: Journal, *, ack_timeout_s: float = 2.0
    ) -> None:
        self.satellite = satellite
        self._connection = connection
        self._journal = journal
        self._ack_timeout_s = ack_timeout_s
        self._unacknowledged: dict[str, tuple[float, str]] = {}
        self.greeted = False
        # Pipecat runs each message handler in a task of its own: queueing keeps the device's order.
        self._inbox: asyncio.Queue[Any] = asyncio.Queue()
        self._reader = asyncio.create_task(self._read(), name=f"satellite {satellite.id}")
        connection.add_event_handler("app-message", self._queue)

    @property
    def unacknowledged(self) -> list[str]:
        """Message types of the intents still waiting for their ack."""
        return [kind for _, kind in self._unacknowledged.values()]

    def send(self, message: wire.Message) -> None:
        self._forget_overdue()
        data = wire.encode(message)
        if message.message_type.startswith("intent."):
            self._unacknowledged[data["id"]] = (time.monotonic(), message.message_type)
        self._connection.send_app_message(data)

    async def close(self) -> None:
        self._reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._reader
        if self.greeted:
            await self._publish(
                SatelliteDisconnected(source=SOURCE, device_id=self.satellite.id, room=self.satellite.room)
            )

    async def _queue(self, _connection: SmallWebRTCConnection, data: Any) -> None:
        self._inbox.put_nowait(data)

    async def _read(self) -> None:
        while True:
            await self._received(await self._inbox.get())

    async def _received(self, data: Any) -> None:
        try:
            message = wire.decode(data).message
        except ContractError as error:
            logger.warning("satellite %s sent an off-contract message: %s", self.satellite.id, error)
            return
        match message:
            case wire.Hello(manifest=manifest) if manifest.device.id != self.satellite.id:
                logger.warning("satellite %s introduced itself as %s: ignored", self.satellite.id, manifest.device.id)
            case wire.Hello():
                self.send(self._welcome())
                if not self.greeted:
                    self.greeted = True
                    await self._publish(
                        SatelliteConnected(source=SOURCE, device_id=self.satellite.id, room=self.satellite.room)
                    )
            case wire.Ack(of=intent):
                self._unacknowledged.pop(intent, None)
            case wire.PersonObservation(count=count, confidence=confidence):
                await self._publish(
                    PersonDetected(source=SOURCE, device_id=self.satellite.id, room=self.satellite.room, count=count,
                                   confidence=confidence)
                )  # fmt: skip
            case wire.SpeechActivityObservation(active=active):
                await self._publish(
                    SpeechActivityObserved(source=SOURCE, device_id=self.satellite.id, room=self.satellite.room,
                                           active=active)
                )  # fmt: skip
            case _:
                logger.warning(
                    "satellite %s sent %s, which only the core sends", self.satellite.id, message.message_type
                )

    def _welcome(self) -> wire.Welcome:
        satellite = self.satellite
        return wire.Welcome(
            device_id=satellite.id, room=satellite.room, capabilities=tuple(sorted(satellite.capabilities))
        )

    async def _publish(self, event: Event) -> None:
        await self._journal.publish(event)

    def _forget_overdue(self) -> None:
        deadline = time.monotonic() - self._ack_timeout_s
        for intent, (sent, kind) in list(self._unacknowledged.items()):
            if sent < deadline:
                del self._unacknowledged[intent]
                logger.warning("satellite %s did not acknowledge %s %s", self.satellite.id, kind, intent)


class RemoteBody(Body):
    """A paired device's body: intents travel over its data channel. Expressions need
    `expression.emotion`, speech beats `motion.head`; the attitude is always sent (a speaker can show
    it with a light)."""

    name = "remote-body"

    def __init__(self, link: SatelliteLink) -> None:
        self._link = link
        self.capabilities = Capabilities(link.satellite.capabilities & {EXPRESSION, HEAD_MOTION})
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
