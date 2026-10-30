"""The agent itself, for whoever lives with it: what it is doing now, and when it will speak up on its own
(its quiet hours, the messages it has scheduled). Read with `agent.read`, no configuration rights needed."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nestor.admin.api.v1.models import AgentActivityOut, People, PersonRef
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import subject
from nestor.admin.state import state
from nestor.modules.accounts import Scope

router = APIRouter(tags=["agent"])
Reader = Annotated[Caller, Depends(allowed(Scope.AGENT_READ))]


class QuietHoursOut(BaseModel):
    start: str  # "22:30", the household's local time
    end: str  # "07:30"; earlier than `start` when the quiet hours cross midnight
    timezone: str  # the household's (`persona.timezone`)
    active: bool  # within them now


class ScheduledDeliveryOut(BaseModel):
    """A written follow-up of something said aloud: sent at `due_at` unless someone answers first."""

    about: str  # as journaled: `task 3f2a completed`, `watch w1`
    delivery: str  # the thread it belongs to, as the journal's `links.delivery` (`watch:w1`, `task:3f2a`)
    person: PersonRef | None
    spoken_on: str  # where it was said (`voice:salon`)
    written_on: str  # where it will be written (`telegram:7`)
    due_at: datetime


class InitiativeOut(BaseModel):
    quiet_hours: QuietHoursOut | None  # None: the agent may speak up at any hour
    upcoming: list[ScheduledDeliveryOut]  # soonest first; with `journal.read.own` only, those for one's person


@router.get("/agent/activity")
async def get_agent_activity(request: Request, caller: Reader) -> AgentActivityOut:
    """Listening beats speaking, then thinking, working (delegated tasks), sleeping (quiet hours), idle.
    The journal's stream sends the same as `event: activity` on every change."""
    return AgentActivityOut.of(state(request).nestor.activity.current())


@router.get("/agent/initiative")
async def get_agent_initiative(request: Request, caller: Reader) -> InitiativeOut:
    nestor = state(request).nestor
    policy, activity = nestor.courier.policy, nestor.activity.current()
    quiet = policy.quiet_hours
    people = People(nestor.household)
    everyone = caller.principal.can(Scope.JOURNAL_READ_ALL)
    upcoming = []
    for follow_up in nestor.courier.scheduled():
        if not everyone and (caller.person is None or follow_up.person != caller.person):
            continue
        about = subject(follow_up.about)
        upcoming.append(
            ScheduledDeliveryOut(
                about=follow_up.about,
                delivery=about["about"] if about["subject"] == "other" else f"{about['subject']}:{about['id']}",
                person=people.ref(follow_up.person),
                spoken_on=str(follow_up.spoken),
                written_on=str(follow_up.written),
                due_at=follow_up.due_at,
            )
        )
    return InitiativeOut(
        quiet_hours=QuietHoursOut(
            start=quiet.start.strftime("%H:%M"),
            end=quiet.end.strftime("%H:%M"),
            timezone=policy.timezone,
            active=activity.quiet,
        )
        if quiet
        else None,
        upcoming=upcoming,
    )
