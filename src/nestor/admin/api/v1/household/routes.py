"""The household: its people, where they are, what is plugged in for them, whether they have an account."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.access import household_person
from nestor.admin.api.v1.household.schemas import PersonOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import Usage
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["household"])
Reader = Annotated[Caller, Depends(allowed(Scope.HOUSEHOLD_READ))]


@router.get("/household/people")
async def list_people(request: Request, caller: Reader) -> list[PersonOut]:
    admin = state(request)
    usage = await Usage.of(admin)
    return [PersonOut.of(admin, caller, p, usage) for p in admin.nestor.household.people]


@router.get("/household/people/{person_id}")
async def get_person(request: Request, caller: Reader, person_id: str) -> PersonOut:
    admin = state(request)
    person = admin.nestor.household.person(household_person(admin, person_id))
    return PersonOut.of(admin, caller, person, await Usage.of(admin))
