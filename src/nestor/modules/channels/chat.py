"""A chat served by a page (the admin's): people signed in write to the assistant, in as many chats as they like, each
its own session (`<channel>:<person>/<chat>`); the assistant's memory is the same in all of them.

The page hands each message over (`say`) and streams the answer as it is written. The answer goes on when the page is
left, and a page that comes back follows it again (`following`). Chats are read from the journal: what Nestor sends
unprompted (a task's result, in the chat it was asked from) is logged there, which is how `send` delivers it.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.channels.ports import Assistant, Channel, MessageEnd, Reply
from nestor.modules.channels.types import Address, AttachmentKind, InboundMessage, Medium

logger = logging.getLogger(__name__)

CHAT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True, slots=True)
class Written:
    """Words of the message being written."""

    text: str


@dataclass(frozen=True, slots=True)
class Ended:
    """The message is complete; `last`: no other follows in this answer."""

    last: bool


@dataclass(frozen=True, slots=True)
class Failed:
    """The answer broke off: the assistant could not finish it."""


type Part = Written | Ended | Failed


class LiveAnswer:
    """An answer being written in a chat. Every page that follows it gets all its parts from the start, then each
    new one, until it is over."""

    def __init__(self, reply: Reply, over: Callable[["LiveAnswer"], None]) -> None:
        self._reply, self._on_over = reply, over
        self._parts: list[Part] = []
        self._changed = asyncio.Event()
        self._over = False
        self._task = asyncio.create_task(self._run())

    @property
    def over(self) -> bool:
        return self._over

    async def parts(self) -> AsyncIterator[Part]:
        sent = 0
        while True:
            changed = self._changed
            while sent < len(self._parts):
                yield self._parts[sent]
                sent += 1
            if self._over:
                return
            await changed.wait()

    async def stop(self) -> None:
        """Stop writing: what was written so far reached the page, and stays as it is."""
        if not self._over:
            await self._reply.interrupt("".join(p.text for p in self._parts if isinstance(p, Written)))
        await self.close()

    async def close(self) -> None:
        self._task.cancel()
        await asyncio.wait({self._task})

    async def _run(self) -> None:
        try:
            async for part in self._reply:
                self._add(Ended(part.last) if isinstance(part, MessageEnd) else Written(part))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("chat: the assistant failed to answer")
            self._add(Failed())
        finally:
            self._over = True
            self._wake()
            self._on_over(self)

    def _add(self, part: Part) -> None:
        self._parts.append(part)
        self._wake()

    def _wake(self) -> None:
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()


class ChatBusy(ContractError):
    """A message reached a chat whose answer is still being written."""


class ChatChannel(Channel):
    """A chat a page serves (the admin's): the page signs people in, so each message names its person
    (`Sender.person`) and nobody needs an account on it. An answer to a voice message goes back as one; the page plays
    it from the journal. Its conversations are listed by their title."""

    name = "chat"
    sends = frozenset({AttachmentKind.VOICE})
    titled = True

    def __init__(self, channel_id: str, *, conversation_ends_after_s: float | None = None) -> None:
        super().__init__(channel_id, conversation_ends_after_s=conversation_ends_after_s)
        self._assistant: Assistant | None = None
        self._live: dict[Address, LiveAnswer] = {}
        self._closing = asyncio.Event()

    def chat(self, person: PersonId, chat: str) -> Address:
        """The address of one of `person`'s chats."""
        if not CHAT_ID.fullmatch(chat):
            raise ContractError(f"invalid chat id {chat!r}")
        return Address(self.channel_id, f"{person}/{chat}")

    def chats_of(self, person: PersonId) -> str:
        """What the sessions of `person`'s chats start with."""
        return f"{self.channel_id}:{person}/"

    def say(self, message: InboundMessage) -> LiveAnswer:
        """Hand `message` to the assistant; its answer is written in the background. Raises `ChatBusy` while the
        chat's previous answer is still being written, `ProviderError` when the channel is not served."""
        if self._assistant is None or self._closing.is_set():
            raise ProviderError(self.name, "the chat is not served", transient=True)
        if message.address in self._live:
            raise ChatBusy(f"{message.address} is still answering")
        live = self._live[message.address] = LiveAnswer(self._assistant.respond(message), self._forget(message.address))
        return live

    def following(self, address: Address) -> LiveAnswer | None:
        """The answer being written in a chat, if any."""
        return self._live.get(address)

    def answering(self) -> list[Address]:
        """The chats whose answer is being written."""
        return list(self._live)

    def _forget(self, address: Address) -> Callable[[LiveAnswer], None]:
        def over(live: LiveAnswer) -> None:
            if self._live.get(address) is live:
                del self._live[address]

        return over

    async def serve(self, assistant: Assistant) -> None:
        self._assistant = assistant
        await self._closing.wait()

    async def send(self, to: Address, text: str, medium: Medium) -> None:
        if not self.reachable(to, medium):
            raise ContractError(f"{to} is not on channel {self.channel_id!r} {medium}")
        if self._closing.is_set():
            raise ProviderError(self.name, "the channel is closed", transient=False)
        # delivered by being logged: the chat is read from the journal

    async def close(self) -> None:
        self._closing.set()
        live, self._live = self._live, {}
        await asyncio.gather(*(answer.close() for answer in live.values()))
