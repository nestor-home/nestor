"""The household: its people, where they are, what is plugged in for them, whether they have an account."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nestor.admin.api.v1.models import AccountOut, People
from nestor.admin.api.v1.routes.connections import ConnectionOut, connection_out, reaches
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["household"])
Reader = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_READ))]


class PresenceOut(BaseModel):
    home: bool | None  # None: no tracker knows
    room: str | None


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
    nestor = admin.nestor
    people = People(nestor.household)
    presence = nestor.presence.presence() if nestor.presence else None
    connections = list(nestor.connections.connections.values()) if nestor.connections else []
    accounts = caller.principal.can(Scope.ACCOUNTS_MANAGE)
    listed = []
    for person in nestor.household.people:
        whereabouts = presence.of(person.id) if presence else None
        account = admin.accounts.of_person(person.id) if accounts else None
        listed.append(
            PersonOut(
                id=person.id,
                name=person.name,
                channel_accounts=[str(a) for a in person.accounts],
                reach=str(person.reach) if person.reach else None,
                presence=PresenceOut(home=whereabouts.home, room=whereabouts.room) if whereabouts else None,
                connections=[
                    connection_out(admin, c)
                    for c in connections
                    if c.owner == person.id and reaches(caller.principal, c.owner)
                ],
                account=AccountOut.of(account, people) if account else None,
            )
        )
    return listed
