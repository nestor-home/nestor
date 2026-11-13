"""What Meta posts to the webhook: the messages it carries, read as what reaches the assistant."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from nestor.adapters.channels.messaging import Incoming, Pending, kind_of
from nestor.adapters.channels.whatsapp.api import CloudApi
from nestor.modules.channels import Address, Sender

MEDIA = ("image", "audio", "voice", "document", "video", "sticker")


def messages(body: Mapping[str, Any], channel_id: str, api: CloudApi) -> list[tuple[str, Incoming]]:
    """Each message of a post, with its id; its files are fetched from `api` when the assistant reads them."""
    found = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for message in value.get("messages") or []:
                if (received := incoming(message, names, channel_id, api)) is not None:
                    found.append((str(message.get("id", "")), received))
    return found


def incoming(
    message: Mapping[str, Any], names: Mapping[str, str | None], channel_id: str, api: CloudApi
) -> Incoming | None:
    sender, kind = str(message.get("from") or ""), message.get("type")
    if not sender:
        return None
    at = datetime.fromtimestamp(int(message["timestamp"]), tz=UTC) if message.get("timestamp") else None
    address, who = Address(channel_id, sender), Sender(sender, names.get(sender))
    if kind == "text":
        return Incoming(address=address, sender=who, text=str((message.get("text") or {}).get("body") or ""), at=at)
    if kind not in MEDIA or not isinstance(message.get(kind), Mapping):
        return None  # a reaction, a location, a contact card
    media = message[kind]
    media_type = str(media.get("mime_type") or "application/octet-stream")
    voice = kind == "voice" or (kind == "audio" and bool(media.get("voice")))
    media_id = str(media["id"])

    async def fetch() -> bytes:
        return await api.media(media_id)

    pending = Pending(
        kind=kind_of(media_type, voice=voice), media_type=media_type, fetch=fetch, name=media.get("filename")
    )
    return Incoming(address=address, sender=who, text=str(media.get("caption") or ""), files=(pending,), at=at)
