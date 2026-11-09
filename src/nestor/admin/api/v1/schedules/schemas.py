"""A wake-up as the admin shows it: what the agent will do, for whom, when next."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import OriginOut, People, PersonRef
from nestor.modules.initiative import Day, Schedule, ScheduleBook


class ScheduleOut(BaseModel):
    id: str
    instruction: str  # what the agent does when it wakes, in its own words
    owner: PersonRef | None  # whoever set it: what it finds reaches them
    origin: OriginOut | None  # where it was set
    recurring: bool
    once_at: datetime | None  # a one-off's moment
    times: list[str]  # a recurring one's times of day, "HH:MM" in the household's clock
    days: list[Day]  # its days; empty: every day
    next_due: datetime | None  # None: a one-off already past

    @classmethod
    def of(cls, schedule: Schedule, book: ScheduleBook, people: People) -> "ScheduleOut":
        origin = schedule.created_in
        return cls(
            id=schedule.id,
            instruction=schedule.instruction,
            owner=people.ref(schedule.owner),
            origin=OriginOut(session=str(origin), channel=origin.channel) if origin else None,
            recurring=schedule.recurring,
            once_at=schedule.at,
            times=[t.strftime("%H:%M") for t in schedule.times],
            days=[Day(d) for d in schedule.days],
            next_due=book.next_due(schedule),
        )


class SchedulesOut(BaseModel):
    schedules: list[ScheduleOut]  # soonest first
    timezone: str  # the household's clock, which `times` are in
