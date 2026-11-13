"""Connections as the API sends them (the household and connectors send them too) and what changing one takes."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from nestor.admin.api.v1.access import connections_of
from nestor.admin.api.v1.shared import Input, People, PersonRef, ReasonOut
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState
from nestor.core import utc_now
from nestor.modules.cognition.tools import Risk, ToolCalled
from nestor.modules.connectors import Connection, Status


class ConnectionSettingsIn(Input):
    disabled_tools: list[str] | None = None
    confirm_writes: bool | None = None


USAGE_SCAN = 5000  # tool calls read, newest first, to say when each tool was last used


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
            brand=connector.brand_of(connection) if connector else None,
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
