"""The audio of linked satellites: each device allowed audio offers WebRTC once welcomed, and its
voice session runs on that connection until it or its link ends (A1-A3).

A session's address is `<channel>:<room>`, the device's paired room, so a conversation continues
across reconnections and with what is typed there; the speaker is known as the room (map it in the
household, e.g. an account `satellites:*`). Unprompted messages go to the most recent session of a
room. Limits: one speaker identity per room (no voice recognition yet).
"""

import asyncio
import contextlib
import logging
from typing import Any, cast

from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from nestor.adapters.channels.satellites.gateway import AudioOffers
from nestor.adapters.channels.satellites.link import RemoteBody, SatelliteLink
from nestor.adapters.channels.satellites.voice.providers import Speech
from nestor.adapters.channels.satellites.voice.session import SessionSettings, VoiceSession
from nestor.core import ContractError, ProviderError
from nestor.modules.channels import Address, Assistant, Sender
from nestor.modules.satellites import TEXT_DISPLAY, wire

logger = logging.getLogger(__name__)

PROVIDER = "voice"


class SatelliteVoice(AudioOffers):
    """`serve` lends it the assistant; then each answered offer runs a voice session."""

    def __init__(self, channel_id: str, *, speech: Speech, settings: SessionSettings) -> None:
        self.speech = speech
        self._channel_id = channel_id
        self._settings = settings
        self._assistant: Assistant | None = None
        self._handler = SmallWebRTCRequestHandler()
        self._links: dict[str, SatelliteLink] = {}  # device id → its link, while it is up
        self._owners: dict[str, str] = {}  # peer connection id → device id
        self._sessions: dict[str, VoiceSession] = {}  # device id → its current session
        self._by_transport: dict[BaseTransport, VoiceSession] = {}
        self._closed = False
        self._running: set[asyncio.Task[None]] = set()

    def serve(self, assistant: Assistant) -> None:
        self._assistant = assistant

    def attach(self, link: SatelliteLink) -> None:
        """The device's link is up: its audio offers are answered from now on."""
        self._links[link.satellite.id] = link

    async def hang_up(self, link: SatelliteLink) -> None:
        """The device's link ended: its audio ends too (A3)."""
        device = link.satellite.id
        if self._links.get(device) is link:
            del self._links[device]
        if session := self._sessions.get(device):
            await session.stop()

    async def offer(self, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        link = self._link(device_id, body.get("pc_id"))
        request = SmallWebRTCRequest(
            sdp=body["sdp"], type=body["type"], pc_id=body.get("pc_id"), restart_pc=body.get("restart_pc")
        )

        async def connected(connection: SmallWebRTCConnection) -> None:
            task = asyncio.create_task(self._run(connection, link), name=f"voice {link.satellite.id}")
            self._running.add(task)
            task.add_done_callback(self._running.discard)

        # The handler raises rather than return no answer (Pipecat 1.14), despite its annotation.
        answer = cast(dict[str, Any], await self._handler.handle_web_request(request, connected))
        self._owners[answer["pc_id"]] = device_id
        return answer

    async def patch(self, device_id: str, body: dict[str, Any]) -> None:
        self._link(device_id, body["pc_id"])
        candidates = [IceCandidate(**c) for c in body.get("candidates", [])]
        await self._handler.handle_patch_request(SmallWebRTCPatchRequest(pc_id=body["pc_id"], candidates=candidates))

    @property
    def rooms(self) -> frozenset[str]:
        """Rooms where someone can hear the assistant right now."""
        return frozenset(s.address.conversation for s in self._sessions.values())

    def reachable(self, to: Address) -> bool:
        return any(s.address == to for s in self._sessions.values())

    async def say(self, to: Address, text: str, timeout_s: float) -> None:
        """Speak an unprompted message in a room once nobody is speaking there."""
        sessions = [s for s in self._sessions.values() if s.address == to]
        if not sessions:
            raise ProviderError(PROVIDER, f"nobody is connected in {to}", transient=True)
        try:
            async with asyncio.timeout(timeout_s):
                await sessions[-1].say(text)
        except TimeoutError:
            raise ProviderError(PROVIDER, f"nobody stopped speaking in {to}", transient=True) from None

    async def close(self) -> None:
        """End every session (their pending messages fail) and refuse new ones."""
        self._closed = True
        for session in list(self._sessions.values()):
            await session.stop()
        await self._handler.close()
        await asyncio.gather(*self._running, return_exceptions=True)

    async def converse(self, transport: BaseTransport, link: SatelliteLink) -> None:
        """Run the voice session of a linked device on `transport` until it ends (the device leaves,
        `leave`, a newer session of the device, closing); nothing once closed."""
        if self._assistant is None:
            raise ContractError("serve the satellites channel before a voice session starts")
        if self._closed:
            return
        device = link.satellite
        if previous := self._sessions.get(device.id):
            await previous.stop()
        body = RemoteBody(link)
        shown = (lambda text: link.send(wire.TextIntent(text=text))) if TEXT_DISPLAY in link.allowed else None
        session = VoiceSession(
            transport,
            speech=self.speech,
            assistant=self._assistant,
            address=Address(self._channel_id, device.room),
            sender=Sender(device.room),
            settings=self._settings,
            body=body,
            shown=shown,
        )
        self._sessions[device.id] = session
        self._by_transport[transport] = session
        try:
            await session.run()
        finally:
            await body.close()
            del self._by_transport[transport]
            if self._sessions.get(device.id) is session:
                del self._sessions[device.id]

    async def leave(self, transport: BaseTransport) -> None:
        """The client behind `transport` left: its session ends."""
        if session := self._by_transport.get(transport):
            await session.stop()

    def _link(self, device_id: str, pc_id: str | None) -> SatelliteLink:
        link = self._links.get(device_id)
        if link is None:
            raise PermissionError("this device has no link up")
        if pc_id is not None and self._owners.get(pc_id) != device_id:
            raise PermissionError("this peer connection belongs to no session of this device")
        return link

    async def _run(self, connection: SmallWebRTCConnection, link: SatelliteLink) -> None:
        """One audio connection of a linked device; a new one replaces the previous (reconnection)."""
        transport = SmallWebRTCTransport(connection, TransportParams(audio_in_enabled=True, audio_out_enabled=True))

        async def disconnected(_transport: BaseTransport, _client: object) -> None:
            await self.leave(transport)

        transport.add_event_handler("on_client_disconnected", disconnected)
        try:
            await self.converse(transport, link)
        finally:
            self._owners.pop(connection.pc_id, None)
            with contextlib.suppress(Exception):
                await connection.disconnect()
