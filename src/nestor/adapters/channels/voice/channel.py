"""The realtime voice channel: a room where people talk with the assistant.

Each connected client runs its own pipeline (see `session`). Every session of the channel shares
one address, `<channel>:<room>`, so the conversation continues across reconnections; the speaker
is known as the room (map it in the household, e.g. an account `voice:*`).

Limits: one speaker identity per room (no voice recognition yet); unprompted messages go to the
most recent session of the room.
"""

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

from pipecat.transports.base_transport import BaseTransport

from nestor.adapters.channels.voice.providers import Speech
from nestor.adapters.channels.voice.resilience import load_clips
from nestor.adapters.channels.voice.server import SignallingServer
from nestor.adapters.channels.voice.session import SessionSettings, VoiceSession
from nestor.core import ContractError, ProviderError
from nestor.modules.channels import Address, Assistant, Channel, Medium, Sender

logger = logging.getLogger(__name__)

PROVIDER = "voice"


class VoiceChannel(Channel):
    """`serve` runs the signalling server (when `port` is set) and answers every session until closed.

    Sessions can also be attached directly with `attach` (another transport, tests). `send` speaks
    an unprompted message in the room once nobody is speaking, and fails with a transient
    `ProviderError` when nobody is connected or nobody stops speaking within `send_timeout_s`.
    """

    name = "voice"
    medium = Medium.SPOKEN

    def __init__(
        self,
        channel_id: str,
        *,
        room: str,
        speech: Speech,
        style: str = "",
        host: str = "localhost",
        port: int | None = None,
        session: SessionSettings | None = None,
        clips: Path | None = None,
        send_timeout_s: float = 30.0,
    ) -> None:
        super().__init__(channel_id)
        self.style = style
        self.address = Address(channel_id, room)
        self._speech = speech
        self._host, self._port = host, port
        self._session = session or SessionSettings()
        self._clips_folder = clips
        self._send_timeout_s = send_timeout_s
        self._settings: SessionSettings | None = None
        self._assistant: Assistant | None = None
        self._sessions: dict[BaseTransport, VoiceSession] = {}
        self._server: SignallingServer | None = None
        self._closed = asyncio.Event()

    async def start(self) -> None:
        self._settings = replace(self._session, clips=load_clips(self._clips_folder))

    async def serve(self, assistant: Assistant) -> None:
        self._assistant = assistant
        if self._port is None or self._closed.is_set():
            await self._closed.wait()
            return
        self._server = SignallingServer(host=self._host, port=self._port, attach=self.attach, detach=self.detach)
        logger.info("voice: %s listening on http://%s:%d/client", self.address, self._host, self._port)
        await self._server.serve()

    async def attach(self, transport: BaseTransport) -> None:
        """Run a voice session on `transport` until it ends (client gone, `detach`, channel closed)."""
        if self._assistant is None or self._settings is None:
            raise ContractError("start the voice channel and serve it before attaching a session")
        if self._closed.is_set():
            return
        session = VoiceSession(
            transport,
            speech=self._speech,
            assistant=self._assistant,
            address=self.address,
            sender=Sender(self.address.conversation),
            settings=self._settings,
        )
        self._sessions[transport] = session
        try:
            await session.run()
        finally:
            del self._sessions[transport]

    async def detach(self, transport: BaseTransport) -> None:
        if session := self._sessions.get(transport):
            await session.stop()

    def reachable(self, to: Address) -> bool:
        return to == self.address and bool(self._sessions)

    async def send(self, to: Address, text: str) -> None:
        if to.channel != self.channel_id:
            raise ContractError(f"{to} is not on channel {self.channel_id!r}")
        if not self.reachable(to):
            raise ProviderError(PROVIDER, f"nobody is connected in {to}", transient=True)
        session = list(self._sessions.values())[-1]
        try:
            async with asyncio.timeout(self._send_timeout_s):
                await session.say(text)
        except TimeoutError:
            raise ProviderError(PROVIDER, f"nobody stopped speaking in {to}", transient=True) from None

    async def close(self) -> None:
        self._closed.set()
        for session in list(self._sessions.values()):
            await session.stop()
        if self._server is not None:
            self._server.stop()
