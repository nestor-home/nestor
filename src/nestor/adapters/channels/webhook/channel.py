"""The webhook channel: each message posted as JSON to one address, signed when a secret is set."""

import asyncio
import base64
import json

import httpx

from nestor.adapters.channels.messaging import files_sent
from nestor.adapters.channels.push import PushChannel
from nestor.adapters.common.http import HttpApi, signature
from nestor.modules.channels import Attachment, AttachmentKind

SIGNATURE = "X-Nestor-Signature"


class WebhookChannel(PushChannel):
    name = "webhook"
    brand = "webhook"
    sends = frozenset(AttachmentKind)  # every file goes in the body, whatever it is

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
        """One post with the files in its body; the text alone when the address refuses them."""
        if attachments and await files_sent(
            self, conversation, attachments, self._post(conversation, text, attachments)
        ):
            return
        await self._post(conversation, text, ())

    async def _post(self, conversation: str, text: str, attachments: tuple[Attachment, ...]) -> None:
        body = await asyncio.to_thread(_body, conversation, text, attachments)  # documents of many MB, in base64
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers[SIGNATURE] = signature(self._secret, body)
        await self._api.request("POST", self._url, content=body, headers=headers)

    async def close(self) -> None:
        await super().close()
        await self._api.aclose()


def _body(conversation: str, text: str, attachments: tuple[Attachment, ...]) -> bytes:
    files = [
        {"kind": a.kind.value, "media_type": a.media_type, "name": a.name, "data": base64.b64encode(a.data).decode()}
        for a in attachments
    ]
    return json.dumps({"to": conversation, "text": text, "attachments": files}, ensure_ascii=False).encode()
