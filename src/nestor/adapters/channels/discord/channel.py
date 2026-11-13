"""The Discord channel: a bot application on the Gateway and the HTTP API, a `MessagingChannel`."""

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Any

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from nestor.adapters.channels.discord.gateway import INTENTS, Beat, Fatal, frames, frames_of
from nestor.adapters.channels.messaging import Incoming, MessagingChannel, Pending, kind_of, split_text
from nestor.adapters.common.http import HttpApi
from nestor.core import ProviderError
from nestor.modules.channels import Address, Answer, AttachmentKind, Sender

logger = logging.getLogger(__name__)

PROVIDER = "discord"
API = "https://discord.com/api/v10"
MESSAGE_LIMIT = 2000
VOICE_MESSAGE = 1 << 13  # a message's flag


class DiscordChannel(MessagingChannel):
    name = "discord"
    brand = "discord"
    sends = frozenset({AttachmentKind.IMAGE})

    typing_every_s = 8.0  # Discord shows it for 10 s

    def __init__(
        self,
        channel_id: str,
        *,
        token: str,
        api: str = API,
        transport: httpx.AsyncBaseTransport | None = None,
        **common: Any,
    ) -> None:
        """`common`: what every `MessagingChannel` takes (`apology`, `retry_delay_s`…)."""
        super().__init__(channel_id, **common)
        self._token = token
        self._api = HttpApi(PROVIDER, api, headers={"Authorization": f"Bot {token}"}, secret=token, transport=transport)
        self._files = HttpApi(PROVIDER, "", transport=transport)  # attachments, on Discord's CDN: no token there
        self._me: str | None = None
        self._socket: ClientConnection | None = None  # the gateway's, closed with the channel

    async def receive(self) -> AsyncIterator[Incoming]:
        """Raises `ProviderError` when Discord refuses the token or the intents; other failures reconnect."""
        failures = 0
        while not self.closed:
            try:
                gateway = (await self._api.request("GET", "/gateway/bot")).json()["url"]
                async with connect(f"{gateway}?v=10&encoding=json", logger=frames, max_size=2**24) as socket:
                    self._socket, beat = socket, Beat()
                    async for incoming in self._session(socket, beat):
                        failures = 0
                        yield incoming
                if beat.asked_to_reconnect:
                    continue
                raise ConnectionError("the gateway closed")  # reconnected after a pause, as after a failure
            except Fatal as fatal:
                raise ProviderError(PROVIDER, f"the gateway refused the bot ({fatal})", transient=False) from None
            except (ProviderError, OSError, WebSocketException, ValueError, KeyError) as error:
                if self.closed:
                    return
                await self.retry_later(error, failures)
                failures += 1

    async def disconnect(self) -> None:
        if self._socket is not None:
            await self._socket.close()
        await self._api.aclose()
        await self._files.aclose()

    async def deliver(self, conversation: str, answer: Answer) -> None:
        parts = split_text(answer.text, MESSAGE_LIMIT) or [""]
        pictures = [a for a in answer.attachments if a.kind is AttachmentKind.IMAGE]
        for part in parts[:-1]:
            await self._api.request("POST", f"/channels/{conversation}/messages", json={"content": part})
        last = {"content": parts[-1]}
        if not pictures:
            await self._api.request("POST", f"/channels/{conversation}/messages", json=last)
            return
        files = {
            f"files[{n}]": (p.name or f"image{n}.{p.media_type.rpartition('/')[2]}", p.data, p.media_type)
            for n, p in enumerate(pictures)
        }
        await self._api.request(
            "POST", f"/channels/{conversation}/messages", data={"payload_json": json.dumps(last)}, files=files
        )

    async def show_typing(self, conversation: str) -> None:
        await self._api.request("POST", f"/channels/{conversation}/typing")

    async def _session(self, socket: ClientConnection, beat: Beat) -> AsyncIterator[Incoming]:
        """One connection: Hello, Identify, then heartbeats beside the messages, until Discord asks to reconnect or
        the connection ends."""
        hello = json.loads(await socket.recv())
        interval_s = hello["d"]["heartbeat_interval"] / 1000
        properties = {"os": "linux", "browser": "nestor", "device": "nestor"}
        await socket.send(
            json.dumps({"op": 2, "d": {"token": self._token, "intents": INTENTS, "properties": properties}})
        )
        beating = asyncio.create_task(self._heartbeat(socket, interval_s, beat))
        try:
            async for raw in frames_of(socket):
                frame = json.loads(raw)
                if frame.get("s") is not None:
                    beat.sequence = frame["s"]
                match frame.get("op"):
                    case 0 if frame.get("t") == "READY":
                        self._me = frame["d"]["user"]["id"]
                    case 0 if frame.get("t") == "MESSAGE_CREATE":
                        if (incoming := self._incoming(frame["d"])) is not None:
                            yield incoming
                    case 1:
                        await socket.send(json.dumps({"op": 1, "d": beat.sequence}))
                    case 11:
                        beat.acknowledged = True
                    case 7 | 9:  # reconnect, invalid session
                        beat.asked_to_reconnect = True
                        return
        finally:
            beating.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beating

    async def _heartbeat(self, socket: ClientConnection, interval_s: float, beat: Beat) -> None:
        """A heartbeat every `interval_s`; one left unacknowledged means a dead connection: it is closed, and the
        channel reconnects."""
        with contextlib.suppress(WebSocketException):
            while True:
                await asyncio.sleep(interval_s)
                if not beat.acknowledged:
                    await socket.close(4000, "heartbeat not acknowledged")
                    return
                beat.acknowledged = False
                await socket.send(json.dumps({"op": 1, "d": beat.sequence}))

    def _incoming(self, message: Mapping[str, Any]) -> Incoming | None:
        author = message.get("author") or {}
        if author.get("bot") or author.get("id") == self._me:
            return None
        text = str(message.get("content") or "")
        if message.get("guild_id"):  # in a server's channel, only what mentions the bot
            if not any(m.get("id") == self._me for m in message.get("mentions") or []):
                return None
            text = re.sub(rf"<@!?{self._me}>", "", text).strip()
        voice = bool((message.get("flags") or 0) & VOICE_MESSAGE)
        at = datetime.fromisoformat(message["timestamp"]) if message.get("timestamp") else None
        return Incoming(
            address=Address(self.channel_id, str(message["channel_id"])),
            sender=Sender(str(author["id"]), author.get("global_name") or author.get("username")),
            text=text,
            files=tuple(self._pending(a, voice=voice) for a in message.get("attachments") or []),
            at=at,
        )

    def _pending(self, attachment: Mapping[str, Any], *, voice: bool) -> Pending:
        media_type = str(attachment.get("content_type") or "application/octet-stream").split(";")[0]
        kind = kind_of(media_type, voice=voice)
        url = str(attachment["url"])

        async def fetch() -> bytes:
            return (await self._files.request("GET", url)).content

        name, size = attachment.get("filename"), attachment.get("size")
        return Pending(kind=kind, media_type=media_type, fetch=fetch, name=name, size=size)
