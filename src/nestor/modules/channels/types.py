"""Values exchanged with channels: where a message comes from, who sent it, what it carries."""

from dataclasses import dataclass, field
from datetime import datetime

from nestor.core import ContractError, SessionId, new_id, utc_now


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
