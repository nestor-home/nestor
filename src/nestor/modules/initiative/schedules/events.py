"""Events of wake-ups: created, fired (once per time it was due, before it runs), cancelled."""

from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange


class ScheduleCreated(Event, event_type="schedule.created"):
    """`once_at` for once; else `times` ("08:00") on `days` (every day when empty), in the household's clock."""

    schedule_id: str
    instruction: str
    owner: PersonId | None = None
    created_in: Address | None = None
    once_at: datetime | None = None
    times: tuple[str, ...] = ()
    days: tuple[str, ...] = ()
    exchange: Exchange | None = None


class ScheduleFired(Event, event_type="schedule.fired"):
    """Written before the agent runs it: a crash midway never runs it twice."""

    schedule_id: str
    due_at: datetime


class ScheduleCancelled(Event, event_type="schedule.cancelled"):
    schedule_id: str
    by: PersonId | None = None
