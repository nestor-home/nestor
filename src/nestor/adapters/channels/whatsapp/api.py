"""Meta's Cloud API for one business number: the media a person sent, the files uploaded, the messages sent."""

from collections.abc import Mapping
from typing import Any

import httpx

from nestor.adapters.common.http import HttpApi
from nestor.modules.channels import Attachment, AttachmentKind

GRAPH = "https://graph.facebook.com/v21.0"
MESSAGE_TYPES = {  # the message that carries each kind of file
    AttachmentKind.IMAGE: "image",
    AttachmentKind.VOICE: "audio",  # OGG/Opus, which WhatsApp plays as a voice message
    AttachmentKind.AUDIO: "audio",
    AttachmentKind.FILE: "document",
}


class CloudApi:
    def __init__(
        self, phone_number_id: str, token: str, *, api: str = GRAPH, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._number = phone_number_id
        auth = {"Authorization": f"Bearer {token}"}
        self._api = HttpApi("whatsapp", api, headers=auth, secret=token, transport=transport)

    async def media(self, media_id: str) -> bytes:
        url = (await self._api.request("GET", f"/{media_id}")).json()["url"]
        return (await self._api.request("GET", url)).content  # Meta's media host asks for the token too

    async def send_file(self, to: str, file: Attachment) -> None:
        """`file` uploaded, then sent as the message of its kind; a document shows its name (a file without one takes
        its kind's, with the extension of its type: `file.pdf`)."""
        name = file.file_name
        kind = MESSAGE_TYPES[file.kind]
        content = {"id": await self._upload(file, name)}
        await self.send(to, kind, content | ({"filename": name} if kind == "document" else {}))

    async def _upload(self, file: Attachment, name: str) -> str:
        uploaded = await self._api.request(
            "POST",
            f"/{self._number}/media",
            data={"messaging_product": "whatsapp", "type": file.media_type},
            files={"file": (name, file.data, file.media_type)},
        )
        return str(uploaded.json()["id"])

    async def send(self, to: str, kind: str, content: Mapping[str, Any]) -> None:
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": kind, kind: content}
        await self._api.request("POST", f"/{self._number}/messages", json=body)

    async def aclose(self) -> None:
        await self._api.aclose()
