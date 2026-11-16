"""Slack channel against a fake Socket Mode server (a real WebSocket) and a mocked Web API: the messaging contract,
events acknowledged, a direct message answered and a channel only when the bot is mentioned (once), a picture
uploaded in three steps, a refused token."""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from websockets.asyncio.server import ServerConnection, serve

from nestor.adapters.channels.slack.channel import SlackChannel
from nestor.core import ProviderError
from nestor.modules.channels import Address, Assistant, Attachment, AttachmentKind
from nestor.testing.channels import MessagingChannelContract, Platform, ScriptedAssistant

APP, BOT = "xapp-1-secret", "xoxb-secret"
ADA = "U07"


class FakeSlack:
    """Socket Mode hands out queued events in envelopes and records the acknowledgements; the Web API keeps posted
    messages and the three steps of an upload, and shares in a channel only a file whose bytes arrived (`too_large`
    refuses every upload); private files are served to the bot's token only."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.acked: list[str] = []
        self.posted: list[dict[str, Any]] = []
        self.uploads: list[tuple[str, Any]] = []
        self.tickets: dict[str, str] = {}  # file id: the name asked for it
        self.received: dict[str, bytes] = {}
        self.shared: list[tuple[str, bytes]] = []  # the name shown in the channel, the bytes
        self.files: dict[str, bytes] = {}
        self.too_large = False
        self.port = 0
        self.transport = httpx.MockTransport(self.handle)

    async def socket(self, socket: ServerConnection) -> None:
        await socket.send(json.dumps({"type": "hello"}))
        closed = asyncio.ensure_future(socket.wait_closed())
        acks = asyncio.ensure_future(self._acks(socket))
        try:
            n = 0
            while True:
                event = asyncio.ensure_future(self.events.get())
                await asyncio.wait({event, closed}, return_when=asyncio.FIRST_COMPLETED)
                if closed.done():
                    event.cancel()
                    return
                n += 1
                envelope = {"envelope_id": f"env{n}", "type": "events_api", "payload": {"event": event.result()}}
                await socket.send(json.dumps(envelope))
        finally:
            acks.cancel()

    async def _acks(self, socket: ServerConnection) -> None:
        async for raw in socket:
            self.acked.append(json.loads(raw)["envelope_id"])

    def handle(self, request: httpx.Request) -> httpx.Response:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        path = request.url.path
        if request.url.host == "files.slack.test":
            if path.startswith("/upload/"):
                self.uploads.append(("bytes", request.content))
                self.received[path.removeprefix("/upload/")] = request.content
                return httpx.Response(200, text="OK")
            if token != BOT:
                return httpx.Response(403)
            return httpx.Response(200, content=self.files[path])
        if path.endswith("/apps.connections.open"):
            if token != APP:
                return httpx.Response(200, json={"ok": False, "error": "invalid_auth"})
            return httpx.Response(200, json={"ok": True, "url": f"ws://127.0.0.1:{self.port}"})
        if token != BOT:
            return httpx.Response(200, json={"ok": False, "error": "invalid_auth"})
        if path.endswith("/chat.postMessage"):
            self.posted.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/files.getUploadURLExternal"):
            if self.too_large:
                return httpx.Response(200, json={"ok": False, "error": "file_too_large"})
            form = dict(httpx.QueryParams(request.content.decode()))
            file_id = f"F{len(self.tickets) + 1}"
            self.tickets[file_id] = form["filename"]
            self.uploads.append(("ticket", form))
            upload_url = f"https://files.slack.test/upload/{file_id}"
            return httpx.Response(200, json={"ok": True, "upload_url": upload_url, "file_id": file_id})
        if path.endswith("/files.completeUploadExternal"):
            body = json.loads(request.content)
            self.uploads.append(("shared", body))
            if any(f["id"] not in self.received for f in body["files"]):
                return httpx.Response(200, json={"ok": False, "error": "file_not_found"})
            self.shared += [(f.get("title") or self.tickets[f["id"]], self.received[f["id"]]) for f in body["files"]]
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": False, "error": "unknown_method"})

    def say(
        self,
        text: str,
        *,
        channel: str = "D1",
        direct: bool = True,
        kind: str = "message",
        files: list[dict] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "type": kind,
            "channel": channel,
            "user": ADA,
            "text": text,
            "ts": "1700000000.000100",
            "channel_type": "im" if direct else "channel",
        }
        if files:
            event |= {"files": files, "subtype": "file_share"}
        self.events.put_nowait(event)

    def texts(self) -> list[str]:
        return [p["text"] for p in self.posted]


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


@asynccontextmanager
async def serving(slack: FakeSlack, assistant: Assistant, app_token: str = APP) -> AsyncGenerator[SlackChannel]:
    async with serve(slack.socket, "127.0.0.1", 0) as server:
        slack.port = next(iter(server.sockets)).getsockname()[1]
        channel = SlackChannel(
            "slack",
            app_token=app_token,
            bot_token=BOT,
            api="https://slack.test/api",
            retry_delay_s=0.01,
            transport=slack.transport,
        )
        task = asyncio.create_task(channel.serve(assistant))
        try:
            yield channel
        finally:
            await channel.close()
            await asyncio.wait_for(task, 2)


class SlackPlatform(Platform):
    def __init__(self, slack: FakeSlack, channel: SlackChannel) -> None:
        self.channel = channel
        self.address = Address(channel.channel_id, "D1")
        self.slack = slack

    async def send(self, text: str, *attachments: Attachment) -> None:
        files = []
        for n, file in enumerate(attachments):
            self.slack.files[f"/f/{n}"] = file.data
            entry = {
                "id": f"F{n}",
                "name": "file",
                "mimetype": file.media_type,
                "size": len(file.data),
                "url_private_download": f"https://files.slack.test/f/{n}",
            }
            if file.kind is AttachmentKind.VOICE:
                entry["subtype"] = "slack_audio"
            files.append(entry)
        self.slack.say(text, files=files)

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.slack.posted) >= count)

    def texts(self) -> list[str]:
        return self.slack.texts()

    def voices(self) -> list[bytes]:
        return []

    def refuse_files(self) -> None:
        self.slack.too_large = True

    def files(self) -> list[tuple[str | None, bytes]]:
        return list(self.slack.shared)


class TestSlackMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        slack = FakeSlack()
        async with serving(slack, assistant) as channel:
            yield SlackPlatform(slack, channel)


def echo(message: Any) -> str:
    return f"echo: {message.text}"


async def test_events_are_acknowledged_and_a_channel_is_answered_once_when_the_bot_is_mentioned() -> None:
    slack = FakeSlack()
    async with serving(slack, ScriptedAssistant(echo)):
        slack.say("<@UBOT> tu es là ?", channel="C1", direct=False)  # the message event of a mention
        slack.say("<@UBOT> tu es là ?", channel="C1", direct=False, kind="app_mention")
        slack.say("bonjour")
        await eventually(lambda: len(slack.posted) == 2)
        await eventually(lambda: len(slack.acked) == 3)
        await asyncio.sleep(0.05)
    assert sorted(slack.texts()) == ["echo: bonjour", "echo: tu es là ?"]
    assert {p["channel"] for p in slack.posted} == {"C1", "D1"}


async def test_a_picture_is_uploaded_in_three_steps() -> None:
    slack = FakeSlack()
    picture = Attachment(kind=AttachmentKind.IMAGE, data=b"png", media_type="image/png", name="dessin.png")
    async with serving(slack, ScriptedAssistant(lambda message: "Voilà.", files=(picture,))):
        slack.say("dessine")
        await eventually(lambda: any(step == "shared" for step, _ in slack.uploads))
    (_, ticket), (_, sent), (_, shared) = slack.uploads
    assert ticket == {"filename": "dessin.png", "length": "3"}
    assert sent == b"png"
    assert shared == {"files": [{"id": "F1", "title": "dessin.png"}], "channel_id": "D1"}


async def test_a_refused_token_stops_the_channel() -> None:
    slack = FakeSlack()
    channel = SlackChannel(
        "slack", app_token="xapp-wrong", bot_token=BOT, api="https://slack.test/api", transport=slack.transport
    )
    with pytest.raises(ProviderError, match="invalid_auth"):
        await asyncio.wait_for(channel.serve(ScriptedAssistant(echo)), 2)
    await channel.close()
