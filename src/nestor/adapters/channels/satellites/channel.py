"""The satellites channel: paired devices people talk with, in writing, aloud or both.

Each device holds a link (`link`) through which it types and shows text; a device allowed audio also
speaks through the voice (`voice`, only when configured). A device's conversation is its room's,
`<channel>:<room>`, whatever the medium: a typed follow-up to a spoken question stays in it. The
speaker is known as the room (map it in the household, e.g. an account `satellites:*`).

- A typed turn is answered in writing on a device allowed `text.display`, otherwise aloud (T3).
- An unprompted message in writing goes to every device of the room that shows text; aloud, to the
  most recent voice session of the room.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from fastapi import WebSocket

from nestor.adapters.channels.satellites.gateway import SatelliteGateway
from nestor.adapters.channels.satellites.link import SatelliteLink
from nestor.adapters.channels.satellites.server import DeviceServer
from nestor.core import Capability, ContractError, ProviderError
from nestor.modules.channels import Address, Assistant, Channel, InboundMessage, Medium, MessageEnd, Sender
from nestor.modules.journal import Journal
from nestor.modules.satellites import (
    AUDIO_CAPTURE,
    AUDIO_PLAYBACK,
    TEXT_DISPLAY,
    Pairing,
    Satellite,
    SatelliteHost,
    wire,
)

if TYPE_CHECKING:
    from nestor.adapters.channels.satellites.voice.audio import SatelliteVoice

logger = logging.getLogger(__name__)

PROVIDER = "satellites"
AUDIO = frozenset({AUDIO_CAPTURE, AUDIO_PLAYBACK})


class SatellitesChannel(Channel, SatelliteHost):
    """`serve` runs the HTTP server and answers every device until closed. Without a voice, devices are
    allowed no audio on their link, whatever their pairing granted."""

    name = "satellites"
    brand = "satellites"

    def __init__(
        self,
        channel_id: str,
        *,
        host: str = "localhost",
        port: int,
        public_url: str | None = None,
        voice: "SatelliteVoice | None" = None,
        style: str = "",
        send_timeout_s: float = 30.0,
        conversation_ends_after_s: float | None = None,
    ) -> None:
        super().__init__(channel_id, conversation_ends_after_s=conversation_ends_after_s)
        self.media = frozenset({Medium.WRITTEN, Medium.SPOKEN}) if voice else frozenset({Medium.WRITTEN})
        self.style = style
        self._host, self._port, self._public_url = host, port, public_url
        self._voice = voice
        self._send_timeout_s = send_timeout_s
        self._assistant: Assistant | None = None
        self._hosting: tuple[Pairing, Journal] | None = None
        self._links: dict[str, SatelliteLink] = {}  # device id → its current link
        self._gateway: SatelliteGateway | None = None
        self._server: DeviceServer | None = None
        self._closed = asyncio.Event()

    def details(self) -> Mapping[str, str]:
        return {"speech": self._voice.speech.brand} if self._voice and self._voice.speech.brand else {}

    def host_satellites(self, pairing: Pairing, journal: Journal) -> None:
        self._hosting = (pairing, journal)

    def satellite_url(self, seen_as: str) -> str | None:
        if self._hosting is None:
            return None
        if self._public_url:
            return self._public_url.rstrip("/")
        host = seen_as if self._host in ("0.0.0.0", "::", "") else self._host
        return f"http://{f'[{host}]' if ':' in host else host}:{self._port}"

    def allowed(self, satellite: Satellite) -> frozenset[Capability]:
        """What a paired device is granted on its link: its pairing's capabilities the core can serve."""
        return satellite.capabilities if self._voice else satellite.capabilities - AUDIO

    async def serve(self, assistant: Assistant) -> None:
        if self._hosting is None:
            raise ContractError("the runtime hosts satellites before serving the channel")
        self._assistant = assistant
        if self._voice is not None:
            self._voice.serve(assistant)
        if self._closed.is_set():
            return
        gateway = SatelliteGateway(self._hosting[0], on_link=self._linked, allowed=self.allowed, audio=self._voice)
        self._gateway = gateway
        self._server = DeviceServer(host=self._host, port=self._port, routes=[gateway])
        logger.info("satellites: %s serving on http://%s:%d", self.channel_id, self._host, self._port)
        await self._server.serve()

    @property
    def rooms(self) -> frozenset[str]:
        """Rooms where someone can hear the assistant right now."""
        return self._voice.rooms if self._voice else frozenset()

    def reachable(self, to: Address, medium: Medium) -> bool:
        if to.channel != self.channel_id:
            return False
        if medium is Medium.SPOKEN:
            return self._voice is not None and self._voice.reachable(to)
        return bool(self._showing(to.conversation))

    async def send(self, to: Address, text: str, medium: Medium) -> None:
        if to.channel != self.channel_id or medium not in self.media:
            raise ContractError(f"{to} is not on channel {self.channel_id!r} {medium}")
        if medium is Medium.SPOKEN:
            assert self._voice is not None
            await self._voice.say(to, text, self._send_timeout_s)
            return
        showing = self._showing(to.conversation)
        if not showing:
            raise ProviderError(PROVIDER, f"no screen is connected in {to}", transient=True)
        for link in showing:
            link.send(wire.TextIntent(text=text))

    async def close(self) -> None:
        self._closed.set()
        if self._voice is not None:
            await self._voice.close()
        if self._gateway is not None:
            await self._gateway.close()  # links learn the core stops (1001) before the server goes
        if self._server is not None:
            self._server.stop()

    def _showing(self, room: str) -> list[SatelliteLink]:
        return [link for link in self._links.values() if link.satellite.room == room and TEXT_DISPLAY in link.allowed]

    async def _linked(self, socket: WebSocket, satellite: Satellite, allowed: frozenset[Capability]) -> None:
        assert self._hosting is not None
        pairing, journal = self._hosting
        link = SatelliteLink(socket, satellite, journal, allowed=allowed)
        self._links[satellite.id] = link
        if self._voice is not None:
            self._voice.attach(link)
        try:
            with pairing.online(satellite.id, link.identify):
                await link.run(self._typed)
        finally:
            if self._links.get(satellite.id) is link:
                del self._links[satellite.id]
                if self._voice is not None:
                    await self._voice.hang_up(link)

    async def _typed(self, link: SatelliteLink, text: str) -> None:
        """A typed turn: answered in writing where it shows text, otherwise aloud (T3)."""
        assert self._assistant is not None
        room = link.satellite.room
        address, sender = Address(self.channel_id, room), Sender(room)
        if self._assistant.identify(address, sender) is None:
            logger.info("satellites: %s is not a known sender in %s, ignoring typed text", sender.id, address)
            return
        shows = TEXT_DISPLAY in link.allowed
        if not shows and not (self._voice and self._voice.reachable(address)):
            logger.warning("satellites: %s typed, but can neither show nor say an answer", link.satellite.id)
            return
        medium = Medium.WRITTEN if shows else Medium.SPOKEN
        reply = self._assistant.respond(InboundMessage(address=address, sender=sender, text=text, medium=medium))
        if not shows:
            assert self._voice is not None
            if spoken := " ".join(await reply.collect()):
                await self._voice.say(address, spoken, self._send_timeout_s)
            return
        written: list[str] = []
        async for part in reply:  # each message shown as soon as it ends, as a messaging channel does
            if not isinstance(part, MessageEnd):
                written.append(part)
                continue
            message, written = "".join(written).strip(), []
            if message:
                link.send(wire.TextIntent(text=message, final=part.last))
