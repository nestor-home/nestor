"""The agent itself, for whoever lives with it: what it is doing now, and when it will speak up on its own
(its quiet hours, the messages it has scheduled). Read with `agent.read`, no configuration rights needed."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nestor.admin.api.v1.agent.schemas import AgentActivityOut, InitiativeOut, QuietHoursOut, ScheduledDeliveryOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.api.v1.shared import People
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["agent"])
Reader = Annotated[Caller, Depends(allowed(Scope.AGENT_READ))]


@router.get("/agent/activity")
async def get_agent_activity(request: Request, caller: Reader) -> AgentActivityOut:
    """Listening beats speaking, then thinking, working (delegated tasks), sleeping (quiet hours), idle.
    The journal's stream sends the same as `event: activity` on every change."""
    return AgentActivityOut.of(state(request).nestor.activity.current())


@router.get("/agent/initiative")
async def get_agent_initiative(request: Request, caller: Reader) -> InitiativeOut:
    nestor = state(request).nestor
    people = People(nestor.household)
    everyone = caller.principal.can(Scope.JOURNAL_READ_ALL)
    return InitiativeOut(
        quiet_hours=QuietHoursOut.of(nestor.courier.policy, active=nestor.activity.current().quiet),
        upcoming=[
            ScheduledDeliveryOut.of(f, people)
            for f in nestor.courier.scheduled()
            if everyone or (caller.person is not None and f.person == caller.person)
        ],
    )
