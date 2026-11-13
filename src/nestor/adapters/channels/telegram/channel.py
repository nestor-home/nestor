"""The Telegram channel: a bot polling `getUpdates`, a `MessagingChannel`."""

import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from nestor.adapters.channels.messaging import Incoming, MessagingChannel, Pending, split_text, utf16_length
from nestor.adapters.channels.telegram.api import BotApi, TelegramError
from nestor.adapters.channels.telegram.messages import UPDATES, File, Message, Update, User
from nestor.core import ProviderError
from nestor.modules.channels import Address, Answer, Attachment, AttachmentKind, Sender

logger = logging.getLogger(__name__)

MESSAGE_LIMIT = 4096  # Telegram's limit, in UTF-16 code units
CAPTION_LIMIT = 1024  # a file's caption
FILE_LIMIT = 20 * 1024 * 1024  # what the Bot API lets a bot download


class TelegramChannel(MessagingChannel):
    """A Telegram bot, polling `getUpdates`. Messages go out as plain text (no Markdown parsing, so a stray `*` cannot
    make Telegram reject them), split under the message limit; an answer to a voice message goes back as voice
    messages, each with its text as caption when it fits."""

    name = "telegram"
    brand = "telegram"
    file_limit = FILE_LIMIT
    sends = frozenset({AttachmentKind.VOICE, AttachmentKind.IMAGE})

    typing_every_s = 4.0  # Telegram clears "typing…" after about 5 s

    def __init__(
        self,
        channel_id: str,
        *,
        token: str,
        api_base: str = "https://api.telegram.org",
        poll_timeout_s: int = 30,
        request_timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        **common: Any,
    ) -> None:
        """`common`: what every `MessagingChannel` takes (`apology`, `retry_delay_s`…)."""
        super().__init__(channel_id, **common)
        self._api = BotApi(token, api_base=api_base, timeout_s=request_timeout_s, transport=transport)
        self._poll_timeout_s = poll_timeout_s
        self._request_timeout_s = request_timeout_s

    async def receive(self) -> AsyncIterator[Incoming]:
        """Raises `ProviderError` on a fatal API error (bad token); network failures and a conflicting instance
        polling are retried."""
        offset: int | None = None
        while (updates := await self._next_updates(offset)) is not None:
            for update in updates:
                offset = update.update_id + 1
                if (message := update.message) is not None and message.sender is not None:
                    yield self._incoming(message, message.sender)

    async def disconnect(self) -> None:
        await self._api.aclose()

    def _incoming(self, message: Message, sender: User) -> Incoming:
        def fetch(file: File) -> Callable[[], Awaitable[bytes]]:
            return lambda: self._api.download(file.file_id)

        return Incoming(
            address=Address(self.channel_id, str(message.chat.id)),
            sender=Sender(str(sender.id), sender.first_name),
            text=message.text or message.caption or "",
            files=tuple(
                Pending(kind=kind, media_type=media_type, fetch=fetch(file), name=file.file_name, size=file.file_size)
                for kind, file, media_type in message.files()
            ),
            at=datetime.fromtimestamp(message.date, tz=UTC),
        )

    async def _next_updates(self, offset: int | None) -> list[Update] | None:
        """The next batch of updates, retrying transient failures with backoff; `None` once closed."""
        failures = 0
        payload: dict[str, object] = {"timeout": self._poll_timeout_s, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        while not self.closed:
            poll = self._api.call("getUpdates", payload, timeout_s=self._poll_timeout_s + self._request_timeout_s)
            try:
                result = await self.unless_closed(poll)
            except TelegramError as error:
                await self.retry_later(error, failures, after_s=error.retry_after_s)
                failures += 1
                continue
            if self.closed:
                break
            try:
                return UPDATES.validate_python(result)
            except ValidationError:
                raise TelegramError("getUpdates: unexpected result", transient=False) from None
        return None

    async def deliver(self, conversation: str, answer: Answer) -> None:
        """A message as a voice message when it has its recording, written otherwise, then its pictures; a single
        picture takes the text as caption when it fits and nothing is said aloud."""
        pictures = [a for a in answer.attachments if a.kind is AttachmentKind.IMAGE]
        if answer.voice is not None:
            await self._send_captioned(conversation, answer.text, answer.voice)
        elif len(pictures) == 1:
            await self._send_captioned(conversation, answer.text, pictures[0])
            return
        else:
            await self._send_text(conversation, answer.text)
        for picture in pictures:
            with contextlib.suppress(ProviderError):  # said by `_upload`: the words went out already
                await self._upload(conversation, picture)

    async def _send_captioned(self, chat_id: str, text: str, file: Attachment) -> None:
        """A voice message or a picture with `text` as caption when it fits, or written after it; written alone when
        the file cannot be sent."""
        fits = utf16_length(text) <= CAPTION_LIMIT
        try:
            await self._upload(chat_id, file, caption=text if fits else None)
        except ProviderError:
            fits = False
        if not fits:
            await self._send_text(chat_id, text)

    async def _upload(self, chat_id: str, file: Attachment, *, caption: str | None = None) -> None:
        method, field = ("sendVoice", "voice") if file.kind is AttachmentKind.VOICE else ("sendPhoto", "photo")
        fields = {"chat_id": chat_id} | ({"caption": caption} if caption is not None else {})
        try:
            await self._api.upload(method, fields, field, file)
        except ProviderError as error:
            logger.warning("telegram: a %s could not be sent to %s: %s", file.kind, chat_id, error)
            raise

    async def _send_text(self, chat_id: str, text: str) -> None:
        for part in split_text(text, MESSAGE_LIMIT, measure=utf16_length):
            await self._api.call("sendMessage", {"chat_id": int(chat_id), "text": part})

    async def show_typing(self, conversation: str) -> None:
        await self._api.call("sendChatAction", {"chat_id": int(conversation), "action": "typing"})
