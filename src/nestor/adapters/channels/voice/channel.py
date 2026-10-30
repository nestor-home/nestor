"""The realtime voice channel: rooms where people talk with the assistant.

Each connected client runs its own pipeline (see `session`). A session's address is
`<channel>:<room>` — the satellite's paired room, or the channel's `room` for the development
browser — so a conversation continues across reconnections; the speaker is known as the room
(map it in the household, e.g. an account `voice:*`).

Limits: one speaker identity per room (no voice recognition yet); unprompted messages go to the
most recent session of the room.
"""

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from nestor.adapters.channels.voice.providers import Speech
from nestor.adapters.channels.voice.resilience import load_clips
from nestor.adapters.channels.voice.satellites.gateway import SatelliteGateway
from nestor.adapters.channels.voice.satellites.link import RemoteBody, SatelliteLink
from nestor.adapters.channels.voice.server import BrowserRoutes, Routes, SignallingServer, audio_transport
from nestor.adapters.channels.voice.session import SessionSettings, VoiceSession
from nestor.core import ContractError, ProviderError
from nestor.modules.behavior import Body
from nestor.modules.channels import Address, Assistant, Channel, Medium, Sender
from nestor.modules.journal import Journal
from nestor.modules.satellites import Pairing, Satellite, SatelliteHost

logger = logging.getLogger(__name__)

PROVIDER = "voice"


class VoiceChannel(Channel, SatelliteHost):
    """`serve` runs the HTTP server (when `port` is set) and answers every session until closed.

    - Paired satellites connect once the runtime called `host_satellites`; the browser client
      connects without pairing only with `allow_unpaired_browser` (trusted LAN, development).
    - Sessions can also be attached directly with `attach` (another transport, tests).
    - `send` speaks an unprompted message in a room once nobody is speaking, and fails with a
      transient `ProviderError` when nobody is connected there or nobody stops speaking within
      `send_timeout_s`.
    """

    name = "voice"
    brand = "webrtc"
    medium = Medium.SPOKEN

    def details(self) -> Mapping[str, str]:
        known = {"speech": self._speech.brand}
        return {role: brand for role, brand in known.items() if brand}

    def __init__(
        self,
        channel_id: str,
        *,
        room: str,
        speech: Speech,
        style: str = "",
        host: str = "localhost",
        port: int | None = None,
        allow_unpaired_browser: bool = True,
        public_url: str | None = None,
        session: SessionSettings,
        clips: Path | None = None,
        send_timeout_s: float = 30.0,
        conversation_ends_after_s: float | None = None,
    ) -> None:
        super().__init__(channel_id, conversation_ends_after_s=conversation_ends_after_s)
        self.style = style
        self.room = self._default_room = room  # the browser's room; satellites bring their own
        self._speech = speech
        self._host, self._port = host, port
        self._public_url = public_url  # how satellites reach this server, when its own address does not tell
        self._allow_unpaired_browser = allow_unpaired_browser
        self._session = session
        self._clips_folder = clips
        self._send_timeout_s = send_timeout_s
        self._settings: SessionSettings | None = None
        self._assistant: Assistant | None = None
        self._sessions: dict[BaseTransport, VoiceSession] = {}
        self._satellites: dict[str, BaseTransport] = {}  # device id → its current transport
        self._hosting: tuple[Pairing, Journal] | None = None
        self._server: SignallingServer | None = None
        self._closed = asyncio.Event()

    def host_satellites(self, pairing: Pairing, journal: Journal) -> None:
        self._hosting = (pairing, journal)

    def satellite_url(self, seen_as: str) -> str | None:
        if self._port is None or self._hosting is None:
            return None
        if self._public_url:
            return self._public_url.rstrip("/")
        host = seen_as if self._host in ("0.0.0.0", "::", "") else self._host
        return f"http://{f'[{host}]' if ':' in host else host}:{self._port}"

    async def start(self) -> None:
        self._settings = replace(self._session, clips=load_clips(self._clips_folder))

    async def serve(self, assistant: Assistant) -> None:
        self._assistant = assistant
        routes = self._routes()
        if self._port is None or self._closed.is_set() or not routes:
            await self._closed.wait()
            return
        self._server = SignallingServer(host=self._host, port=self._port, routes=routes)
        logger.info("voice: %s serving on http://%s:%d", self.channel_id, self._host, self._port)
        await self._server.serve()

    async def attach(self, transport: BaseTransport, *, room: str | None = None, body: Body | None = None) -> None:
        """Run a voice session on `transport` until it ends (client gone, `detach`, channel closed).
        `room` defaults to the channel's; `body` is animated with the played audio."""
        if self._assistant is None or self._settings is None:
            raise ContractError("start the voice channel and serve it before attaching a session")
        if self._closed.is_set():
            return
        address = Address(self.channel_id, room or self._default_room)
        session = VoiceSession(
            transport,
            speech=self._speech,
            assistant=self._assistant,
            address=address,
            sender=Sender(address.conversation),
            settings=self._settings,
            body=body,
            rtvi=body is None,
        )
        self._sessions[transport] = session
        try:
            await session.run()
        finally:
            del self._sessions[transport]

    async def detach(self, transport: BaseTransport) -> None:
        if session := self._sessions.get(transport):
            await session.stop()

    @property
    def rooms(self) -> frozenset[str]:
        """Rooms where someone can hear the channel right now."""
        return frozenset(s.address.conversation for s in self._sessions.values())

    def reachable(self, to: Address) -> bool:
        return any(s.address == to for s in self._sessions.values())

    async def send(self, to: Address, text: str) -> None:
        if to.channel != self.channel_id:
            raise ContractError(f"{to} is not on channel {self.channel_id!r}")
        sessions = [s for s in self._sessions.values() if s.address == to]
        if not sessions:
            raise ProviderError(PROVIDER, f"nobody is connected in {to}", transient=True)
        try:
            async with asyncio.timeout(self._send_timeout_s):
                await sessions[-1].say(text)
        except TimeoutError:
            raise ProviderError(PROVIDER, f"nobody stopped speaking in {to}", transient=True) from None

    async def close(self) -> None:
        self._closed.set()
        for session in list(self._sessions.values()):
            await session.stop()
        if self._server is not None:
            self._server.stop()

    def _routes(self) -> list[Routes]:
        routes: list[Routes] = []
        if self._hosting is not None:
            pairing, journal = self._hosting
            routes.append(SatelliteGateway(pairing, lambda c, s: self._serve_satellite(c, s, journal)))
        if self._allow_unpaired_browser:
            routes.append(BrowserRoutes(attach=self.attach, detach=self.detach))
        return routes

    async def _serve_satellite(self, connection: SmallWebRTCConnection, satellite: Satellite, journal: Journal) -> None:
        """One connection of a paired device; a new one replaces the previous (reconnection)."""
        if previous := self._satellites.get(satellite.id):
            await self.detach(previous)
        transport = audio_transport(connection)
        self._satellites[satellite.id] = transport

        async def disconnected(_transport: BaseTransport, _client: object) -> None:
            await self.detach(transport)

        transport.add_event_handler("on_client_disconnected", disconnected)
        link = SatelliteLink(connection, satellite, journal)
        body = RemoteBody(link)
        pairing = self._hosting[0] if self._hosting else None
        try:
            with pairing.online(satellite.id, link.identify) if pairing else contextlib.nullcontext():
                await self.attach(transport, room=satellite.room, body=body)
        finally:
            await body.close()
            await link.close()
            if self._satellites.get(satellite.id) is transport:
                del self._satellites[satellite.id]
