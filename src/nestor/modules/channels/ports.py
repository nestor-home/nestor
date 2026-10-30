"""Channels: every way to reach the assistant (voice, messaging apps, web) behind one port.

A channel turns platform traffic into `InboundMessage`s, lets the `Assistant` answer, and delivers
the answer back. Voice is a channel too: a realtime voice pipeline, a hosted voice framework or a
speech-to-speech model each implement `Channel`, so every channel reaches the same assistant.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from nestor.core import Component, PersonId
from nestor.modules.channels.types import Address, InboundMessage, Medium, Sender


class Reply(ABC):
    """An answer streamed as text chunks.

    Text channels can simply `collect()` it. A voice channel speaks chunks as they come and, if the
    user cuts in, calls `interrupt` with what was actually heard so that the assistant remembers
    only that part.
    """

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[str]: ...

    @abstractmethod
    async def interrupt(self, heard: str) -> None:
        """Stop the answer; `heard` is the part the user received before cutting in."""

    async def collect(self) -> str:
        return "".join([chunk async for chunk in self])


class Assistant(ABC):
    """What channels see of Nestor: one assistant, whatever the channel."""

    @abstractmethod
    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        """The household member behind a sender; `None` means a stranger, whom channels drop."""

    @abstractmethod
    def respond(self, message: InboundMessage) -> Reply: ...


class Channel(Component, ABC):
    """Contract:
    - `serve` receives messages until the channel is closed and answers each one through the assistant;
    - `send` delivers an unprompted message (task result, initiative) and raises `ProviderError` when
      it cannot — a voice channel with nobody connected cannot;
    - senders the channel cannot authenticate are dropped before reaching the assistant.
    """

    medium: Medium = Medium.WRITTEN
    style: str = ""  # how to write for this channel (e.g. expression tags the voice understands)
    room: str | None = None  # where a spoken channel is heard (a home area id), if it is a satellite

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id

    @abstractmethod
    async def serve(self, assistant: Assistant) -> None: ...

    @abstractmethod
    async def send(self, to: Address, text: str) -> None: ...

    def reachable(self, to: Address) -> bool:
        """Whether `send` can deliver now (a voice channel needs someone connected). Cheap; `send`
        may still fail."""
        return to.channel == self.channel_id
