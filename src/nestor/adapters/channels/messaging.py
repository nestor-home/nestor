"""What every messaging channel does the same way, whatever its platform: a member's messages answered in order, one
conversation at a time and conversations at once; their files downloaded before the assistant reads them; each
message of an answer sent as soon as it is written, with "typing…" shown meanwhile; an excuse when the assistant
fails, or when nothing of a message could be fetched.

A platform says how messages arrive (`receive`), how an answer goes out (`deliver`) and how it shows that the
assistant is writing (`typing`). Telegram, Discord, Slack, Matrix and Signal are such platforms.
"""

import asyncio
import contextlib
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import Field

from nestor.core import ContractError, ProviderError, utc_now
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
from nestor.runtime.plugins import ChannelSettings, Services

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class Pending:
    """A file of a message, not downloaded yet: `fetch` downloads it. `size` is what the platform says it weighs,
    when it says it."""

    kind: AttachmentKind
    media_type: str
    fetch: Callable[[], Awaitable[bytes]]
    name: str | None = None
    size: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Incoming:
    """A message as the platform delivers it, its files not downloaded yet."""

    address: Address
    sender: Sender
    text: str = ""
    files: tuple[Pending, ...] = ()
    at: datetime | None = None


def kind_of(media_type: str, *, voice: bool = False) -> AttachmentKind:
    """What a received file is, from its type: a picture, an audio file, or another file; `voice`, a voice message
    as the platform marks it."""
    if voice:
        return AttachmentKind.VOICE
    base = media_type.split(";")[0].strip().lower()
    if base in IMAGE_TYPES:
        return AttachmentKind.IMAGE
    return AttachmentKind.AUDIO if base.startswith("audio/") else AttachmentKind.FILE


class MessagingSettings(ChannelSettings):
    """What every messaging channel lets a household set."""

    apology: str | None = None  # what the bot says when an answer fails; default: `channel-apology`, "" for silence
    retry_delay_s: float = Field(default=1.0, gt=0, json_schema_extra={"advanced": True})  # doubled at each failure

    def common(self, services: Services) -> dict[str, Any]:
        """The arguments every `MessagingChannel` takes, from these settings."""
        apology = self.apology
        if apology is None:
            apology = services.localizer.format(Message.of("channel-apology"), services.locale)
        return {
            "apology": apology,
            "retry_delay_s": self.retry_delay_s,
            "conversation_ends_after_s": self.conversation_ends_after_s,
        }


class MessagingChannel(Channel, ABC):
    """A messaging platform's bot: household members write to it, strangers are ignored.

    Contract for a platform: `receive` yields the messages it gets until the channel is `closed`, and raises
    `ProviderError` on a failure it cannot get past (a bad token), waiting with `retry_later` before trying again
    otherwise; `deliver` sends a message of an answer, with the attachments of the kinds it `sends`, raising
    `ProviderError` when it cannot; `disconnect` releases the platform's connections.
    """

    file_limit: int | None = None  # the largest file the platform lets a bot download, in bytes
    typing_every_s: float | None = None  # how often `show_typing` must be said again; `None`: the platform shows none

    def __init__(
        self,
        channel_id: str,
        *,
        apology: str = "",
        retry_delay_s: float = 1.0,
        max_retry_delay_s: float = 60.0,
        conversation_ends_after_s: float | None = None,
    ) -> None:
        """`apology`: what is written when the assistant fails; empty, nothing is. `retry_delay_s`: the first wait
        after a failure to reach the platform, doubled each time up to `max_retry_delay_s`."""
        super().__init__(channel_id, conversation_ends_after_s=conversation_ends_after_s)
        self._apology = apology
        self._retry_delay_s, self._max_retry_delay_s = retry_delay_s, max_retry_delay_s
        self._closing = asyncio.Event()
        self._conversations: _Conversations | None = None

    @property
    def closed(self) -> bool:
        return self._closing.is_set()

    @abstractmethod
    def receive(self) -> AsyncIterator[Incoming]: ...

    @abstractmethod
    async def deliver(self, conversation: str, answer: Answer) -> None: ...

    async def show_typing(self, conversation: str) -> None:
        """Shows once that the assistant is writing, for about `typing_every_s`."""

    async def hide_typing(self, conversation: str) -> None:
        """Stops showing it, where the platform does not stop by itself."""

    async def disconnect(self) -> None:
        """Releases the platform's connections, once the channel is closed."""

    async def serve(self, assistant: Assistant) -> None:
        conversations = self._conversations = _Conversations(lambda incoming: self._answer(assistant, incoming))
        try:
            async for incoming in self.receive():
                if not (incoming.text or incoming.files):
                    continue
                if assistant.identify(incoming.address, incoming.sender) is None:
                    logger.info("%s: ignoring a message from unknown user %s", self.brand, incoming.sender.id)
                    continue
                conversations.submit(incoming)
        finally:
            await conversations.aclose()

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...]) -> None:
        if to.channel != self.channel_id or medium not in self.media:
            raise ContractError(f"{to} is not on channel {self.channel_id!r} {medium}")
        if self.closed:
            raise ProviderError(self.brand or self.name, "the channel is closed", transient=False)
        await self.deliver(to.conversation, Answer(text, attachments))

    async def close(self) -> None:
        if self.closed:
            return
        self._closing.set()
        if self._conversations is not None:
            await self._conversations.aclose()
        await self.disconnect()

    async def retry_later(self, error: Exception, failures: int, *, after_s: float | None = None) -> None:
        """After the `failures`-th failure in a row to reach the platform: raises `error` when nothing will get past
        it (a `ProviderError` that is not transient), otherwise waits (`after_s` when the platform says how long),
        or less when the channel closes meanwhile."""
        if isinstance(error, ProviderError) and not error.transient:
            raise error
        delay = after_s or min(self._retry_delay_s * 2**failures, self._max_retry_delay_s)
        logger.warning("%s: %s, retrying in %.1f s", self.brand, error, delay)
        await self.unless_closed(asyncio.sleep(delay))

    async def unless_closed[T](self, work: Awaitable[T]) -> T | None:
        """`work`'s result, or `None` when the channel is closed first (`work` is then cancelled)."""
        task = asyncio.ensure_future(work)
        closing = asyncio.ensure_future(self._closing.wait())
        try:
            await asyncio.wait({task, closing}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            closing.cancel()
            task.cancel()
        return task.result() if task.done() and not task.cancelled() else None

    async def _answer(self, assistant: Assistant, incoming: Incoming) -> None:
        conversation = incoming.address.conversation
        async with self._typing(conversation):
            message = await self._inbound(incoming)
            if message is None:
                if self._apology:
                    await self.deliver(conversation, Answer(self._apology))
                return
            answers = _answers(assistant, message)
            while True:
                try:
                    answer = await anext(answers, None)
                except Exception:
                    logger.exception("%s: the assistant failed to answer in %s", self.brand, incoming.address)
                    answer = Answer(self._apology) if self._apology else None
                    if answer is not None:
                        await self.deliver(conversation, answer)
                    return
                if answer is None:
                    return
                await self.deliver(conversation, answer)

    @contextlib.asynccontextmanager
    async def _typing(self, conversation: str) -> AsyncGenerator[None]:
        """ "typing…" said again every `typing_every_s` while the body runs, where the platform shows it."""
        every = self.typing_every_s
        if every is None:
            yield
            return

        async def keep() -> None:
            while True:
                try:
                    await self.show_typing(conversation)
                except ProviderError as error:
                    logger.debug("%s: typing indicator failed in %s: %s", self.brand, conversation, error)
                await asyncio.sleep(every)

        task = asyncio.create_task(keep())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.wait({task})
            with contextlib.suppress(ProviderError):
                await self.hide_typing(conversation)

    async def _inbound(self, incoming: Incoming) -> InboundMessage | None:
        """The message with its files downloaded, all at once; `None` when none could be and it has no text."""
        found = await asyncio.gather(*(self._download(f, incoming.address) for f in incoming.files))
        attachments = tuple(a for a in found if a is not None)
        if not (incoming.text or attachments):
            return None
        return InboundMessage(
            address=incoming.address,
            sender=incoming.sender,
            text=incoming.text,
            attachments=attachments,
            at=incoming.at or utc_now(),
        )

    async def _download(self, file: Pending, address: Address) -> Attachment | None:
        if self.file_limit is not None and file.size is not None and file.size > self.file_limit:
            logger.warning("%s: a %s of %d bytes in %s is over the limit", self.brand, file.kind, file.size, address)
            return None
        try:
            data = await file.fetch()
        except ProviderError as error:
            logger.warning("%s: could not download a %s in %s: %s", self.brand, file.kind, address, error)
            return None
        return Attachment(kind=file.kind, data=data, media_type=file.media_type, name=file.name)


async def _answers(assistant: Assistant, message: InboundMessage) -> AsyncIterator[Answer]:
    """The messages of the answer; asks on the first read, so that a failure to answer is caught there."""
    async for answer in assistant.respond(message).answers():
        yield answer


def split_text(text: str, limit: int, *, measure: Callable[[str], int] = len) -> list[str]:
    """Cut `text` into messages of at most `limit`, as `measure` counts (characters, UTF-16 units), preferring
    paragraph, then line, then sentence, then word boundaries; a word longer than `limit` is cut where it must be."""
    parts = []
    rest = text.strip()
    while measure(rest) > limit:
        window = _longest_prefix(rest, limit, measure)
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


def _longest_prefix(text: str, limit: int, measure: Callable[[str], int]) -> str:
    window = text[:limit]
    while (excess := measure(window) - limit) > 0:
        window = window[: -max(1, excess // 2)]  # a character is one or two units: never cuts too much
    return window


def utf16_length(text: str) -> int:
    """How Telegram and others count a text's length."""
    return len(text.encode("utf-16-le")) // 2


class _Conversations:
    """Answers the messages of one conversation in order, and different conversations concurrently."""

    def __init__(self, answer: Callable[[Incoming], Awaitable[None]]) -> None:
        self._answer = answer
        self._queues: dict[Address, asyncio.Queue[Incoming]] = {}
        self._workers: set[asyncio.Task[None]] = set()

    def submit(self, message: Incoming) -> None:
        queue = self._queues.get(message.address)
        if queue is None:
            queue = self._queues[message.address] = asyncio.Queue()
            self._workers.add(asyncio.create_task(self._work(queue)))
        queue.put_nowait(message)

    async def _work(self, queue: asyncio.Queue[Incoming]) -> None:
        while True:
            message = await queue.get()
            try:
                await self._answer(message)
            except Exception:
                logger.exception("could not answer in %s", message.address)

    async def aclose(self) -> None:
        workers, self._workers, self._queues = self._workers, set(), {}
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.wait(workers)
