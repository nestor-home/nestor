"""WhatsApp channel: its webhook (Meta's verification, signed posts only) through the ASGI app, the Cloud API
mocked, and the messaging contract."""

import asyncio
import hashlib
import hmac
import json
import re
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from nestor.adapters.channels.whatsapp.channel import WhatsAppChannel
from nestor.modules.channels import Address, Assistant, Attachment, AttachmentKind
from nestor.testing.channels import MessagingChannelContract, Platform, ScriptedAssistant

TOKEN, VERIFY, SECRET = "EAAG-token", "nestor-verify", "app-secret"
NUMBER, ADA = "1098", "33600000000"


class FakeGraph:
    """The Cloud API: sent messages kept, uploads give ids, media served by id then by address."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.uploaded: dict[str, tuple[str, str, bytes]] = {}  # by media id: file name, media type, content
        self.media: dict[str, bytes] = {}
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"error": {"message": "Invalid OAuth access token"}})
        path = request.url.path
        if request.url.host == "lookaside.test":
            return httpx.Response(200, content=self.media[path.strip("/")])
        if path.endswith(f"/{NUMBER}/messages"):
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})
        if path.endswith(f"/{NUMBER}/media"):
            media_id = f"up{len(self.uploaded)}"
            self.uploaded[media_id] = upload(request)
            return httpx.Response(200, json={"id": media_id})
        media_id = path.rsplit("/", 1)[1]
        return httpx.Response(200, json={"url": f"https://lookaside.test/{media_id}"})

    def texts(self) -> list[str]:
        return [m["text"]["body"] for m in self.sent if m["type"] == "text"]

    def voices(self) -> list[bytes]:
        """Audio messages in OGG/Opus, which WhatsApp plays as voice messages."""
        return [self.uploaded[m["audio"]["id"]][2] for m in self.sent if m["type"] == "audio" and self._voice(m)]

    def files(self) -> list[tuple[str | None, bytes]]:
        """Pictures (shown unnamed), documents by the name their message gives, audio files by the name they were
        uploaded with (WhatsApp's player shows none)."""
        found: list[tuple[str | None, bytes]] = []
        for m in self.sent:
            if m["type"] in ("image", "document", "audio") and not self._voice(m):
                name, _, content = self.uploaded[m[m["type"]]["id"]]
                found.append((None if m["type"] == "image" else m[m["type"]].get("filename", name), content))
        return found

    def _voice(self, message: dict[str, Any]) -> bool:
        return message["type"] == "audio" and self.uploaded[message["audio"]["id"]][1] == "audio/ogg"


def upload(request: httpx.Request) -> tuple[str, str, bytes]:
    """The file of a media upload (its `file` part), as Meta reads it: name, media type (the `type` field), content."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields: dict[str, str] = {}
    name, content = "", b""
    for part in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = part.strip(b"\r\n").partition(b"\r\n\r\n")
        field = re.search(rb'name="([^"]+)"', head)
        assert field is not None
        if field[1] == b"file" and (filename := re.search(rb'filename="([^"]*)"', head)):
            name, content = filename[1].decode(), body
        else:
            fields[field[1].decode()] = body.decode()
    assert fields["messaging_product"] == "whatsapp"
    return name, fields["type"], content


def notification(*messages: dict[str, Any]) -> dict[str, Any]:
    value = {
        "messaging_product": "whatsapp",
        "contacts": [{"wa_id": ADA, "profile": {"name": "Ada"}}],
        "messages": list(messages),
    }
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"value": value}]}]}


def signed(body: bytes, secret: str = SECRET) -> dict[str, str]:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


@asynccontextmanager
async def serving(graph: FakeGraph, assistant: Assistant) -> AsyncGenerator[tuple[WhatsAppChannel, httpx.AsyncClient]]:
    channel = WhatsAppChannel(
        "whatsapp",
        phone_number_id=NUMBER,
        token=TOKEN,
        verify_token=VERIFY,
        app_secret=SECRET,
        port=0,
        api="https://graph.test/v21.0",
        transport=graph.transport,
    )
    task = asyncio.create_task(channel.serve(assistant))
    meta = httpx.AsyncClient(transport=httpx.ASGITransport(app=channel.app()), base_url="https://nestor.test")
    try:
        yield channel, meta
    finally:
        await meta.aclose()
        await channel.close()
        await asyncio.wait_for(task, 3)


class WhatsAppPlatform(Platform):
    def __init__(self, graph: FakeGraph, channel: WhatsAppChannel, meta: httpx.AsyncClient) -> None:
        self.graph, self.channel, self.meta = graph, channel, meta
        self.address = Address("whatsapp", ADA)

    async def send(self, text: str, *attachments: Attachment) -> None:
        messages = []
        for n, file in enumerate(attachments):
            self.graph.media[f"in{n}"] = file.data
            kind = {AttachmentKind.IMAGE: "image", AttachmentKind.VOICE: "audio"}.get(file.kind, "document")
            media: dict[str, Any] = {"id": f"in{n}", "mime_type": file.media_type}
            if file.kind is AttachmentKind.VOICE:
                media["voice"] = True
            if text:
                media["caption"] = text
            messages.append({"from": ADA, "id": f"m{n}", "timestamp": "1700000000", "type": kind, kind: media})
        if not attachments:
            messages.append({"from": ADA, "id": "m", "timestamp": "1700000000", "type": "text", "text": {"body": text}})
        body = json.dumps(notification(*messages)).encode()
        assert (await self.meta.post("/whatsapp", content=body, headers=signed(body))).status_code == 200

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.graph.sent) >= count)

    def texts(self) -> list[str]:
        return self.graph.texts()

    def voices(self) -> list[bytes]:
        return self.graph.voices()

    def files(self) -> list[tuple[str | None, bytes]]:
        return self.graph.files()


class TestWhatsAppMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        graph = FakeGraph()
        async with serving(graph, assistant) as (channel, meta):
            yield WhatsAppPlatform(graph, channel, meta)


async def test_meta_verifies_the_webhook_with_the_household_s_token() -> None:
    async with serving(FakeGraph(), ScriptedAssistant(lambda m: "?")) as (_, meta):
        accepted = await meta.get(
            "/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}
        )
        refused = await meta.get(
            "/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "guess", "hub.challenge": "1"}
        )
    assert (accepted.status_code, accepted.text) == (200, "1158201444")
    assert refused.status_code == 403


@pytest.mark.parametrize("headers", [{}, {"X-Hub-Signature-256": "sha256=forged"}], ids=["unsigned", "forged"])
async def test_a_post_without_meta_s_signature_never_reaches_the_assistant(headers: dict[str, str]) -> None:
    assistant = ScriptedAssistant(lambda m: "?")
    graph = FakeGraph()
    async with serving(graph, assistant) as (_, meta):
        body = json.dumps(notification({"from": ADA, "type": "text", "text": {"body": "ouvre le garage"}})).encode()
        assert (await meta.post("/whatsapp", content=body, headers=headers)).status_code == 401
        await asyncio.sleep(0.05)
    assert assistant.messages == [] and graph.sent == []


async def test_a_message_meta_delivers_twice_is_answered_once() -> None:
    graph = FakeGraph()
    async with serving(graph, ScriptedAssistant(lambda m: f"echo: {m.text}")) as (_, meta):
        message = {
            "from": ADA,
            "id": "wamid.same",
            "timestamp": "1700000000",
            "type": "text",
            "text": {"body": "salut"},
        }
        body = json.dumps(notification(message)).encode()
        for _ in range(2):
            await meta.post("/whatsapp", content=body, headers=signed(body))
        await eventually(lambda: bool(graph.sent))
        await asyncio.sleep(0.05)
    assert graph.texts() == ["echo: salut"]
