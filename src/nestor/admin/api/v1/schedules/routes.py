"""Wake-ups and reminders: what the agent will do later on its own, for whom, when — and cancelling one.

`schedules.manage.all` reaches every wake-up; `schedules.manage.own` those set for the account's person.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.access import reachable_schedule, reaches_schedule
from nestor.admin.api.v1.schedules.schemas import ScheduleOut, SchedulesOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["schedules"])
Manager = Annotated[Caller, Depends(allowed(Scope.SCHEDULES_MANAGE_ALL, Scope.SCHEDULES_MANAGE_OWN))]


@router.get("/schedules")
async def list_schedules(request: Request, caller: Manager) -> SchedulesOut:
    """Soonest first."""
    nestor = state(request).nestor
    book, people = nestor.schedule_book, People(nestor.household)
    return SchedulesOut(
        schedules=[ScheduleOut.of(s, book, people) for s in book.upcoming() if reaches_schedule(caller, s)],
        timezone=book.timezone,
    )


@router.post("/schedules/{schedule_id}/cancel", status_code=204)
async def cancel_schedule(request: Request, caller: Manager, schedule_id: str) -> Response:
    admin = state(request)
    schedule = reachable_schedule(admin, caller, schedule_id)
    await admin.nestor.schedule_book.cancel(schedule.id, by=caller.person)
    return Response(status_code=204)
