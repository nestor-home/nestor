"""The ntfy channel: a notification for each message, with its files (pictures, documents, audio)."""

import logging

import httpx

from nestor.adapters.channels.push import PushChannel
from nestor.adapters.common.http import HttpApi
from nestor.core import ProviderError
from nestor.modules.channels import Attachment, AttachmentKind

logger = logging.getLogger(__name__)


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
        files = [a for a in attachments if a.kind in self.sends]
        if not files:
            await self._api.request("POST", f"/{conversation}", content=text.encode())
            return
        for n, file in enumerate(files):
            words = text if n == 0 else ""
            try:
                await self._attach(conversation, file, words)
            except ProviderError as error:
                logger.warning("ntfy: a %s could not be sent to %s: %s", file.kind, conversation, error)
                if words:
                    await self._api.request("POST", f"/{conversation}", content=words.encode())

    async def _attach(self, conversation: str, file: Attachment, text: str) -> None:
        params = {"filename": file.file_name}
        if text:
            params["message"] = text  # in the query, where any character goes (a header takes ASCII only)
        await self._api.request("PUT", f"/{conversation}", content=file.data, params=params)

    async def close(self) -> None:
        await super().close()
        await self._api.aclose()
