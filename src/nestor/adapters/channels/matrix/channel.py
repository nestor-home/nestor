"""The Matrix channel: a bot account on a homeserver, through `/sync` long polling, a `MessagingChannel`."""

import json
import logging
import urllib.parse
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from nestor.adapters.channels.messaging import Incoming, MessagingChannel, Pending, kind_of
from nestor.adapters.common.http import HttpApi
from nestor.core import ProviderError, new_id
from nestor.modules.channels import Address, Answer, Attachment, AttachmentKind, Sender

logger = logging.getLogger(__name__)

PROVIDER = "matrix"
CLIENT = "/_matrix/client/v3"
VOICE = "org.matrix.msc3245.voice"  # what marks an audio message as a voice message (MSC3245)
FILES = frozenset({"m.image", "m.audio", "m.file", "m.video"})
SENT = {AttachmentKind.IMAGE: "m.image", AttachmentKind.VOICE: "m.audio"}
# what `/sync` brings: the rooms' messages and invitations, nothing else (presence, receipts, state)
FILTER = json.dumps(
    {
        "presence": {"types": []},
        "account_data": {"types": []},
        "room": {
            "timeline": {"types": ["m.room.message"], "limit": 50},
            "state": {"types": []},
            "ephemeral": {"types": []},
            "account_data": {"types": []},
        },
    }
)


class MatrixChannel(MessagingChannel):
    name = "matrix"
    brand = "matrix"
    sends = frozenset({AttachmentKind.VOICE, AttachmentKind.IMAGE})

    typing_every_s = 20.0  # each lasts 30 s

    def __init__(
        self,
        channel_id: str,
        *,
        homeserver: str,
        token: str,
        poll_timeout_s: int = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        **common: Any,
    ) -> None:
        """`common`: what every `MessagingChannel` takes (`apology`, `retry_delay_s`…)."""
        super().__init__(channel_id, **common)
        headers = {"Authorization": f"Bearer {token}"}
        timeout_s = poll_timeout_s + 10.0
        self._api = HttpApi(
            PROVIDER, homeserver.rstrip("/"), headers=headers, secret=token, timeout_s=timeout_s, transport=transport
        )
        self._poll_timeout_s = poll_timeout_s
        self._me: str | None = None

    async def receive(self) -> AsyncIterator[Incoming]:
        """Raises `ProviderError` when the token is refused; other failures are retried with backoff."""
        self._me = (await self._json("GET", f"{CLIENT}/account/whoami"))["user_id"]
        first = await self._sync(None, timeout_ms=0)  # what was said before the start is skipped, not invitations
        since = first["next_batch"]
        for room in first.get("rooms", {}).get("invite", {}):
            await self._join(room)
        while not self.closed:
            found = await self.unless_closed(self._sync(since, timeout_ms=self._poll_timeout_s * 1000))
            if found is None:
                return
            since = found["next_batch"]
            rooms = found.get("rooms", {})
            for room in rooms.get("invite", {}):
                await self._join(room)
            for room, joined in rooms.get("join", {}).items():
                for event in joined.get("timeline", {}).get("events", []):
                    if (incoming := self._incoming(room, event)) is not None:
                        yield incoming

    async def disconnect(self) -> None:
        await self._api.aclose()

    async def deliver(self, conversation: str, answer: Answer) -> None:
        """The recording when it has one (its text as the message's caption, as Matrix clients show it), written
        otherwise; then its pictures."""
        pictures = [a for a in answer.attachments if a.kind is AttachmentKind.IMAGE]
        voice = answer.voice
        if voice is not None:
            await self._send_file(conversation, voice, caption=answer.text)
        else:
            await self._send(conversation, {"msgtype": "m.text", "body": answer.text})
        for picture in pictures:
            await self._send_file(conversation, picture)

    async def show_typing(self, conversation: str) -> None:
        await self._set_typing(conversation, {"typing": True, "timeout": 30000})

    async def hide_typing(self, conversation: str) -> None:
        await self._set_typing(conversation, {"typing": False})

    def _incoming(self, room: str, event: Mapping[str, Any]) -> Incoming | None:
        content = event.get("content") or {}
        if event.get("type") != "m.room.message" or event.get("sender") == self._me:
            return None
        msgtype, body = content.get("msgtype"), str(content.get("body") or "")
        at = datetime.fromtimestamp(event["origin_server_ts"] / 1000, tz=UTC) if "origin_server_ts" in event else None
        address, sender = Address(self.channel_id, room), Sender(str(event["sender"]))
        if msgtype in ("m.text", "m.notice", "m.emote"):
            return Incoming(address=address, sender=sender, text=body, at=at)
        if msgtype not in FILES or not isinstance(content.get("url"), str):
            return None
        info = content.get("info") or {}
        media_type = str(info.get("mimetype") or "application/octet-stream")
        kind = kind_of(media_type, voice=msgtype == "m.audio" and VOICE in content)
        url, name = content["url"], content.get("filename") or body or None
        size = info.get("size")
        pending = Pending(kind=kind, media_type=media_type, fetch=lambda: self._media(url), name=name, size=size)
        caption = body if content.get("filename") else ""  # with a file name apart, the body is a caption
        return Incoming(address=address, sender=sender, text=caption, files=(pending,), at=at)

    async def _sync(self, since: str | None, *, timeout_ms: int) -> Mapping[str, Any]:
        """The next batch; failures are retried until the channel closes."""
        failures = 0
        params = {"timeout": str(timeout_ms), "filter": FILTER} | ({"since": since} if since else {})
        while True:
            try:
                return await self._json("GET", f"{CLIENT}/sync", params=params)
            except ProviderError as error:
                await self.retry_later(error, failures)
                failures += 1

    async def _join(self, room: str) -> None:
        try:
            await self._json("POST", f"{CLIENT}/join/{_quoted(room)}", json={})
        except ProviderError as error:
            logger.warning("matrix: could not join %s: %s", room, error)

    async def _send(self, room: str, content: Mapping[str, Any]) -> None:
        await self._json("PUT", f"{CLIENT}/rooms/{_quoted(room)}/send/m.room.message/{new_id()}", json=content)

    async def _send_file(self, room: str, file: Attachment, *, caption: str | None = None) -> None:
        name = file.name or ("voice.ogg" if file.kind is AttachmentKind.VOICE else "image")
        uploaded = await self._json(
            "POST",
            "/_matrix/media/v3/upload",
            params={"filename": name},
            content=file.data,
            headers={"Content-Type": file.media_type},
        )
        content: dict[str, Any] = {
            "msgtype": SENT[file.kind],
            "body": caption or name,
            "url": uploaded["content_uri"],
            "info": {"mimetype": file.media_type, "size": len(file.data)},
        }
        if caption:
            content["filename"] = name
        if file.kind is AttachmentKind.VOICE:
            content |= {VOICE: {}, "org.matrix.msc1767.audio": {}}
        await self._send(room, content)

    async def _media(self, url: str) -> bytes:
        server, _, media = url.removeprefix("mxc://").partition("/")
        return (await self._api.request("GET", f"/_matrix/client/v1/media/download/{server}/{media}")).content

    async def _set_typing(self, room: str, body: Mapping[str, Any]) -> None:
        if self._me is not None:
            await self._json("PUT", f"{CLIENT}/rooms/{_quoted(room)}/typing/{_quoted(self._me)}", json=body)

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._api.request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError:
            raise self._api.error(f"{path}: not JSON", transient=True) from None


def _quoted(value: str) -> str:
    return urllib.parse.quote(value, safe="")
