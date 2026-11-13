"""Matrix channel against a fake homeserver: the messaging contract, invitations joined, the history before a start
skipped, encrypted rooms left unread, and the token refused."""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from nestor.adapters.channels.matrix.channel import VOICE, MatrixChannel
from nestor.core import ProviderError
from nestor.modules.channels import Assistant, Attachment, AttachmentKind
from nestor.testing.channels import MessagingChannelContract, Platform, ScriptedAssistant

TOKEN = "syt_bot_token"
BOT, ADA = "@nestor:home.test", "@ada:home.test"
ROOM = "!kitchen:home.test"


class FakeHomeserver:
    """Just enough of the client-server API: `/sync` hands out queued events, sent messages and uploads are kept,
    media are served back, invitations are recorded."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.invites: list[str] = []
        self.joined: list[str] = []
        self.sent: list[dict[str, Any]] = []
        self.media: dict[str, bytes] = {}
        self.history = [message(ADA, {"msgtype": "m.text", "body": "said before the start"})]
        self.transport = httpx.MockTransport(self.handle)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"errcode": "M_UNKNOWN_TOKEN", "error": "Invalid access token"})
        path = request.url.path
        if path.endswith("/account/whoami"):
            return httpx.Response(200, json={"user_id": BOT})
        if path.endswith("/sync"):
            return await self.sync(request)
        if "/join/" in path:
            self.joined.append(httpx.URL(path).path.rsplit("/", 1)[1])
            return httpx.Response(200, json={})
        if "/send/m.room.message/" in path:
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"event_id": f"$e{len(self.sent)}"})
        if "/typing/" in path:
            return httpx.Response(200, json={})
        if path == "/_matrix/media/v3/upload":
            uri = f"mxc://home.test/up{len(self.media)}"
            self.media[uri] = request.content
            return httpx.Response(200, json={"content_uri": uri})
        if path.startswith("/_matrix/client/v1/media/download/"):
            uri = "mxc://" + path.removeprefix("/_matrix/client/v1/media/download/")
            return httpx.Response(200, content=self.media[uri]) if uri in self.media else httpx.Response(404)
        return httpx.Response(404, json={"errcode": "M_UNRECOGNIZED"})

    async def sync(self, request: httpx.Request) -> httpx.Response:
        if "since" not in request.url.params:
            rooms: dict[str, Any] = {"join": timeline(self.history)}
            if self.invites:
                rooms["invite"], self.invites = {room: {} for room in self.invites}, []
            return httpx.Response(200, json={"next_batch": "s0", "rooms": rooms})
        rooms: dict[str, Any] = {}
        if self.invites:
            rooms["invite"] = {room: {} for room in self.invites}
            self.invites = []
        try:
            event = await asyncio.wait_for(self.events.get(), timeout=0.05)
            rooms["join"] = timeline([event])
        except TimeoutError:
            pass
        return httpx.Response(200, json={"next_batch": f"s{len(self.sent)}", "rooms": rooms})

    def say(self, content: dict[str, Any], sender: str = ADA) -> None:
        self.events.put_nowait(message(sender, content))

    def texts(self) -> list[str]:
        return [m["body"] for m in self.sent if m["msgtype"] == "m.text"]

    def voices(self) -> list[bytes]:
        return [self.media[m["url"]] for m in self.sent if VOICE in m]


def message(sender: str, content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "m.room.message", "sender": sender, "content": content, "origin_server_ts": 1_700_000_000_000}


def timeline(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {ROOM: {"timeline": {"events": events}}}


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


@asynccontextmanager
async def serving(server: FakeHomeserver, assistant: Assistant, token: str = TOKEN) -> AsyncGenerator[MatrixChannel]:
    channel = MatrixChannel(
        "matrix", homeserver="https://home.test", token=token, poll_timeout_s=1, transport=server.transport
    )
    task = asyncio.create_task(channel.serve(assistant))
    try:
        yield channel
    finally:
        await channel.close()
        await asyncio.wait_for(task, 2)


class MatrixPlatform(Platform):
    def __init__(self, server: FakeHomeserver, channel: MatrixChannel) -> None:
        self.channel = channel
        self.server = server

    async def send(self, text: str, *attachments: Attachment) -> None:
        if not attachments:
            self.server.say({"msgtype": "m.text", "body": text})
        for n, file in enumerate(attachments):
            uri = f"mxc://home.test/in{n}"
            self.server.media[uri] = file.data
            msgtype = {AttachmentKind.IMAGE: "m.image", AttachmentKind.FILE: "m.file"}.get(file.kind, "m.audio")
            content = {"msgtype": msgtype, "url": uri, "info": {"mimetype": file.media_type}}
            content |= {"body": text, "filename": "file"} if text else {"body": "file"}
            if file.kind is AttachmentKind.VOICE:
                content[VOICE] = {}
            self.server.say(content)

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.server.sent) >= count)

    def texts(self) -> list[str]:
        return self.server.texts()

    def voices(self) -> list[bytes]:
        return self.server.voices()


class TestMatrixMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        server = FakeHomeserver()
        async with serving(server, assistant) as channel:
            yield MatrixPlatform(server, channel)


async def test_the_bot_joins_where_it_is_invited_and_answers_only_after_its_start() -> None:
    server = FakeHomeserver()
    server.invites.append(ROOM)
    assistant = ScriptedAssistant(lambda message: f"echo: {message.text}")
    async with serving(server, assistant):
        server.say({"msgtype": "m.text", "body": "bonjour"})
        await eventually(lambda: bool(server.sent))
    assert server.joined == [ROOM]
    assert server.texts() == ["echo: bonjour"], "what was said before the start is not answered"


async def test_its_own_messages_and_encrypted_ones_are_not_answered() -> None:
    server = FakeHomeserver()
    assistant = ScriptedAssistant(lambda message: f"echo: {message.text}")
    async with serving(server, assistant):
        server.say({"msgtype": "m.text", "body": "loop?"}, sender=BOT)
        server.events.put_nowait({"type": "m.room.encrypted", "sender": ADA, "content": {"ciphertext": "…"}})
        server.say({"msgtype": "m.text", "body": "en clair"})
        await eventually(lambda: bool(server.sent))
        await asyncio.sleep(0.1)
    assert server.texts() == ["echo: en clair"]


async def test_a_refused_token_stops_the_channel() -> None:
    with pytest.raises(ProviderError):
        await MatrixChannel(
            "matrix", homeserver="https://home.test", token="wrong", transport=FakeHomeserver().transport
        ).serve(ScriptedAssistant(lambda message: "?"))


async def test_an_invitation_sent_while_the_bot_was_stopped_is_joined() -> None:
    server = FakeHomeserver()
    server.invites.append(ROOM)  # listed by the first sync, the one whose history is skipped
    async with serving(server, ScriptedAssistant(lambda message: "?")):
        await eventually(lambda: bool(server.joined))
    assert server.joined == [ROOM]
