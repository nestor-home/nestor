"""Shapes shared by several resources of the API. Field names are the wire contract of the front."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nestor.admin.presentation import Phrasebook
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import Account, Role
from nestor.modules.household import Household


class Input(BaseModel):
    """A request body: unknown fields are refused rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


class ErrorDetail(BaseModel):
    code: str
    message: str  # in French, shown as is


class ErrorOut(BaseModel):
    error: ErrorDetail


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


Tone = Literal["normal", "decision", "warning"]
Kind = Literal[
    "conversation",
    "delivery",
    "tool",
    "task",
    "watch",
    "memory",
    "connection",
    "presence",
    "satellite",
    "observation",
    "account",
    "other",
]


class JournalItem(BaseModel):
    """One journal entry: each sentence as a message (`id` + `args`, for a front with the catalogue) and
    as `*text`, rendered by the server in the reader's language (so a plugin's events read well even
    when the front has no message for them)."""

    position: int  # grows with every entry: the cursor of pages and of the live stream (`Last-Event-ID`)
    at: datetime
    type: str  # the event type, e.g. `conversation.turn.user`
    kind: Kind
    kind_label: str  # rendered, as `GET /journal/filters` lists it
    message: MessageOut  # the summary
    text: str
    detail: str  # raw content (what was said, a tool's output): never translated; "" without
    detail_message: MessageOut | None  # a detail that is a sentence of Nestor's ("Planned: …")
    detail_text: str  # what to show as detail: `detail_message` rendered, else `detail`
    reason: MessageOut | None  # why the assistant decided to speak, when it did
    reason_text: str
    tone: Tone
    people: list[PersonRef]
    channels: list[str]
    # What links entries together (threads, causal chains); each is None when the event has none.
    session: str | None  # the conversation (`channel:conversation`) it belongs to
    task_id: str | None
    watch_id: str | None
    call_id: str | None  # a tool call: `agent.tool.called` and its `agent.tool.completed`
    turn: str | None  # the `conversation.turn.assistant` entry id an answer cut refers to
    item_id: str | None  # the inbound item (a mail) a watch triggered on
    connection_id: str | None
    device_id: str | None  # a satellite
    pairing_id: str | None
    memory_id: str | None
    account_id: str | None
    invitation_id: str | None
    id: str  # the event's own id (what `turn` refers to)


LINKS = (
    "task_id",
    "watch_id",
    "call_id",
    "turn",
    "item_id",
    "connection_id",
    "device_id",
    "pairing_id",
    "memory_id",
    "account_id",
    "invitation_id",
)


class AccountOut(BaseModel):
    id: str
    login: str
    role: Role
    role_label: str
    person: PersonRef | None
    disabled: bool
    created_at: datetime
    locale: str | None  # the language it chose; None: the household's

    @classmethod
    def of(cls, account: Account, people: People, words: Phrasebook) -> "AccountOut":
        return cls(
            id=account.id,
            login=account.login,
            role=account.role,
            role_label=words.role(account.role),
            person=people.ref(account.person),
            disabled=account.disabled,
            created_at=account.created_at,
            locale=account.locale,
        )
