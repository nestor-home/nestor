"""Meta's Cloud API for one business number: the media a person sent, the files uploaded, the messages sent."""

from collections.abc import Mapping
from typing import Any

import httpx

from nestor.adapters.common.http import HttpApi
from nestor.modules.channels import Attachment, AttachmentKind

GRAPH = "https://graph.facebook.com/v21.0"


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

    async def upload(self, file: Attachment) -> str:
        name = file.name or ("voice.ogg" if file.kind is AttachmentKind.VOICE else "image")
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
