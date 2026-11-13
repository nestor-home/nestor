"""The webhook channel: each message posted as JSON to one address, signed when a secret is set."""

import base64
import hashlib
import hmac
import json

import httpx

from nestor.adapters.channels.push import PushChannel
from nestor.adapters.common.http import HttpApi
from nestor.modules.channels import Attachment, AttachmentKind

SIGNATURE = "X-Nestor-Signature"


class WebhookChannel(PushChannel):
    name = "webhook"
    brand = "webhook"
    sends = frozenset({AttachmentKind.IMAGE, AttachmentKind.VOICE})

    def __init__(
        self,
        channel_id: str,
        *,
        url: str,
        secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(channel_id)
        self._url, self._secret = url, secret
        self._api = HttpApi("webhook", "", secret=secret, transport=transport)  # the address as given, no slash added

    async def push(self, conversation: str, text: str, attachments: tuple[Attachment, ...]) -> None:
        files = [
            {
                "kind": a.kind.value,
                "media_type": a.media_type,
                "name": a.name,
                "data": base64.b64encode(a.data).decode(),
            }
            for a in attachments
        ]
        body = json.dumps({"to": conversation, "text": text, "attachments": files}, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"}
        if self._secret:
            digest = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
            headers[SIGNATURE] = f"sha256={digest}"
        await self._api.request("POST", self._url, content=body, headers=headers)

    async def close(self) -> None:
        await super().close()
        await self._api.aclose()
