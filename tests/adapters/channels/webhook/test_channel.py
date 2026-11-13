"""The webhook channel against a mocked server: its body, signed as GitHub signs its own."""

import base64
import hashlib
import hmac
import json

from nestor.adapters.channels.webhook.channel import SIGNATURE, WebhookChannel
from nestor.modules.channels import Address, Attachment, AttachmentKind, Medium

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
