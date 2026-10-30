"""People of the household and their accounts on channels."""

from dataclasses import dataclass

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address

ANYONE = "*"


@dataclass(frozen=True, slots=True)
class Account:
    """How a channel knows a person: `telegram:123456789`.

    `voice:*` means "anyone speaking on the voice channel is assumed to be this person", the
    explicit stand-in until a speaker identifier is plugged in.
    """

    channel: str
    sender: str

    @classmethod
    def parse(cls, text: str) -> "Account":
        channel, sep, sender = text.partition(":")
        if not (sep and channel and sender):
            raise ContractError(f"invalid account {text!r}, expected 'channel:sender'")
        return cls(channel, sender)

    def __str__(self) -> str:
        return f"{self.channel}:{self.sender}"


@dataclass(frozen=True, slots=True, kw_only=True)
class Person:
    id: PersonId
    name: str
    accounts: tuple[Account, ...] = ()
    reach: Address | None = None  # where to write when they are not in the conversation
