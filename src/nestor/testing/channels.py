"""Doubles for the channels module: an in-memory channel and a scripted assistant."""

import asyncio
from collections.abc import AsyncIterator, Callable

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address, Assistant, Channel, InboundMessage, Reply, Sender


class ScriptedReply(Reply):
    """Streams `text` word by word; stops as soon as it is interrupted."""

    def __init__(self, text: str, *, word_delay_s: float = 0.0) -> None:
        self._words = text.split()
        self._word_delay_s = word_delay_s
        self.heard: str | None = None

    async def __aiter__(self) -> AsyncIterator[str]:
        for i, word in enumerate(self._words):
            if self.heard is not None:
                return
            await asyncio.sleep(self._word_delay_s)
            yield word if i == 0 else f" {word}"

    async def interrupt(self, heard: str) -> None:
        self.heard = heard


class ScriptedAssistant(Assistant):
    """Answers with `answer(message)` and keeps every message and reply for inspection.

    Every sender is a household member unless `strangers` lists them.
    """

    def __init__(
        self,
        answer: Callable[[InboundMessage], str],
        *,
        word_delay_s: float = 0.0,
        strangers: frozenset[str] = frozenset(),
    ) -> None:
        self._answer = answer
        self._strangers = strangers
        self._word_delay_s = word_delay_s
        self.messages: list[InboundMessage] = []
        self.replies: list[ScriptedReply] = []

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return None if sender.id in self._strangers else PersonId(sender.id)

    def respond(self, message: InboundMessage) -> ScriptedReply:
        self.messages.append(message)
        reply = ScriptedReply(self._answer(message), word_delay_s=self._word_delay_s)
        self.replies.append(reply)
        return reply


class InMemoryChannel(Channel):
    """A text channel driven by the test: `ask` plays a user message and returns the full answer,
    or `None` when the assistant does not know the sender."""

    name = "in-memory"

    def __init__(self, channel_id: str = "memory") -> None:
        super().__init__(channel_id)
        self._inbox: asyncio.Queue[tuple[InboundMessage, asyncio.Future[str | None]] | None] = asyncio.Queue()
        self.sent: list[tuple[Address, str]] = []

    async def serve(self, assistant: Assistant) -> None:
        while (item := await self._inbox.get()) is not None:
            message, answered = item
            if assistant.identify(message.address, message.sender) is None:
                answered.set_result(None)
                continue
            try:
                answered.set_result(await assistant.respond(message).collect())
            except Exception as error:
                answered.set_exception(error)

    async def ask(self, text: str, *, sender: str = "user", conversation: str = "main") -> str | None:
        message = InboundMessage(address=Address(self.channel_id, conversation), sender=Sender(sender), text=text)
        answered: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        await self._inbox.put((message, answered))
        return await answered

    async def send(self, to: Address, text: str) -> None:
        if to.channel != self.channel_id:
            raise ContractError(f"{to} is not on channel {self.channel_id!r}")
        self.sent.append((to, text))

    async def close(self) -> None:
        self._inbox.put_nowait(None)
