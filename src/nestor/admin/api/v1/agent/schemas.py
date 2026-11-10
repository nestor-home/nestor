"""When the agent speaks up on its own: its quiet hours and the follow-ups it has scheduled."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import People, PersonRef
from nestor.core import Health
from nestor.modules.activity import Activity, AgentActivity
from nestor.modules.initiative import DeliveryPolicy, FollowUp
from nestor.runtime import Nestor


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

    delivery: str  # the thread it belongs to, as the journal's `links.delivery` (`watch:w1`, `task:3f2a`)
    person: PersonRef | None
    spoken_on: str  # where it was said (`voice:salon`)
    written_on: str  # where it will be written (`telegram:7`)
    due_at: datetime

    @classmethod
    def of(cls, follow_up: FollowUp, people: People) -> "ScheduledDeliveryOut":
        return cls(
            delivery=follow_up.about.key,
            person=people.ref(follow_up.person),
            spoken_on=str(follow_up.spoken),
            written_on=str(follow_up.written),
            due_at=follow_up.due_at,
        )


class InitiativeOut(BaseModel):
    quiet_hours: QuietHoursOut | None  # None: the agent may speak up at any hour
    upcoming: list[ScheduledDeliveryOut]  # soonest first; with `journal.read.own` only, those for one's person


class AgentOut(BaseModel):
    """The assistant itself, as the front's sidebar shows it."""

    name: str  # the persona's name ("Richie")
    status: Health  # started, or degraded when its model or one of its channels cannot serve now

    @classmethod
    def of(cls, nestor: Nestor) -> "AgentOut":
        required = [*nestor.agent.models.distinct(), *nestor.channels]
        degraded = any(c.health() is not Health.STARTED for c in required)
        return cls(name=nestor.config.persona.name, status=Health.DEGRADED if degraded else Health.STARTED)


class AgentActivityOut(BaseModel):
    """What the agent is doing now, from what really runs: `GET /agent/activity`, and `event: activity` on
    the journal's stream at its start and on every change."""

    state: Activity
    since: datetime  # when it entered this state (as this instance saw it: its start at the earliest)
    replies: int  # answers being produced now
    tasks: int  # delegated tasks running
    listening_rooms: list[str]  # where a satellite hears someone speak
    quiet: bool  # within the quiet hours now

    @classmethod
    def of(cls, activity: AgentActivity) -> "AgentActivityOut":
        return cls(
            state=activity.state,
            since=activity.since,
            replies=activity.replies,
            tasks=activity.tasks,
            listening_rooms=list(activity.listening_rooms),
            quiet=activity.quiet,
        )
