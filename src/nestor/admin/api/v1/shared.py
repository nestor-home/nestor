"""Shapes several resources send, each built from the domain by its `of`. Field names are the wire contract
of the front."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.language import account_locale
from nestor.admin.auth import Session
from nestor.admin.connecting import Connecting
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState
from nestor.core import Health, PersonId, utc_now
from nestor.core.i18n import Message
from nestor.modules.accounts import Account, Accounts, Role, Scope
from nestor.modules.activity import Activity, AgentActivity
from nestor.modules.cognition.tools import Risk, ToolCalled
from nestor.modules.connectors import Connection, Connections, Status
from nestor.modules.household import Household
from nestor.runtime import Nestor

USAGE_SCAN = 5000  # tool calls read, newest first, to say when each tool was last used


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


# -- the account and the agent -------------------------------------------------------------------------


class AccountOut(BaseModel):
    id: str
    login: str
    role: Role
    person: PersonRef | None
    disabled: bool
    created_at: datetime
    locale: str | None  # the language it chose; None: the household's
    last_seen_at: datetime | None  # its last sign-in or request (to the minute); None: never since it was opened

    @classmethod
    def of(cls, account: Account, people: People, accounts: Accounts) -> "AccountOut":
        return cls(
            id=account.id,
            login=account.login,
            role=account.role,
            person=people.ref(account.person),
            disabled=account.disabled,
            created_at=account.created_at,
            locale=account.locale,
            last_seen_at=accounts.last_seen(account.id),
        )


class AgentOut(BaseModel):
    """The assistant itself, as the front's sidebar shows it."""

    name: str  # the persona's name ("Richie")
    status: Health  # started, or degraded when its model or one of its channels cannot serve now

    @classmethod
    def of(cls, nestor: Nestor) -> "AgentOut":
        required = [*nestor.agent.models.distinct(), *nestor.channels]
        degraded = any(c.health() is not Health.STARTED for c in required)
        return cls(name=nestor.config.persona.name, status=Health.DEGRADED if degraded else Health.STARTED)


class AgentActivityOut(BaseModel):
    """What the agent is doing now, from what really runs: `GET /agent/activity`, and `event: activity` on
    the journal's stream at its start and on every change."""

    state: Activity
    since: datetime  # when it entered this state (as this instance saw it: its start at the earliest)
    replies: int  # answers being produced now
    tasks: int  # delegated tasks running
    listening_rooms: list[str]  # where a satellite hears someone speak
    quiet: bool  # within the quiet hours now

    @classmethod
    def of(cls, activity: AgentActivity) -> "AgentActivityOut":
        return cls(
            state=activity.state,
            since=activity.since,
            replies=activity.replies,
            tasks=activity.tasks,
            listening_rooms=list(activity.listening_rooms),
            quiet=activity.quiet,
        )


class MeOut(BaseModel):
    account: AccountOut
    locale: str  # the language it reads in: its choice, else the household's (`account.locale` is the choice)
    scopes: list[Scope]  # what the front may offer; the API checks them again on every request
    csrf_token: str  # send it back in `X-CSRF-Token` on every POST, PUT, PATCH and DELETE
    assistant: str  # the assistant's name, for the front's header (also `agent.name`)
    agent: AgentOut
    restart_required: bool  # the configuration was written since the instance started
    pending_changes: list[str]

    @classmethod
    def of(cls, admin: AdminState, account: Account, session: Session) -> "MeOut":
        return cls(
            account=AccountOut.of(account, People(admin.nestor.household), admin.accounts),
            locale=account_locale(admin, account),
            scopes=sorted(account.principal().scopes),
            csrf_token=session.csrf,
            assistant=admin.nestor.config.persona.name,
            agent=AgentOut.of(admin.nestor),
            restart_required=bool(admin.pending_changes),
            pending_changes=admin.pending_changes,
        )


# -- connections: listed on their own, with a connector, and with their person ----------------------------


def connections_of(admin: AdminState) -> Connections:
    if admin.nestor.connections is None:
        raise ApiError(404, "no_connectors")
    return admin.nestor.connections


def connecting_of(admin: AdminState) -> Connecting:
    connections_of(admin)
    assert admin.connecting is not None  # built whenever connections are
    return admin.connecting


@dataclass(frozen=True, slots=True)
class Usage:
    """Tool calls by tool name: the last one, and how many today. Tools are named per connector
    (`<kind>_<action>`), so two accounts of one service share their counts."""

    last: dict[str, datetime]
    today: Counter[str]

    @classmethod
    async def of(cls, admin: AdminState) -> "Usage":
        nestor = admin.nestor
        zone = ZoneInfo(nestor.config.persona.timezone)
        midnight = datetime.combine(utc_now().astimezone(zone).date(), time(), zone)
        calls = await nestor.journal.history(ToolCalled, newest_first=True, limit=USAGE_SCAN)
        last: dict[str, datetime] = {}
        today: Counter[str] = Counter()
        for call in calls:
            last.setdefault(call.name, call.at)
            if call.at >= midnight:
                today[call.name] += 1
        return cls(last, today)


class ToolOut(BaseModel):
    name: str
    description: str
    risk: Risk
    enabled: bool


class ConnectionOut(BaseModel):
    id: str
    kind: str
    brand: str | None  # the connector's vendor
    title: str  # the connector's name
    account: str  # what the person recognises: "mathis@gmail.com"
    owner: PersonRef | None  # None: the whole household
    status: Status
    status_reason: ReasonOut | None  # why it needs authorising again or is in error
    confirm_writes: bool
    disabled_tools: list[str]
    created_at: datetime
    last_used_at: datetime | None  # the last call of one of its tools
    calls_today: int  # calls of its tools since midnight, in the household's timezone
    watches: int  # active watches fed by what it brings in (its person's, or everyone's for a shared one)

    @classmethod
    def of(cls, admin: AdminState, connection: Connection, words: Phrasebook, usage: Usage) -> "ConnectionOut":
        connections = connections_of(admin)
        connector = connections.connectors.get(connection.kind)
        names = {t.name for t in connector.tools(connection, connections.access(connection))} if connector else set()
        inbound = set(connector.info.inbound) if connector else set()
        reason = connection.status_reason
        return cls(
            id=connection.id,
            kind=connection.kind,
            brand=connector.info.brand if connector else None,
            title=words.text(connector.info.title) if connector else connection.kind,
            account=connection.account,
            owner=People(admin.nestor.household).ref(connection.owner),
            status=connection.status,
            status_reason=ReasonOut.of(reason, words) if reason and connection.status is not Status.CONNECTED else None,
            confirm_writes=connection.confirm_writes,
            disabled_tools=sorted(connection.disabled_tools),
            created_at=connection.created_at,
            last_used_at=max((usage.last[n] for n in names if n in usage.last), default=None),
            calls_today=sum(usage.today[n] for n in names),
            watches=sum(
                1
                for w in admin.nestor.watch_book.watches.values()
                if set(w.kinds) & inbound and (connection.owner is None or w.owner == connection.owner)
            ),
        )


class ConnectionDetail(ConnectionOut):
    tools: list[ToolOut]

    @classmethod
    def of(cls, admin: AdminState, connection: Connection, words: Phrasebook, usage: Usage) -> "ConnectionDetail":
        connections = connections_of(admin)
        connector = connections.connectors.get(connection.kind)
        tools = connector.tools(connection, connections.access(connection)) if connector else ()
        return cls(
            **ConnectionOut.of(admin, connection, words, usage).model_dump(),
            tools=[
                ToolOut(
                    name=t.name,
                    description=t.spec.description,
                    risk=t.risk,
                    enabled=t.name not in connection.disabled_tools,
                )
                for t in tools
            ],
        )
