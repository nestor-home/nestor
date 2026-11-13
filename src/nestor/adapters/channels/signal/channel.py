"""The Signal channel: a number served by signal-cli-rest-api, long-polling `/v1/receive`, a `MessagingChannel`."""

import base64
import logging
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from nestor.adapters.channels.messaging import Incoming, MessagingChannel, Pending, kind_of
from nestor.adapters.common.http import HttpApi
from nestor.core import ProviderError
from nestor.modules.channels import Address, Answer, AttachmentKind, Sender

logger = logging.getLogger(__name__)

PROVIDER = "signal"
GROUP = "group."  # how signal-cli-rest-api names a group: this prefix and its id in base64


class SignalChannel(MessagingChannel):
    name = "signal"
    brand = "signal"
    sends = frozenset({AttachmentKind.IMAGE})

    def __init__(
        self,
        channel_id: str,
        *,
        url: str,
        number: str,
        wait_s: int = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        **common: Any,
    ) -> None:
        """`wait_s`: how long a poll waits for messages to come. `common`: what every `MessagingChannel` takes."""
        super().__init__(channel_id, **common)
        self._api = HttpApi(PROVIDER, url.rstrip("/"), timeout_s=wait_s + 30.0, transport=transport)
        self._number, self._wait_s = number, wait_s

    async def receive(self) -> AsyncIterator[Incoming]:
        """Polls `/v1/receive`, which waits up to `wait_s` for messages; raises `ProviderError` when the number is
        unknown to signal-cli, and retries other failures."""
        failures = 0
        params = {"timeout": str(self._wait_s)}
        while not self.closed:
            try:
                found = await self.unless_closed(self._api.request("GET", f"/v1/receive/{self._number}", params=params))
            except ProviderError as error:
                await self.retry_later(error, failures)
                failures += 1
                continue
            if found is None:
                return
            failures = 0
            for envelope in _envelopes(found):
                if (incoming := self._incoming(envelope)) is not None:
                    yield incoming

    async def disconnect(self) -> None:
        await self._api.aclose()

    async def deliver(self, conversation: str, answer: Answer) -> None:
        pictures = [a for a in answer.attachments if a.kind is AttachmentKind.IMAGE]
        body: dict[str, Any] = {"message": answer.text, "number": self._number, "recipients": [conversation]}
        if pictures:
            body["base64_attachments"] = [
                f"data:{p.media_type};filename={p.name or 'image'};base64,{base64.b64encode(p.data).decode()}"
                for p in pictures
            ]
        await self._api.request("POST", "/v2/send", json=body)

    def _incoming(self, envelope: Mapping[str, Any]) -> Incoming | None:
        message = envelope.get("dataMessage")
        sender = envelope.get("sourceNumber") or envelope.get("sourceUuid") or envelope.get("source")
        if not isinstance(message, Mapping) or not sender:
            return None  # a receipt, a typing indicator, a sync message
        group = (message.get("groupInfo") or {}).get("groupId")
        conversation = GROUP + base64.b64encode(group.encode()).decode() if group else str(sender)
        at = datetime.fromtimestamp(envelope["timestamp"] / 1000, tz=UTC) if "timestamp" in envelope else None
        return Incoming(
            address=Address(self.channel_id, conversation),
            sender=Sender(str(sender), envelope.get("sourceName") or None),
            text=str(message.get("message") or ""),
            files=tuple(self._pending(a) for a in message.get("attachments") or [] if a.get("id")),
            at=at,
        )

    def _pending(self, attachment: Mapping[str, Any]) -> Pending:
        media_type = str(attachment.get("contentType") or "application/octet-stream")
        name = attachment.get("filename")
        kind = kind_of(media_type, voice=media_type.startswith("audio/") and not name)  # a voice note has no name
        attachment_id = attachment["id"]

        async def fetch() -> bytes:
            return (await self._api.request("GET", f"/v1/attachments/{attachment_id}")).content

        return Pending(kind=kind, media_type=media_type, fetch=fetch, name=name, size=attachment.get("size"))


def _envelopes(response: httpx.Response) -> list[Mapping[str, Any]]:
    try:
        found = response.json()
    except ValueError:
        logger.warning("signal: /v1/receive answered something that is not JSON")
        return []
    return [r["envelope"] for r in found if isinstance(r, dict) and isinstance(r.get("envelope"), dict)]
