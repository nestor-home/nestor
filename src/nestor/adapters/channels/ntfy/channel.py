"""The ntfy channel: a notification for each message, with its pictures."""

import httpx

from nestor.adapters.channels.push import PushChannel
from nestor.adapters.common.http import HttpApi
from nestor.modules.channels import Attachment, AttachmentKind


class NtfyChannel(PushChannel):
    name = "ntfy"
    brand = "ntfy"
    sends = frozenset({AttachmentKind.IMAGE})

    def __init__(
        self, channel_id: str, *, url: str, token: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(channel_id)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        self._api = HttpApi("ntfy", url.rstrip("/"), headers=headers, secret=token, transport=transport)

    async def push(self, conversation: str, text: str, attachments: tuple[Attachment, ...]) -> None:
        pictures = [a for a in attachments if a.kind is AttachmentKind.IMAGE]
        if not pictures:
            await self._api.request("POST", f"/{conversation}", content=text.encode())
            return
        for n, picture in enumerate(pictures):  # one notification a picture, the words with the first
            params = {"filename": picture.name or f"image.{picture.media_type.rpartition('/')[2]}"}
            if n == 0 and text:
                params["message"] = text  # in the query, where any character goes (a header takes ASCII only)
            await self._api.request("PUT", f"/{conversation}", content=picture.data, params=params)

    async def close(self) -> None:
        await super().close()
        await self._api.aclose()
