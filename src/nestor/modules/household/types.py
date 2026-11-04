"""People of the household and their accounts on channels."""

from dataclasses import dataclass

from nestor.core import ContractError, PersonId
from nestor.modules.channels import Address

ANYONE = "*"


@dataclass(frozen=True, slots=True)
class Account:
    """How a channel authenticates a person: `telegram:123456789`. One account stands for one person; a shared
    device (a satellite) is a place, not an account: who speaks there is told by their voice or their words."""

    channel: str
    sender: str

    @classmethod
    def parse(cls, text: str) -> "Account":
        channel, sep, sender = text.partition(":")
        if not (sep and channel and sender):
            raise ContractError(f"invalid account {text!r}, expected 'channel:sender'")
        if sender == ANYONE:
            raise ContractError(f"invalid account {text!r}: an account stands for one person, not anyone")
        return cls(channel, sender)

    def __str__(self) -> str:
        return f"{self.channel}:{self.sender}"


@dataclass(frozen=True, slots=True, kw_only=True)
class Person:
    id: PersonId
    name: str
    accounts: tuple[Account, ...] = ()
    reach: Address | None = None  # where to write when they are not in the conversation
    may_message: tuple[str, ...] = (ANYONE,)  # whom they may have the agent write to: person ids, or everyone

    def may_write_to(self, other: PersonId) -> bool:
        return ANYONE in self.may_message or other in self.may_message

    def address_on(self, channel: str) -> Address | None:
        """Where to write to them on `channel`: their account there."""
        return next((Address(a.channel, a.sender) for a in self.accounts if a.channel == channel), None)
