"""Channels: every way to reach the assistant (voice, messaging apps, web) behind one port.

A channel turns platform traffic into `InboundMessage`s, lets the `Assistant` answer, and delivers
the answer back. Voice is a channel too: a realtime voice pipeline, a hosted voice framework or a
speech-to-speech model each implement `Channel`, so every channel reaches the same assistant.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from nestor.core import Component, ContractError, PersonId
from nestor.modules.channels.types import Address, InboundMessage, Medium, Sender
from nestor.modules.identity import Heard


@dataclass(frozen=True, slots=True)
class MessageEnd:
    """Marks the end of a message in a `Reply`: the assistant stops writing to act (a tool call)
    and the next words start a new message. `last`: no other message follows in this turn, so a
    screen can stop showing that the assistant is still at work."""

    last: bool = True


class Reply(ABC):
    """An answer streamed as text chunks, in one or more messages: the assistant ends a message
    when it stops to act and starts another once it knows more ("Je regarde.", then the result).

    A written channel sends each of `messages()` as soon as it is complete. A voice channel speaks
    `speech()` as it comes and, if the user cuts in, calls `interrupt` with what was actually heard
    so that the assistant remembers only that part.
    """

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[str | MessageEnd]:
        """Text chunks, each message followed by a `MessageEnd`."""

    @abstractmethod
    async def interrupt(self, heard: str) -> None:
        """Stop the answer; `heard` is the part the user received before cutting in."""

    async def messages(self) -> AsyncIterator[str]:
        """Each complete message, as soon as it ends."""
        chunks: list[str] = []
        async for part in self:
            if isinstance(part, MessageEnd):
                if text := "".join(chunks).strip():
                    yield text
                chunks.clear()
            else:
                chunks.append(part)
        if text := "".join(chunks).strip():  # cut before its end
            yield text

    async def speech(self) -> AsyncIterator[str]:
        """The messages as one continuous text, a space between two of them."""
        ended, last = False, ""
        async for part in self:
            if isinstance(part, MessageEnd):
                ended = bool(last)
                continue
            if ended and not last[-1:].isspace() and not part[:1].isspace():
                part = f" {part}"
            ended, last = False, part
            yield part

    async def collect(self) -> tuple[str, ...]:
        return tuple([message async for message in self.messages()])


class Assistant(ABC):
    """What channels see of Nestor: one assistant, whatever the channel."""

    @abstractmethod
    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        """The household member behind an account; `None` means a stranger, whom channels drop. A shared device
        asks nothing: it serves whoever is there (`InboundMessage.sender` is `None`)."""

    @abstractmethod
    def respond(self, message: InboundMessage) -> Reply: ...

    @property
    def voice_wait_s(self) -> float | None:
        """How long a turn may wait for its voice to be recognised; `None` when voices are not, and a voice
        channel need not hand any speech to `hear`."""
        return None

    async def hear(self, audio: bytes) -> Heard | None:
        """Who said `audio` (16-bit mono PCM at 16 kHz), as far as their voice tells; `None` without recognition.
        Called as soon as the speech ends, while it is transcribed, so that the turn does not wait for it."""
        return None


class Channel(Component, ABC):
    """Contract:
    - `serve` receives messages until the channel is closed and answers each one through the assistant;
      when it raises, Nestor logs it and calls `serve` again after a pause, so it must be callable again;
    - `send` delivers an unprompted message (task result, initiative) through one of its `media` and
      raises `ProviderError` when it cannot: aloud with nobody connected, for instance;
    - senders the channel cannot authenticate are dropped before reaching the assistant, unless it is a shared
      device that vouches for its place only (`sender=None`);
    - `conversation_ends_after_s` is how long a conversation on it lasts without a turn: what each
      turn's medium suggests, unless its configuration says otherwise.
    """

    media: frozenset[Medium] = frozenset({Medium.WRITTEN})  # how its turns can travel
    style: str = ""  # how to write for this channel (e.g. expression tags the voice understands)

    def __init__(self, channel_id: str, *, conversation_ends_after_s: float | None = None) -> None:
        if conversation_ends_after_s is not None and conversation_ends_after_s <= 0:
            raise ContractError("a conversation must last more than 0 s without a turn")
        self.channel_id = channel_id
        self._conversation_ends_after_s = conversation_ends_after_s

    @property
    def conversation_ends_after_s(self) -> float | None:
        """The silence after which the next turn opens a new conversation, when configured; otherwise
        each turn's medium decides."""
        return self._conversation_ends_after_s

    @property
    def spoken(self) -> bool:
        """Whether it can be heard in rooms."""
        return Medium.SPOKEN in self.media

    @abstractmethod
    async def serve(self, assistant: Assistant) -> None: ...

    @abstractmethod
    async def send(self, to: Address, text: str, medium: Medium) -> None: ...

    @property
    def rooms(self) -> frozenset[str]:
        """Rooms (home area ids) where a spoken channel can be heard right now: its satellites' rooms."""
        return frozenset()

    def reachable(self, to: Address, medium: Medium) -> bool:
        """Whether `send` can deliver through `medium` now (aloud needs someone connected). Cheap;
        `send` may still fail."""
        return to.channel == self.channel_id and medium in self.media
