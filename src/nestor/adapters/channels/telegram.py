"""Telegram channel: a bot reached through the Bot HTTP API with long polling (text messages only).

Limits: voice notes, photos and other media are ignored for now; updates are acknowledged in memory,
so the last batch received before a stop is delivered again at the next start.
"""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field, SecretStr, TypeAdapter, ValidationError

from nestor.core import Component, ContractError, ProviderError
from nestor.modules.channels import Address, Assistant, Channel, InboundMessage, Sender
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services

logger = logging.getLogger(__name__)

PROVIDER = "telegram"
MESSAGE_LIMIT = 4096  # Telegram's limit, in UTF-16 code units
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


class _Message(BaseModel):
    chat: _Chat
    sender: _User | None = Field(default=None, alias="from")
    date: int
    text: str | None = None


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
        try:
            response = await self._client.post(f"/bot{self._token}/{method}", json=payload, timeout=timeout)
        except httpx.HTTPError as error:
            detail = f"{type(error).__name__} {error}".replace(self._token, "<redacted>")
            raise TelegramError(f"{method}: {detail.strip()}", transient=True) from None
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
    """Rate limits and server errors may pass; a bad token (401), a blocked bot (403) or a bad request won't."""
    return status == 429 or status >= 500


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


class _ChatQueues:
    """Answers the messages of one chat in order, and different chats concurrently."""

    def __init__(self, answer: Callable[[InboundMessage], Awaitable[None]]) -> None:
        self._answer = answer
        self._queues: dict[Address, asyncio.Queue[InboundMessage]] = {}
        self._workers: set[asyncio.Task[None]] = set()

    def submit(self, message: InboundMessage) -> None:
        queue = self._queues.get(message.address)
        if queue is None:
            queue = self._queues[message.address] = asyncio.Queue()
            self._workers.add(asyncio.create_task(self._work(queue)))
        queue.put_nowait(message)

    async def _work(self, queue: asyncio.Queue[InboundMessage]) -> None:
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

    `serve` long-polls `getUpdates`; answers are sent as plain text (no Markdown parsing, so a stray
    `*` cannot make Telegram reject them), split under the message limit. When the assistant fails,
    the user receives `apology` rather than a typing indicator followed by silence; an empty
    `apology` keeps the bot silent.
    """

    name = "telegram"
    brand = "telegram"

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
        apology: str = "Sorry, something went wrong. Please try again.",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(channel_id)
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
        (bad token, another bot instance polling) — network failures are retried."""
        chats = self._chats = _ChatQueues(lambda message: self._answer(assistant, message))
        offset: int | None = None
        try:
            while (updates := await self._next_updates(offset)) is not None:
                for update in updates:
                    offset = update.update_id + 1
                    if update.message is not None:
                        self._dispatch(assistant, update.message, chats)
        finally:
            await chats.aclose()

    async def send(self, to: Address, text: str) -> None:
        if to.channel != self.channel_id:
            raise ContractError(f"{to} is not on channel {self.channel_id!r}")
        if self._closing.is_set():
            raise ProviderError(PROVIDER, "the channel is closed", transient=False)
        await self._send_text(to.conversation, text)

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
        if message.sender is None or message.text is None:
            logger.debug("telegram: skipping a message without text or author in %s", address)
            return
        sender = Sender(str(message.sender.id), message.sender.first_name)
        if assistant.identify(address, sender) is None:
            logger.info("telegram: ignoring a message from unknown user %s in %s", sender.id, address)
            return
        at = datetime.fromtimestamp(message.date, tz=UTC)
        chats.submit(InboundMessage(address=address, sender=sender, text=message.text, at=at))

    async def _answer(self, assistant: Assistant, message: InboundMessage) -> None:
        chat_id = int(message.address.conversation)
        async with self._typing(chat_id):
            try:
                text = await assistant.respond(message).collect()
            except Exception:
                logger.exception("telegram: the assistant failed to answer in %s", message.address)
                text = self._apology
        await self._send_text(chat_id, text)

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


class TelegramSettings(AdapterSettings):
    token: SecretStr
    api_base: str = "https://api.telegram.org"
    poll_timeout_s: int = Field(default=30, ge=1, le=50)
    request_timeout_s: float = Field(default=10.0, gt=0)
    apology: str = "Sorry, something went wrong. Please try again."


def build(settings: TelegramSettings, name: str, services: Services) -> Component:
    return TelegramChannel(
        name,
        token=settings.token.get_secret_value(),
        api_base=settings.api_base,
        poll_timeout_s=settings.poll_timeout_s,
        request_timeout_s=settings.request_timeout_s,
        apology=settings.apology,
    )


plugin = Plugin(Family.CHANNEL, "telegram", TelegramSettings, build)
