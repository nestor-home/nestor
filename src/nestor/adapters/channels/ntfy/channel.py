"""The ntfy channel: a notification for each message, with its files (pictures, documents, audio)."""

import httpx

from nestor.adapters.channels.messaging import files_sent
from nestor.adapters.channels.push import PushChannel
from nestor.adapters.common.http import HttpApi
from nestor.modules.channels import Attachment, AttachmentKind


class NtfyChannel(PushChannel):
    name = "ntfy"
    brand = "ntfy"
    sends = frozenset({AttachmentKind.IMAGE, AttachmentKind.FILE, AttachmentKind.AUDIO})

    def __init__(
        self, channel_id: str, *, url: str, token: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(channel_id)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        self._api = HttpApi("ntfy", url.rstrip("/"), headers=headers, secret=token, transport=transport)

    async def push(self, conversation: str, text: str, attachments: tuple[Attachment, ...]) -> None:
        """One notification a file (ntfy takes one attachment a message), the words with the first; written alone
        when that file cannot be sent."""
        if not attachments:
            await self._api.request("POST", f"/{conversation}", content=text.encode())
            return
        for n, file in enumerate(attachments):
            words = text if n == 0 else ""
            if not await files_sent(self, conversation, (file,), self._attach(conversation, file, words)) and words:
                await self._api.request("POST", f"/{conversation}", content=words.encode())

    async def _attach(self, conversation: str, file: Attachment, text: str) -> None:
        params = {"filename": file.file_name}
        if text:
            params["message"] = text  # in the query, where any character goes (a header takes ASCII only)
        await self._api.request("PUT", f"/{conversation}", content=file.data, params=params)

    async def close(self) -> None:
        await super().close()
        await self._api.aclose()
