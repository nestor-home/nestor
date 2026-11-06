"""A person of the household as the admin shows them."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.access import reaches_connections_of
from nestor.admin.api.v1.security import Caller
from nestor.admin.api.v1.shared import AccountOut, ConnectionOut, People, Usage
from nestor.admin.state import AdminState
from nestor.modules.accounts import Scope
from nestor.modules.home import Whereabouts
from nestor.modules.household import Person


class PresenceOut(BaseModel):
    home: bool | None  # None: no tracker knows
    room: str | None
    since: datetime | None  # when these whereabouts started, when the presence source knows

    @classmethod
    def of(cls, whereabouts: Whereabouts) -> "PresenceOut":
        return cls(home=whereabouts.home, room=whereabouts.room, since=whereabouts.since)


class PersonOut(BaseModel):
    id: str
    name: str
    channel_accounts: list[str]  # the accounts channels authenticate them by: "telegram:123"
    reach: str | None  # where the assistant writes to them
    presence: PresenceOut | None  # None: no presence source is plugged in
    connections: list[ConnectionOut]  # only those the caller reaches
    account: AccountOut | None  # only for `accounts.manage`

    @classmethod
    def of(cls, admin: AdminState, caller: Caller, person: Person, usage: Usage) -> "PersonOut":
        nestor = admin.nestor
        whereabouts = nestor.presence.presence().of(person.id) if nestor.presence else None
        connections = nestor.connections.connections.values() if nestor.connections else ()
        account = admin.accounts.of_person(person.id) if caller.principal.can(Scope.ACCOUNTS_MANAGE) else None
        return cls(
            id=person.id,
            name=person.name,
            channel_accounts=[str(a) for a in person.accounts],
            reach=str(person.reach) if person.reach else None,
            presence=PresenceOut.of(whereabouts) if whereabouts else None,
            connections=[
                ConnectionOut.of(admin, c, caller.phrasebook, usage)
                for c in connections
                if c.owner == person.id and reaches_connections_of(caller.principal, c.owner)
            ],
            account=AccountOut.of(account, People(nestor.household), admin.accounts) if account else None,
        )
