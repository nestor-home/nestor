"""The Slack channel: a Slack app in Socket Mode answering through the Web API, a `MessagingChannel`."""

import json
import logging
import re
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from nestor.adapters.channels.messaging import (
    Incoming,
    MessagingChannel,
    Pending,
    kind_of,
    split_text,
)
from nestor.adapters.common.http import HttpApi
from nestor.core import ProviderError
from nestor.modules.channels import Address, Answer, Attachment, AttachmentKind, Sender

logger = logging.getLogger(__name__)

PROVIDER = "slack"
API = "https://slack.com/api"
MESSAGE_LIMIT = 4000  # what Slack advises for one message's text
_MENTION = re.compile(r"<@[A-Z0-9]+>")


class SlackChannel(MessagingChannel):
    name = "slack"
    brand = "slack"
    sends = frozenset({AttachmentKind.IMAGE})

    def __init__(
        self,
        channel_id: str,
        *,
        app_token: str,
        bot_token: str,
        api: str = API,
        transport: httpx.AsyncBaseTransport | None = None,
        **common: Any,
    ) -> None:
        """`common`: what every `MessagingChannel` takes (`apology`, `retry_delay_s`…)."""
        super().__init__(channel_id, **common)
        app, bot = {"Authorization": f"Bearer {app_token}"}, {"Authorization": f"Bearer {bot_token}"}
        self._app = HttpApi(PROVIDER, api, headers=app, secret=app_token, transport=transport)
        self._bot = HttpApi(PROVIDER, api, headers=bot, secret=bot_token, transport=transport)
        self._uploads = HttpApi(PROVIDER, "", transport=transport)  # the address Slack gives for a file: no token
        self._socket: ClientConnection | None = None

    async def receive(self) -> AsyncIterator[Incoming]:
        """Raises `ProviderError` when Slack refuses a token; other failures reconnect."""
        failures = 0
        while not self.closed:
            try:
                url = (await self._call(self._app, "apps.connections.open"))["url"]
                async with connect(url, max_size=2**24) as socket:
                    self._socket, failures = socket, 0
                    async for raw in socket:
                        envelope = json.loads(raw)
                        if envelope.get("envelope_id"):
                            await socket.send(json.dumps({"envelope_id": envelope["envelope_id"]}))
                        if envelope.get("type") == "disconnect":
                            break
                        if envelope.get("type") == "events_api":
                            event = (envelope.get("payload") or {}).get("event") or {}
                            if (incoming := self._incoming(event)) is not None:
                                yield incoming
            except (ProviderError, OSError, WebSocketException, ValueError, KeyError) as error:
                if self.closed:
                    return
                await self.retry_later(error, failures)
                failures += 1

    async def disconnect(self) -> None:
        if self._socket is not None:
            await self._socket.close()
        await self._app.aclose()
        await self._bot.aclose()
        await self._uploads.aclose()

    async def deliver(self, conversation: str, answer: Answer) -> None:
        for part in split_text(answer.text, MESSAGE_LIMIT):
            await self._call(self._bot, "chat.postMessage", {"channel": conversation, "text": part})
        for picture in (a for a in answer.attachments if a.kind is AttachmentKind.IMAGE):
            await self._upload(conversation, picture)

    def _incoming(self, event: Mapping[str, Any]) -> Incoming | None:
        kind, subtype = event.get("type"), event.get("subtype")
        if event.get("bot_id") or subtype not in (None, "file_share") or not event.get("user"):
            return None
        direct = event.get("channel_type") == "im"
        if not ((kind == "message" and direct) or (kind == "app_mention" and not direct)):
            return None  # in a channel, the mention event alone: its message event would answer twice
        at = datetime.fromtimestamp(float(event["ts"]), tz=UTC) if event.get("ts") else None
        return Incoming(
            address=Address(self.channel_id, str(event["channel"])),
            sender=Sender(str(event["user"])),
            text=_MENTION.sub("", str(event.get("text") or "")).strip(),
            files=tuple(self._pending(f) for f in event.get("files") or [] if f.get("url_private_download")),
            at=at,
        )

    def _pending(self, file: Mapping[str, Any]) -> Pending:
        media_type = str(file.get("mimetype") or "application/octet-stream")
        kind = kind_of(media_type, voice=file.get("subtype") == "slack_audio")  # a clip recorded in Slack
        url = str(file["url_private_download"])

        async def fetch() -> bytes:
            return (await self._bot.request("GET", url)).content  # private files: the bot's token, on Slack's host

        return Pending(kind=kind, media_type=media_type, fetch=fetch, name=file.get("name"), size=file.get("size"))

    async def _upload(self, channel: str, file: Attachment) -> None:
        """Slack's upload in three steps: an address to send the file to, the file, then the share in the channel."""
        name = file.name or f"image.{file.media_type.rpartition('/')[2]}"
        ticket = await self._call(
            self._bot, "files.getUploadURLExternal", form={"filename": name, "length": str(len(file.data))}
        )
        await self._uploads.request("POST", ticket["upload_url"], content=file.data)
        files = [{"id": ticket["file_id"], "title": name}]
        await self._call(self._bot, "files.completeUploadExternal", {"files": files, "channel_id": channel})

    async def _call(
        self, api: HttpApi, method: str, body: Mapping[str, Any] | None = None, *, form: Mapping[str, str] | None = None
    ) -> Mapping[str, Any]:
        """A Web API method: Slack answers 200 with `ok: false` and the reason when it refuses."""
        if form is not None:
            response = await api.request("POST", f"/{method}", data=dict(form))
        else:
            response = await api.request("POST", f"/{method}", json=dict(body or {}))
        found = response.json()
        if not found.get("ok"):
            reason = str(found.get("error", "refused"))
            transient = reason in ("ratelimited", "internal_error", "service_unavailable", "request_timeout")
            raise api.error(f"{method}: {reason}", transient=transient)
        return found
