"""What every resource builds on: a request body, a person as the front names them, a message as data. A shape
one resource owns and another sends lives in the owner's `schemas.py`."""

from pydantic import BaseModel, ConfigDict

from nestor.admin.presentation import Phrasebook
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.channels import Address
from nestor.modules.household import Household


class Input(BaseModel):
    """A request body: unknown fields are refused rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


# -- people and messages -------------------------------------------------------------------------------


class PersonRef(BaseModel):
    id: str
    name: str


class People:
    """Person ids as the front shows them: with their name (an id no longer in the household keeps it as name)."""

    def __init__(self, household: Household) -> None:
        self._names = {p.id: p.name for p in household.people}

    def ref(self, person: PersonId | None) -> PersonRef | None:
        if person is None:
            return None
        return PersonRef(id=person, name=self._names.get(person, person))

    def known(self, person: str) -> bool:
        return PersonId(person) in self._names


class MessageOut(BaseModel):
    """A message as data: a front with its own Fluent catalogue renders `id` with `args` itself."""

    id: str
    args: dict[str, str | int | float]

    @classmethod
    def of(cls, message: Message) -> "MessageOut":
        return cls(id=message.id, args=dict(message.args))


class ReasonOut(BaseModel):
    message: MessageOut
    text: str

    @classmethod
    def of(cls, message: Message, words: Phrasebook) -> "ReasonOut":
        return cls(message=MessageOut.of(message), text=words.text(message))


class OriginOut(BaseModel):
    """Where something was asked for: a task, a watch."""

    session: str  # the conversation it was asked in
    channel: str

    @classmethod
    def of(cls, address: Address) -> "OriginOut":
        return cls(session=str(address), channel=address.channel)
