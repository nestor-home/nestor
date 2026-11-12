"""Telegram channel: a bot reached through the Bot HTTP API with long polling.

Text, photos, voice messages, audio files and documents reach the assistant (with their caption); a voice message is
answered with one when the assistant has a voice. Limits: the Bot API serves files up to 20 MB, larger ones are left
out; stickers, videos and locations are ignored; updates are acknowledged in memory, so the last batch received before
a stop is delivered again at the next start.
"""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from nestor.core import Component, ContractError, ProviderError
from nestor.core.i18n import Message
from nestor.modules.channels import (
    IMAGE_TYPES,
    Address,
    Answer,
    Assistant,
    Attachment,
    AttachmentKind,
    Channel,
    InboundMessage,
    Medium,
    Sender,
)
from nestor.runtime.plugins import ChannelSettings, Family, Plugin, RequiredSecret, Services

logger = logging.getLogger(__name__)

PROVIDER = "telegram"
MESSAGE_LIMIT = 4096  # Telegram's limit, in UTF-16 code units
CAPTION_LIMIT = 1024  # a file's caption
FILE_LIMIT = 20 * 1024 * 1024  # what the Bot API lets a bot download
_TOKEN_IN_URL = re.compile(r"/bot[^/\s]+/")


class _RedactBotToken(logging.Filter):
    """httpx logs every request URL at info level, and the Bot API puts the token in the path."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = _TOKEN_IN_URL.sub("/bot<redacted>/", record.getMessage()), None
        return True


logging.getLogger("httpx").addFilter(_RedactBotToken())


class TelegramError(ProviderError):
    """A failed Bot API call; `retry_after_s` is set when Telegram asks to slow down."""

    def __init__(self, message: str, *, transient: bool, retry_after_s: float | None = None) -> None:
        super().__init__(PROVIDER, message, transient=transient)
        self.retry_after_s = retry_after_s


class _Chat(BaseModel):
    id: int


class _User(BaseModel):
    id: int
    first_name: str | None = None


class _File(BaseModel):
    """A file of a message (a photo size, a voice message, an audio file, a document), downloaded by `file_id`."""

    file_id: str
    file_size: int | None = None
    mime_type: str | None = None
    file_name: str | None = None


class _Message(BaseModel):
    chat: _Chat
    sender: _User | None = Field(default=None, alias="from")
    date: int
    text: str | None = None
    caption: str | None = None
    photo: list[_File] = []  # the same picture in several sizes, the largest last
    voice: _File | None = None
    audio: _File | None = None
    document: _File | None = None

    @property
    def has_files(self) -> bool:
        return bool(self.photo or self.voice or self.audio or self.document)

    def files(self) -> list[tuple[AttachmentKind, _File, str]]:
        """Its files, each with its kind and media type: the largest size of a photo, a document that is an image
        as an image."""
        found: list[tuple[AttachmentKind, _File, str]] = []
        if self.photo:
            found.append((AttachmentKind.IMAGE, self.photo[-1], "image/jpeg"))
        if self.voice:
            found.append((AttachmentKind.VOICE, self.voice, self.voice.mime_type or "audio/ogg"))
        if self.audio:
            found.append((AttachmentKind.AUDIO, self.audio, self.audio.mime_type or "audio/mpeg"))
        if self.document:
            media_type = self.document.mime_type or "application/octet-stream"
            kind = AttachmentKind.IMAGE if media_type in IMAGE_TYPES else AttachmentKind.FILE
            found.append((kind, self.document, media_type))
        return found


class _Update(BaseModel):
    update_id: int
    message: _Message | None = None


_UPDATES = TypeAdapter(list[_Update])


class _ResponseParameters(BaseModel):
    retry_after: float | None = None


class _Envelope(BaseModel):
    ok: bool
    result: Any = None
    error_code: int | None = None
    description: str = ""
    parameters: _ResponseParameters | None = None


class BotApi:
    """A thin client of the Telegram Bot HTTP API that turns every failure into a `TelegramError`."""

    def __init__(
        self,
        token: str,
        *,
        api_base: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._client = httpx.AsyncClient(base_url=api_base, timeout=timeout_s, transport=transport)

    async def call(self, method: str, payload: dict[str, object], *, timeout_s: float | None = None) -> Any:
        timeout = httpx.USE_CLIENT_DEFAULT if timeout_s is None else timeout_s
        return self._result(method, await self._post(method, json=payload, timeout=timeout))

    async def upload(self, method: str, fields: dict[str, str], name: str, file: Attachment) -> Any:
        """`method` with `file` sent as its `name` field, the other fields beside it."""
        upload = {name: (file.name or name, file.data, file.media_type)}
        return self._result(method, await self._post(method, data=fields, files=upload))

    async def download(self, file_id: str) -> bytes:
        """A file of a message, by its id."""
        found = await self.call("getFile", {"file_id": file_id})
        path = found.get("file_path") if isinstance(found, dict) else None
        if not isinstance(path, str):
            raise TelegramError("getFile: no file path", transient=False)
        response = await self._request("download", "GET", f"/file/bot{self._token}/{path}")
        if response.is_error:
            raise TelegramError(f"download: HTTP {response.status_code}", transient=_transient(response.status_code))
        return response.content

    async def _post(self, method: str, **request: Any) -> httpx.Response:
        return await self._request(method, "POST", f"/bot{self._token}/{method}", **request)

    async def _request(self, what: str, verb: str, path: str, **request: Any) -> httpx.Response:
        try:
            return await self._client.request(verb, path, **request)
        except httpx.HTTPError as error:
            detail = f"{type(error).__name__} {error}".replace(self._token, "<redacted>")
            raise TelegramError(f"{what}: {detail.strip()}", transient=True) from None

    def _result(self, method: str, response: httpx.Response) -> Any:
        try:
            envelope = _Envelope.model_validate_json(response.content)
        except ValidationError:
            raise TelegramError(
                f"{method}: HTTP {response.status_code}", transient=_transient(response.status_code)
            ) from None
        if envelope.ok:
            return envelope.result
        code = envelope.error_code or response.status_code
        retry_after = envelope.parameters.retry_after if envelope.parameters else None
        raise TelegramError(
            f"{method}: {code} {envelope.description}".strip(), transient=_transient(code), retry_after_s=retry_after
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _transient(status: int) -> bool:
    """Rate limits, server errors and a conflict (another instance polling with the same token, which
    ends with it) may pass; a bad token (401), a blocked bot (403) or a bad request won't."""
    return status in (409, 429) or status >= 500


def split_text(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Cut `text` into messages of at most `limit` UTF-16 units, preferring paragraph, then line, then
    sentence, then word boundaries; a word longer than `limit` is cut where it must be."""
    parts = []
    rest = text.strip()
    while _utf16_length(rest) > limit:
        window = _longest_prefix(rest, limit)
        cut = _boundary(window)
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


_BOUNDARIES = (re.compile(r"\n\s*\n"), re.compile(r"\n"), re.compile(r"[.!?…]\s"), re.compile(r"\s"))


def _boundary(window: str) -> int:
    """Where to cut a window that is too long: the last boundary of the coarsest kind found in its
    second half (a cut earlier than that would leave many short messages)."""
    for pattern in _BOUNDARIES:
        ends = [match.end() for match in pattern.finditer(window) if match.start() >= len(window) // 2]
        if ends:
            return ends[-1]
    return len(window)


def _longest_prefix(text: str, limit: int) -> str:
    window = text[:limit]
    while (excess := _utf16_length(window) - limit) > 0:
        window = window[: -max(1, excess // 2)]  # a character is one or two units: never cuts too much
    return window


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True, slots=True)
class _Incoming:
    """A household member's message, its files not downloaded yet."""

    address: Address
    sender: Sender
    message: _Message


class _ChatQueues:
    """Answers the messages of one chat in order, and different chats concurrently."""

    def __init__(self, answer: Callable[[_Incoming], Awaitable[None]]) -> None:
        self._answer = answer
        self._queues: dict[Address, asyncio.Queue[_Incoming]] = {}
        self._workers: set[asyncio.Task[None]] = set()

    def submit(self, message: _Incoming) -> None:
        queue = self._queues.get(message.address)
        if queue is None:
            queue = self._queues[message.address] = asyncio.Queue()
            self._workers.add(asyncio.create_task(self._work(queue)))
        queue.put_nowait(message)

    async def _work(self, queue: asyncio.Queue[_Incoming]) -> None:
        while True:
            message = await queue.get()
            try:
                await self._answer(message)
            except Exception:
                logger.exception("telegram: could not answer in %s", message.address)

    async def aclose(self) -> None:
        workers, self._workers, self._queues = self._workers, set(), {}
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.wait(workers)


class TelegramChannel(Channel):
    """A Telegram bot: household members write to it, strangers are ignored.

    `serve` long-polls `getUpdates`; each message of an answer is sent as soon as it is written ("Je
    regarde." before the tools run, the result after), as plain text (no Markdown parsing, so a stray
    `*` cannot make Telegram reject them), split under the message limit. When the assistant fails,
    the user receives `apology` rather than a typing indicator followed by silence; an empty
    `apology` keeps the bot silent; so does a message whose files could not be downloaded.

    The files of a message are downloaded before it reaches the assistant; an answer to a voice message goes back as
    voice messages, each with its text as caption when it fits, or written when the assistant gives no voice.
    """

    name = "telegram"
    brand = "telegram"
    sends = frozenset({AttachmentKind.VOICE, AttachmentKind.IMAGE})

    def __init__(
        self,
        channel_id: str,
        *,
        token: str,
        api_base: str = "https://api.telegram.org",
        poll_timeout_s: int = 30,
        request_timeout_s: float = 10.0,
        typing_interval_s: float = 4.0,
        retry_delay_s: float = 1.0,
        max_retry_delay_s: float = 60.0,
        apology: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        conversation_ends_after_s: float | None = None,
    ) -> None:
        super().__init__(channel_id, conversation_ends_after_s=conversation_ends_after_s)
        self._api = BotApi(token, api_base=api_base, timeout_s=request_timeout_s, transport=transport)
        self._poll_timeout_s = poll_timeout_s
        self._request_timeout_s = request_timeout_s
        self._typing_interval_s = typing_interval_s
        self._retry_delay_s = retry_delay_s
        self._max_retry_delay_s = max_retry_delay_s
        self._apology = apology
        self._closing = asyncio.Event()
        self._chats: _ChatQueues | None = None

    async def serve(self, assistant: Assistant) -> None:
        """Answer messages until the channel is closed; raises `ProviderError` on a fatal API error
        (bad token) — network failures and a conflicting instance polling are retried."""
        chats = self._chats = _ChatQueues(lambda incoming: self._answer(assistant, incoming))
        offset: int | None = None
        try:
            while (updates := await self._next_updates(offset)) is not None:
                for update in updates:
                    offset = update.update_id + 1
                    if update.message is not None:
                        self._dispatch(assistant, update.message, chats)
        finally:
            await chats.aclose()

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...] = ()) -> None:
        if to.channel != self.channel_id or medium not in self.media:
            raise ContractError(f"{to} is not on channel {self.channel_id!r} {medium}")
        if self._closing.is_set():
            raise ProviderError(PROVIDER, "the channel is closed", transient=False)
        await self._send_answer(to.conversation, Answer(text, attachments))

    async def close(self) -> None:
        if self._closing.is_set():
            return
        self._closing.set()
        if self._chats is not None:
            await self._chats.aclose()
        await self._api.aclose()

    async def _next_updates(self, offset: int | None) -> list[_Update] | None:
        """The next batch of updates, retrying transient failures with backoff; `None` once closed."""
        failures = 0
        payload: dict[str, object] = {"timeout": self._poll_timeout_s, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        while not self._closing.is_set():
            poll = self._api.call("getUpdates", payload, timeout_s=self._poll_timeout_s + self._request_timeout_s)
            try:
                result = await self._unless_closed(poll)
            except TelegramError as error:
                if not error.transient:
                    raise
                delay = error.retry_after_s or min(self._retry_delay_s * 2**failures, self._max_retry_delay_s)
                failures += 1
                logger.warning("telegram: polling failed (%s), retrying in %.1f s", error, delay)
                await self._unless_closed(asyncio.sleep(delay))
                continue
            if self._closing.is_set():
                break
            try:
                return _UPDATES.validate_python(result)
            except ValidationError:
                raise TelegramError("getUpdates: unexpected result", transient=False) from None
        return None

    def _dispatch(self, assistant: Assistant, message: _Message, chats: _ChatQueues) -> None:
        address = Address(self.channel_id, str(message.chat.id))
        if message.sender is None or not (message.text or message.caption or message.has_files):
            logger.debug("telegram: skipping a message without text, file or author in %s", address)
            return
        sender = Sender(str(message.sender.id), message.sender.first_name)
        if assistant.identify(address, sender) is None:
            logger.info("telegram: ignoring a message from unknown user %s in %s", sender.id, address)
            return
        chats.submit(_Incoming(address, sender, message))

    async def _answer(self, assistant: Assistant, incoming: _Incoming) -> None:
        chat_id = int(incoming.address.conversation)
        message = await self._inbound(incoming)
        if message is None:
            if self._apology:
                await self._send_text(chat_id, self._apology)
            return
        answers = self._answers(assistant, message)
        while (answer := await self._next(answers, chat_id, message.address)) is not None:
            await self._send_answer(chat_id, answer)

    async def _inbound(self, incoming: _Incoming) -> InboundMessage | None:
        """The message with its files downloaded; `None` when none could be and it has no text."""
        message = incoming.message
        attachments = [a for f in message.files() if (a := await self._download(*f, incoming.address))]
        text = message.text or message.caption or ""
        if not (text or attachments):
            return None
        at = datetime.fromtimestamp(message.date, tz=UTC)
        return InboundMessage(
            address=incoming.address, sender=incoming.sender, text=text, attachments=tuple(attachments), at=at
        )

    async def _download(
        self, kind: AttachmentKind, file: _File, media_type: str, address: Address
    ) -> Attachment | None:
        if file.file_size is not None and file.file_size > FILE_LIMIT:
            logger.warning(
                "telegram: a %s of %d bytes in %s is over the Bot API's limit", kind, file.file_size, address
            )
            return None
        try:
            data = await self._api.download(file.file_id)
        except TelegramError as error:
            logger.warning("telegram: could not download a %s in %s: %s", kind, address, error)
            return None
        return Attachment(kind=kind, data=data, media_type=media_type, name=file.file_name)

    async def _send_answer(self, chat_id: int | str, answer: Answer) -> None:
        """A message as a voice message when it has its recording, written otherwise, then its pictures; a single
        picture takes the text as caption when it fits and nothing is said aloud."""
        pictures = [a for a in answer.attachments if a.kind is AttachmentKind.IMAGE]
        if answer.voice is not None:
            await self._send_voice(chat_id, answer.text, answer.voice)
        elif len(pictures) == 1 and _utf16_length(answer.text) <= CAPTION_LIMIT:
            await self._api.upload("sendPhoto", {"chat_id": str(chat_id), "caption": answer.text}, "photo", pictures[0])
            return
        else:
            await self._send_text(chat_id, answer.text)
        for picture in pictures:
            await self._api.upload("sendPhoto", {"chat_id": str(chat_id)}, "photo", picture)

    async def _send_voice(self, chat_id: int | str, text: str, voice: Attachment) -> None:
        """A voice message, with its text as caption when it fits, or written after it."""
        fits = _utf16_length(text) <= CAPTION_LIMIT
        fields = {"chat_id": str(chat_id), "caption": text} if fits else {"chat_id": str(chat_id)}
        await self._api.upload("sendVoice", fields, "voice", voice)
        if not fits:
            await self._send_text(chat_id, text)

    async def _answers(self, assistant: Assistant, message: InboundMessage) -> AsyncIterator[Answer]:
        async for answer in assistant.respond(message).answers():  # asks on the first read: a failure is caught there
            yield answer

    async def _next(self, answers: AsyncIterator[Answer], chat_id: int, address: Address) -> Answer | None:
        """The next message of an answer, with "typing…" shown meanwhile (sending one clears it);
        the apology when the assistant fails, then `None`."""
        async with self._typing(chat_id):
            try:
                return await anext(answers, None)
            except Exception:
                logger.exception("telegram: the assistant failed to answer in %s", address)
                return Answer(self._apology)

    async def _send_text(self, chat_id: int | str, text: str) -> None:
        for part in split_text(text):
            await self._api.call("sendMessage", {"chat_id": chat_id, "text": part})

    @asynccontextmanager
    async def _typing(self, chat_id: int) -> AsyncGenerator[None]:
        """Show "typing…" in the chat while the body runs (Telegram clears it after about 5 s)."""
        typing = asyncio.create_task(self._keep_typing(chat_id))
        try:
            yield
        finally:
            typing.cancel()
            await asyncio.wait({typing})

    async def _keep_typing(self, chat_id: int) -> None:
        while True:
            try:
                await self._api.call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
            except TelegramError as error:
                logger.debug("telegram: typing indicator failed in chat %s: %s", chat_id, error)
            await asyncio.sleep(self._typing_interval_s)

    async def _unless_closed[T](self, work: Awaitable[T]) -> T | None:
        """`work`'s result, or `None` when the channel is closed first (`work` is then cancelled)."""
        task = asyncio.ensure_future(work)
        closing = asyncio.ensure_future(self._closing.wait())
        try:
            await asyncio.wait({task, closing}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            closing.cancel()
            task.cancel()
        return task.result() if task.done() else None


class TelegramSettings(ChannelSettings):
    token: RequiredSecret
    api_base: str = "https://api.telegram.org"
    poll_timeout_s: int = Field(default=30, ge=1, le=50)
    request_timeout_s: float = Field(default=10.0, gt=0)
    apology: str | None = None  # what the bot says when an answer fails; default: `telegram-apology`, "" for silence


def build(settings: TelegramSettings, name: str, services: Services) -> Component:
    return TelegramChannel(
        name,
        token=settings.token.get_secret_value(),
        api_base=settings.api_base,
        poll_timeout_s=settings.poll_timeout_s,
        request_timeout_s=settings.request_timeout_s,
        apology=settings.apology
        if settings.apology is not None
        else services.localizer.format(Message.of("telegram-apology"), services.locale),
        conversation_ends_after_s=settings.conversation_ends_after_s,
    )


plugin = Plugin(Family.CHANNEL, "telegram", TelegramSettings, build)
