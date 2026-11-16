"""The webhook channel against a mocked server: its body, signed as GitHub signs its own, and the text alone when
the address refuses its files."""

import base64
import hashlib
import hmac
import json

import httpx

from nestor.adapters.channels.webhook.channel import SIGNATURE, WebhookChannel
from nestor.modules.channels import Address, Attachment, AttachmentKind, Medium
from nestor.testing.channels import DEVIS, SONG

from ..push import Recorder

PICTURE = Attachment(kind=AttachmentKind.IMAGE, data=b"png", media_type="image/png", name="dessin.png")


async def test_a_webhook_body_is_signed_with_its_secret() -> None:
    server = Recorder()
    async with WebhookChannel(
        "webhook", url="https://hooks.test/nestor", secret="s3cret", transport=server.transport
    ) as hook:
        await hook.send(Address("webhook", "lea"), "Le dîner est prêt.", Medium.WRITTEN, (PICTURE,))
    [posted] = server.requests
    assert str(posted.url) == "https://hooks.test/nestor", "the address as given, without a slash added"
    body = json.loads(posted.content)
    assert body["to"] == "lea" and body["text"] == "Le dîner est prêt."
    assert body["attachments"] == [
        {"kind": "image", "media_type": "image/png", "name": "dessin.png", "data": base64.b64encode(b"png").decode()}
    ]
    expected = hmac.new(b"s3cret", posted.content, hashlib.sha256).hexdigest()
    assert posted.headers[SIGNATURE] == f"sha256={expected}"


async def test_a_document_and_an_audio_file_go_in_the_body_by_their_name() -> None:
    server = Recorder()
    async with WebhookChannel("webhook", url="https://hooks.test/nestor", transport=server.transport) as hook:
        assert {AttachmentKind.FILE, AttachmentKind.AUDIO} <= hook.sends, "or the core leaves them out"
        await hook.send(Address("webhook", "lea"), "Le devis corrigé, et ta chanson.", Medium.WRITTEN, (DEVIS, SONG))
    [posted] = server.requests
    assert json.loads(posted.content)["attachments"] == [
        {
            "kind": "file",
            "media_type": "application/pdf",
            "name": "devis.pdf",
            "data": base64.b64encode(DEVIS.data).decode(),
        },
        {
            "kind": "audio",
            "media_type": "audio/mpeg",
            "name": "chanson.mp3",
            "data": base64.b64encode(SONG.data).decode(),
        },
    ]


async def test_the_text_goes_alone_when_the_address_refuses_its_files() -> None:
    posted: list[dict[str, object]] = []

    def server(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["attachments"]:
            return httpx.Response(413, text="Payload Too Large")
        posted.append(body)
        return httpx.Response(200)

    async with WebhookChannel(
        "webhook", url="https://hooks.test/nestor", transport=httpx.MockTransport(server)
    ) as hook:
        await hook.send(Address("webhook", "lea"), "Le devis corrigé.", Medium.WRITTEN, (DEVIS,))
    assert posted == [{"to": "lea", "text": "Le devis corrigé.", "attachments": []}]
