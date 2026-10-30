"""Values exchanged with channels: where a message comes from, who sent it, what it carries."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from nestor.core import ContractError, SessionId, new_id, utc_now
from nestor.core.events import JSON


class Medium(StrEnum):
    """How the user receives answers: it decides their form (length, no Markdown when spoken), and how
    long a conversation lasts without a turn."""

    SPOKEN = "spoken"
    WRITTEN = "written"

    @property
    def conversation_ends_after_s(self) -> float:
        """The silence after which the next turn opens a new conversation, unless a channel says otherwise.

        Spoken: 5 minutes, Home Assistant Assist's timeout; people speak in the moment and walk away.
        Written: 4 hours; a message chat is picked up again later in the day (after a meeting, after
        lunch), as a messaging thread is. A night's sleep is longer, so the next morning opens a new
        conversation without any clock rule.
        """
        return 300.0 if self is Medium.SPOKEN else 4 * 3600.0


@dataclass(frozen=True, slots=True)
class Address:
    """A conversation on a channel: `telegram:123456789`, `voice:living-room`.

    `channel` is the configured channel name, not the adapter kind: two Telegram bots are two channels.
    """

    channel: str
    conversation: str

    def __str__(self) -> str:
        return f"{self.channel}:{self.conversation}"

    @classmethod
    def parse(cls, text: str) -> "Address":
        channel, sep, conversation = text.partition(":")
        if not (sep and channel and conversation):
            raise ContractError(f"invalid address {text!r}, expected 'channel:conversation'")
        return cls(channel, conversation)

    @property
    def session(self) -> SessionId:
        """One session per conversation, whoever speaks in it (a group chat is one session)."""
        return SessionId(str(self))


@dataclass(frozen=True, slots=True, kw_only=True)
class Exchange:
    """Where an effect belongs in the dialogue, as Home Assistant's Assist counts it.

    `conversation_id` groups the turns of one session that follow each other closely: it ends after a
    while without any (`Channel.conversation_ends_after_s`). `turn_id` is one message and all it caused (tool
    calls, memories, tasks, the reply), or one unprompted message.
    """

    conversation_id: str
    turn_id: str


def before_exchanges(payload: dict[str, JSON]) -> dict[str, JSON]:
    """The payload of a version 1 record of an event that gained `exchange` in version 2: written
    before conversations were counted, it belongs to none."""
    return {**payload, "exchange": None}


@dataclass(frozen=True, slots=True)
class Sender:
    """The author as the channel knows them; the runtime maps `id` to a person of the household."""

    id: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Media:
    uri: str
    mime_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class InboundMessage:
    address: Address
    sender: Sender
    text: str
    media: tuple[Media, ...] = ()
    id: str = field(default_factory=new_id)
    at: datetime = field(default_factory=utc_now)
