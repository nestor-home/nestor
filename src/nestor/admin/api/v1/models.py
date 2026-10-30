"""Shapes shared by several resources of the API. Field names are the wire contract of the front."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nestor.admin.presentation import Phrasebook
from nestor.core import Health, PersonId
from nestor.core.i18n import Message
from nestor.modules.accounts import Account, Accounts, Role
from nestor.modules.activity import AgentActivity
from nestor.modules.household import Household
from nestor.runtime import Nestor


class Input(BaseModel):
    """A request body: unknown fields are refused rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


class ProblemOut(BaseModel):
    """What is wrong in an edited configuration, located by its path in the document."""

    path: list[str | int]  # `["channels", 0, "token"]`; empty: the document as a whole
    code: str  # missing, extra, invalid, unknown_kind, reference (an environment variable), secret
    message_id: str  # `config-error-<code>`, with `args` {path, detail}
    args: dict[str, str | int | float]
    message: str


class ErrorDetail(BaseModel):
    code: str  # for programs: `invalid_credentials`, `last_owner`…
    message_id: str  # `error-<code with dashes>`, for a front rendering with its own catalogue
    args: dict[str, str | int | float]
    message: str  # rendered in the reader's language, shown as is
    problems: list[ProblemOut] | None = None  # a configuration refused: what is wrong, where


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


class LinksOut(BaseModel):
    """What threads entries together; the front builds threads and chains from these only."""

    session: str | None  # where people talk (`channel:conversation`, e.g. `telegram:42`, `voice:salon`)
    conversation: str | None  # one conversation in the session: turns within its inactivity window
    turn: str | None  # one message and all it caused: the user's message, tool calls, memories, tasks, the reply
    call: str | None  # a tool call: called, then completed
    task: str | None
    watch: str | None
    delivery: (
        str | None
    )  # what an unprompted message is about (`watch:w1`, `task:3f2a`): considered, delivered, followed up
    connection: str | None
    satellite: str | None  # a device id
    memory: str | None


class OutcomeOut(BaseModel):
    ok: bool
    duration_s: float


class ReasonOut(BaseModel):
    message: MessageOut
    text: str


class JournalItem(BaseModel):
    """One journal entry: each sentence as a message (`id` + `args`, for a front with the catalogue) and
    as text rendered by the server in the reader's language (so a plugin's events read well even when
    the front has no message for them)."""

    position: int  # grows with every entry: the cursor of pages, of the stream (`Last-Event-ID`), of `cause`
    id: str  # the event's own id
    at: datetime
    type: str  # the event type, e.g. `conversation.turn.user`
    kind: Kind
    kind_label: str
    message: MessageOut  # the summary; deliveries carry `args.follow_up` ("yes" / "no")
    text: str
    detail: str  # raw content (what was said, a tool's output): never translated; "" without
    detail_message: MessageOut | None = Field(  # a detail that is a sentence of Nestor's ("Planned: …")
        examples=[
            {"id": "journal-detail-plan", "args": {"way": "both", "spoken": "voice:salon", "written": "telegram:7"}}
        ]
    )
    detail_text: str  # what to show as detail: `detail_message` rendered, else `detail`
    reason: ReasonOut | None  # why the assistant decided to speak, when it did
    tone: Tone
    people: list[PersonRef]
    channels: list[str]
    room: str | None
    tool: str | None  # the tool called
    outcome: OutcomeOut | None  # of a tool call or a task
    brand: str | None  # of the channel, connector, satellite or executor it came through
    links: LinksOut
    cause: int | None  # the position of the entry that caused this one, when known


class AccountOut(BaseModel):
    id: str
    login: str
    role: Role
    role_label: str
    person: PersonRef | None
    disabled: bool
    created_at: datetime
    locale: str | None  # the language it chose; None: the household's
    last_seen_at: datetime | None  # its last sign-in or request (to the minute); None: never since it was opened

    @classmethod
    def of(cls, account: Account, people: People, words: Phrasebook, accounts: Accounts) -> "AccountOut":
        return cls(
            id=account.id,
            login=account.login,
            role=account.role,
            role_label=words.role(account.role),
            person=people.ref(account.person),
            disabled=account.disabled,
            created_at=account.created_at,
            locale=account.locale,
            last_seen_at=accounts.last_seen(account.id),
        )


class AgentOut(BaseModel):
    """The assistant itself, as the front's sidebar shows it."""

    name: str  # the persona's name ("Richie")
    status: Literal["online", "degraded"]  # degraded: its model or one of its channels cannot serve now

    @classmethod
    def of(cls, nestor: Nestor) -> "AgentOut":
        required = [nestor.model, *nestor.channels]
        degraded = any(c.health() is not Health.STARTED for c in required)
        return cls(name=nestor.config.persona.name, status="degraded" if degraded else "online")


class AgentActivityOut(BaseModel):
    """What the agent is doing now, from what really runs: `GET /agent/activity`, and `event: activity` on
    the journal's stream at its start and on every change."""

    state: Literal["idle", "listening", "thinking", "speaking", "working", "sleeping"]
    since: datetime  # when it entered this state (as this instance saw it: its start at the earliest)
    replies: int  # answers being produced now
    tasks: int  # delegated tasks running
    listening_rooms: list[str]  # where a satellite hears someone speak
    quiet: bool  # within the quiet hours now

    @classmethod
    def of(cls, activity: AgentActivity) -> "AgentActivityOut":
        return cls(
            state=activity.state.value,
            since=activity.since,
            replies=activity.replies,
            tasks=activity.tasks,
            listening_rooms=list(activity.listening_rooms),
            quiet=activity.quiet,
        )
