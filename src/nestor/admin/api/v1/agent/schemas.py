"""When the agent speaks up on its own: its quiet hours and the follow-ups it has scheduled."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.admin.presentation import subject
from nestor.modules.initiative import DeliveryPolicy, FollowUp


class QuietHoursOut(BaseModel):
    start: str  # "22:30", the household's local time
    end: str  # "07:30"; earlier than `start` when the quiet hours cross midnight
    timezone: str  # the household's (`persona.timezone`)
    active: bool  # within them now

    @classmethod
    def of(cls, policy: DeliveryPolicy, *, active: bool) -> "QuietHoursOut | None":
        quiet = policy.quiet_hours
        if quiet is None:
            return None
        return cls(
            start=quiet.start.strftime("%H:%M"),
            end=quiet.end.strftime("%H:%M"),
            timezone=policy.timezone,
            active=active,
        )


class ScheduledDeliveryOut(BaseModel):
    """A written follow-up of something said aloud: sent at `due_at` unless someone answers first."""

    about: str  # as journaled: `task 3f2a completed`, `watch w1`
    delivery: str  # the thread it belongs to, as the journal's `links.delivery` (`watch:w1`, `task:3f2a`)
    person: PersonRef | None
    spoken_on: str  # where it was said (`voice:salon`)
    written_on: str  # where it will be written (`telegram:7`)
    due_at: datetime

    @classmethod
    def of(cls, follow_up: FollowUp, people: People) -> "ScheduledDeliveryOut":
        about = subject(follow_up.about)
        return cls(
            about=follow_up.about,
            delivery=about["about"] if about["subject"] == "other" else f"{about['subject']}:{about['id']}",
            person=people.ref(follow_up.person),
            spoken_on=str(follow_up.spoken),
            written_on=str(follow_up.written),
            due_at=follow_up.due_at,
        )


class InitiativeOut(BaseModel):
    quiet_hours: QuietHoursOut | None  # None: the agent may speak up at any hour
    upcoming: list[ScheduledDeliveryOut]  # soonest first; with `journal.read.own` only, those for one's person
