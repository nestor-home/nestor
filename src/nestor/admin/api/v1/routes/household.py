"""The household: its people, where they are, what is plugged in for them, whether they have an account."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nestor.admin.api.v1.errors import not_found
from nestor.admin.api.v1.models import AccountOut, People
from nestor.admin.api.v1.routes.connections import ConnectionOut, Usage, connection_out, reaches
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import AdminState, state
from nestor.modules.accounts import Scope
from nestor.modules.household import Person

router = APIRouter(tags=["household"])
Reader = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_READ))]


class PresenceOut(BaseModel):
    home: bool | None  # None: no tracker knows
    room: str | None
    since: datetime | None  # when these whereabouts started, when the presence source knows


class PersonOut(BaseModel):
    id: str
    name: str
    channel_accounts: list[str]  # how channels know them: "telegram:123", "voice:*"
    reach: str | None  # where the assistant writes to them
    presence: PresenceOut | None  # None: no presence source is plugged in
    connections: list[ConnectionOut]  # only those the caller reaches
    account: AccountOut | None  # only for `accounts.manage`


@router.get("/household/people")
async def list_people(request: Request, caller: Reader) -> list[PersonOut]:
    admin = state(request)
    usage = await Usage.of(admin)
    return [_person(admin, caller, p, usage) for p in admin.nestor.household.people]


@router.get("/household/people/{person_id}")
async def get_person(request: Request, caller: Reader, person_id: str) -> PersonOut:
    admin = state(request)
    person = next((p for p in admin.nestor.household.people if p.id == person_id), None)
    if person is None:
        raise not_found("person_unknown")
    return _person(admin, caller, person, await Usage.of(admin))


def _person(admin: AdminState, caller: Caller, person: Person, usage: Usage) -> PersonOut:
    nestor = admin.nestor
    presence = nestor.presence.presence() if nestor.presence else None
    connections = list(nestor.connections.connections.values()) if nestor.connections else []
    whereabouts = presence.of(person.id) if presence else None
    account = admin.accounts.of_person(person.id) if caller.principal.can(Scope.ACCOUNTS_MANAGE) else None
    return PersonOut(
        id=person.id,
        name=person.name,
        channel_accounts=[str(a) for a in person.accounts],
        reach=str(person.reach) if person.reach else None,
        presence=PresenceOut(home=whereabouts.home, room=whereabouts.room, since=whereabouts.since)
        if whereabouts
        else None,
        connections=[
            connection_out(admin, c, caller.phrasebook, usage)
            for c in connections
            if c.owner == person.id and reaches(caller.principal, c.owner)
        ],
        account=AccountOut.of(account, People(nestor.household), caller.phrasebook, admin.accounts)
        if account
        else None,
    )
