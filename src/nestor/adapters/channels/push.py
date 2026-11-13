"""What the channels that only send share (ntfy, webhook): nothing to serve, a closed channel refuses to send.

Nobody answers through them: they are where Nestor reaches someone by itself (a reminder, a task's result).
"""

import asyncio
from abc import ABC, abstractmethod

from nestor.core import ProviderError
from nestor.modules.channels import Address, Assistant, Attachment, Channel, Medium


class PushChannel(Channel, ABC):
    """Contract: `push` delivers `text` with the `attachments` of the kinds the channel `sends` to `conversation`
    (a topic, a target), raising `ProviderError` when it cannot."""

    def __init__(self, channel_id: str) -> None:
        super().__init__(channel_id)
        self._closed = asyncio.Event()

    @abstractmethod
    async def push(self, conversation: str, text: str, attachments: tuple[Attachment, ...]) -> None: ...

    async def serve(self, assistant: Assistant) -> None:
        await self._closed.wait()  # nothing comes in

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...]) -> None:
        self.check_serves(to, medium)
        if self._closed.is_set():
            raise ProviderError(self.brand or self.name, "the channel is closed", transient=False)
        await self.push(to.conversation, text, attachments)

    async def close(self) -> None:
        self._closed.set()
