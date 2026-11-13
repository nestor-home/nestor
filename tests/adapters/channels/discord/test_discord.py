"""Discord channel against a fake gateway (a real WebSocket server) and a mocked HTTP API: the messaging contract,
direct messages answered and a server's channel only when the bot is mentioned, a reconnection asked by Discord,
a refused token, and long answers split."""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from websockets.asyncio.server import ServerConnection, serve

from nestor.adapters.channels.discord.channel import DiscordChannel
from nestor.core import ProviderError
from nestor.modules.channels import Assistant, Attachment, AttachmentKind
from nestor.testing.channels import MessagingChannelContract, Platform, ScriptedAssistant

TOKEN = "bot.token.secret"
BOT, ADA = "100", "7"


class FakeDiscord:
    """The gateway hands out queued messages after Hello and READY; the API keeps what was posted and serves files.
    `refuse` closes the gateway as Discord does for a bad token; `reconnect` asks the bot to come back once."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.posted: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.identified: list[dict[str, Any]] = []
        self.refuse = False
        self.reconnect = False
        self.heartbeat_ms = 45000  # never acknowledged: a short one makes the bot find the connection dead
        self.port = 0
        self.transport = httpx.MockTransport(self.handle)

    async def gateway(self, socket: ServerConnection) -> None:
        await socket.send(json.dumps({"op": 10, "d": {"heartbeat_interval": self.heartbeat_ms}}))
        identify = json.loads(await socket.recv())
        self.identified.append(identify["d"])
        if self.refuse:
            await socket.close(4004, "Authentication failed.")
            return
        await socket.send(json.dumps({"op": 0, "t": "READY", "s": 1, "d": {"user": {"id": BOT}}}))
        if self.reconnect:
            self.reconnect = False
            await socket.send(json.dumps({"op": 7, "d": None}))
            await socket.wait_closed()
            return
        closed = asyncio.ensure_future(socket.wait_closed())
        while True:
            message = asyncio.ensure_future(self.events.get())
            await asyncio.wait({message, closed}, return_when=asyncio.FIRST_COMPLETED)
            if closed.done():
                message.cancel()
                return
            await socket.send(json.dumps({"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": message.result()}))

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.test":
            return httpx.Response(200, content=self.files[request.url.path])
        if request.headers.get("Authorization") != f"Bot {TOKEN}":
            return httpx.Response(401, json={"message": "401: Unauthorized", "code": 0})
        if request.url.path.endswith("/gateway/bot"):
            return httpx.Response(200, json={"url": f"ws://127.0.0.1:{self.port}"})
        if request.url.path.endswith("/typing"):
            return httpx.Response(204)
        if request.url.path.endswith("/messages"):
            if request.headers["content-type"].startswith("multipart/"):
                payload = request.content.split(b'name="payload_json"\r\n\r\n')[1].split(b"\r\n--")[0]
                self.posted.append(json.loads(payload) | {"files": request.content.count(b'name="files[')})
            else:
                self.posted.append(json.loads(request.content))
            return httpx.Response(200, json={"id": str(len(self.posted))})
        return httpx.Response(404, json={"message": "404: Not Found"})

    def say(
        self, text: str, *, guild: bool = False, mentions: bool = False, files: list[dict] | None = None, flags: int = 0
    ) -> None:
        message = {
            "id": "1",
            "channel_id": "55" if guild else "42",
            "author": {"id": ADA, "username": "ada"},
            "content": text,
            "attachments": files or [],
            "flags": flags,
            "timestamp": "2026-11-13T07:00:00+00:00",
            "mentions": [{"id": BOT}] if mentions else [],
        }
        if guild:
            message["guild_id"] = "9"
        self.events.put_nowait(message)

    def texts(self) -> list[str]:
        return [p["content"] for p in self.posted if p.get("content")]


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


@asynccontextmanager
async def serving(discord: FakeDiscord, assistant: Assistant) -> AsyncGenerator[DiscordChannel]:
    async with serve(discord.gateway, "127.0.0.1", 0) as server:
        discord.port = next(iter(server.sockets)).getsockname()[1]
        channel = DiscordChannel(
            "discord", token=TOKEN, api="https://discord.test/api/v10", retry_delay_s=0.01, transport=discord.transport
        )
        task = asyncio.create_task(channel.serve(assistant))
        try:
            yield channel
        finally:
            await channel.close()
            await asyncio.wait_for(task, 2)


class DiscordPlatform(Platform):
    def __init__(self, discord: FakeDiscord, channel: DiscordChannel) -> None:
        self.channel = channel
        self.discord = discord

    async def send(self, text: str, *attachments: Attachment) -> None:
        files = []
        for n, file in enumerate(attachments):
            self.discord.files[f"/a/{n}"] = file.data
            files.append(
                {
                    "id": str(n),
                    "filename": "file",
                    "content_type": file.media_type,
                    "size": len(file.data),
                    "url": f"https://cdn.test/a/{n}",
                }
            )
        voice = any(a.kind is AttachmentKind.VOICE for a in attachments)
        self.discord.say(text, files=files, flags=(1 << 13) if voice else 0)

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.discord.posted) >= count)

    def texts(self) -> list[str]:
        return self.discord.texts()

    def voices(self) -> list[bytes]:
        return []


class TestDiscordMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        discord = FakeDiscord()
        async with serving(discord, assistant) as channel:
            yield DiscordPlatform(discord, channel)


def echo(message: Any) -> str:
    return f"echo: {message.text}"


async def test_a_server_s_channel_is_answered_only_when_the_bot_is_mentioned() -> None:
    discord = FakeDiscord()
    async with serving(discord, ScriptedAssistant(echo)):
        discord.say("entre nous", guild=True)
        discord.say(f"<@{BOT}> tu es là ?", guild=True, mentions=True)
        await eventually(lambda: bool(discord.posted))
        await asyncio.sleep(0.05)
    assert discord.texts() == ["echo: tu es là ?"]
    assert discord.identified[0]["token"] == TOKEN and discord.identified[0]["intents"] & (1 << 15)


async def test_a_reconnection_discord_asks_for_is_made_and_messages_flow_again() -> None:
    discord = FakeDiscord()
    discord.reconnect = True
    async with serving(discord, ScriptedAssistant(echo)):
        await eventually(lambda: len(discord.identified) == 2)
        discord.say("toujours là ?")
        await eventually(lambda: bool(discord.posted))
    assert discord.texts() == ["echo: toujours là ?"]


async def test_a_long_answer_is_split_and_a_picture_goes_with_its_last_part() -> None:
    discord = FakeDiscord()
    picture = Attachment(kind=AttachmentKind.IMAGE, data=b"png", media_type="image/png")
    long = "Une phrase. " * 300
    async with serving(discord, ScriptedAssistant(lambda message: long, pictures=(picture,))):
        discord.say("raconte")
        await eventually(lambda: any(p.get("files") for p in discord.posted))
    assert all(len(p["content"]) <= 2000 for p in discord.posted) and len(discord.posted) == 2
    assert discord.posted[-1]["files"] == 1


async def test_a_refused_token_stops_the_channel() -> None:
    discord = FakeDiscord()
    discord.refuse = True
    async with serve(discord.gateway, "127.0.0.1", 0) as server:
        discord.port = next(iter(server.sockets)).getsockname()[1]
        channel = DiscordChannel(
            "discord", token=TOKEN, api="https://discord.test/api/v10", transport=discord.transport
        )
        with pytest.raises(ProviderError, match="refused"):
            await asyncio.wait_for(channel.serve(ScriptedAssistant(echo)), 2)
        await channel.close()


async def test_a_connection_whose_heartbeats_go_unacknowledged_is_replaced() -> None:
    discord = FakeDiscord()
    discord.heartbeat_ms = 30
    async with serving(discord, ScriptedAssistant(echo)):
        await eventually(lambda: len(discord.identified) >= 2)
