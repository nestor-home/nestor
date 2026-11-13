"""Signal channel against a fake signal-cli-rest-api: the messaging contract, groups answered in the group, receipts
ignored, pictures sent as attachments, and the polling that gets past an outage."""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from nestor.adapters.channels.signal.channel import SignalChannel
from nestor.modules.channels import Assistant, Attachment, AttachmentKind
from nestor.testing.channels import MessagingChannelContract, Platform, ScriptedAssistant

BOT, ADA = "+33100000000", "+33600000000"


class FakeSignalApi:
    """`/v1/receive` hands out queued envelopes, `/v2/send` keeps what was sent, attachments are served by id;
    `down` answers 503 a number of times first."""

    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.down = 0
        self.transport = httpx.MockTransport(self.handle)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == f"/v1/receive/{BOT}":
            if not (self.envelopes or self.down):
                await asyncio.sleep(0.01)  # a long poll that waits for messages to come
            if self.down:
                self.down -= 1
                return httpx.Response(503, json={"error": "signal-cli is starting"})
            found, self.envelopes = self.envelopes, []
            return httpx.Response(200, json=[{"envelope": e, "account": BOT} for e in found])
        if path == "/v2/send":
            self.sent.append(json.loads(request.content))
            return httpx.Response(201, json={"timestamp": "1"})
        if path.startswith("/v1/attachments/"):
            return httpx.Response(200, content=self.files[path.rsplit("/", 1)[1]])
        return httpx.Response(404, json={"error": "not found"})

    def say(self, text: str, *files: dict[str, Any], group: str | None = None, sender: str = ADA) -> None:
        message: dict[str, Any] = {"message": text or None, "attachments": list(files)}
        if group:
            message["groupInfo"] = {"groupId": group, "type": "DELIVER"}
        self.envelopes.append({"sourceNumber": sender, "sourceName": "Ada", "timestamp": 1, "dataMessage": message})

    def texts(self) -> list[str]:
        return [m["message"] for m in self.sent if m["message"]]


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


@asynccontextmanager
async def serving(api: FakeSignalApi, assistant: Assistant) -> AsyncGenerator[SignalChannel]:
    channel = SignalChannel(
        "signal",
        url="http://signal.test",
        number=BOT,
        wait_s=1,
        retry_delay_s=0.01,
        transport=api.transport,
    )
    task = asyncio.create_task(channel.serve(assistant))
    try:
        yield channel
    finally:
        await channel.close()
        await asyncio.wait_for(task, 2)


class SignalPlatform(Platform):
    def __init__(self, api: FakeSignalApi, channel: SignalChannel) -> None:
        self.channel = channel
        self.api = api

    async def send(self, text: str, *attachments: Attachment) -> None:
        files = []
        for n, file in enumerate(attachments):
            self.api.files[f"a{n}"] = file.data
            name = None if file.kind is AttachmentKind.VOICE else "file"
            files.append({"id": f"a{n}", "contentType": file.media_type, "filename": name, "size": len(file.data)})
        self.api.say(text, *files)

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.api.sent) >= count)

    def texts(self) -> list[str]:
        return self.api.texts()

    def voices(self) -> list[bytes]:
        return []


class TestSignalMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        api = FakeSignalApi()
        async with serving(api, assistant) as channel:
            yield SignalPlatform(api, channel)


async def test_a_group_is_answered_in_the_group_and_receipts_are_ignored() -> None:
    api = FakeSignalApi()
    api.down = 2
    api.envelopes.append({"sourceNumber": ADA, "timestamp": 1, "receiptMessage": {"isRead": True}})
    api.say("on mange quoi ?", group="family")
    async with serving(api, ScriptedAssistant(lambda message: f"echo: {message.text}")):
        await eventually(lambda: bool(api.sent))
    [sent] = api.sent
    assert sent["recipients"] == ["group." + base64.b64encode(b"family").decode()]
    assert api.texts() == ["echo: on mange quoi ?"], "after the outage, and the receipt left alone"


async def test_a_picture_the_assistant_made_goes_as_an_attachment() -> None:
    api = FakeSignalApi()
    picture = Attachment(kind=AttachmentKind.IMAGE, data=b"png", media_type="image/png", name="dessin.png")
    api.say("dessine")
    async with serving(api, ScriptedAssistant(lambda message: "Voilà.", pictures=(picture,))):
        await eventually(lambda: bool(api.sent))
    [sent] = api.sent
    assert sent["message"] == "Voilà."
    assert sent["base64_attachments"] == [
        f"data:image/png;filename=dessin.png;base64,{base64.b64encode(b'png').decode()}"
    ]
