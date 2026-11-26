"""An alert as the admin shows it: what rings it, what the agent does then, for whom, and why it rang."""

from datetime import datetime

from pydantic import BaseModel

from nestor.admin.api.v1.shared import OriginOut, People, PersonRef
from nestor.core import Day
from nestor.modules.initiative import Alert, AlertBook, Frequency, Ring, RingCause, Trigger


class RingOut(BaseModel):
    """One time it rang, and why: its time came (`due_at`), an event arrived, or an item matched (`summary` says
    how)."""

    at: datetime
    cause: RingCause
    due_at: datetime | None
    item_title: str | None
    item_kind: str | None
    summary: str

    @classmethod
    def of(cls, ring: Ring) -> "RingOut":
        return cls(
            at=ring.at,
            cause=ring.cause,
            due_at=ring.due_at,
            item_title=ring.item_title,
            item_kind=ring.item_kind,
            summary=ring.summary,
        )


class AlertOut(BaseModel):
    id: str
    title: str  # the short name the agent gave it
    instruction: str  # what the agent does when it rings, in its own words
    condition: str | None  # what must hold to tell, in the person's words
    trigger: Trigger
    at: datetime | None  # `at`: its moment
    times: list[str]  # `times`: its times of day, "HH:MM" in the household's clock
    days: list[Day]  # `times`: its days; empty: every day
    kinds: list[str]  # `events`: the kinds of items it waits for ("mail", "dishwasher")
    frequency: Frequency
    until: datetime | None  # it ends then at the latest
    urgent: bool  # told at once, even in quiet hours
    owner: PersonRef | None  # whoever set it: what it finds reaches them
    origin: OriginOut | None  # where it was set
    created_at: datetime
    next_due: datetime | None  # when its time next comes; None for items
    rang: int  # how many times it rang so far
    rings: list[RingOut]  # the last times it rang, newest first

    @classmethod
    def of(cls, alert: Alert, book: AlertBook, people: People) -> "AlertOut":
        origin = alert.created_in
        return cls(
            id=alert.id,
            title=alert.title,
            instruction=alert.instruction,
            condition=alert.condition,
            trigger=alert.trigger,
            at=alert.at,
            times=[t.strftime("%H:%M") for t in sorted(alert.times)],
            days=list(alert.days),
            kinds=list(alert.kinds),
            frequency=alert.frequency,
            until=alert.until,
            urgent=alert.urgent,
            owner=people.ref(alert.owner),
            origin=OriginOut.of(origin) if origin else None,
            created_at=alert.created_at,
            next_due=book.next_due(alert),
            rang=book.rang[alert.id],
            rings=[RingOut.of(r) for r in reversed(book.rings.get(alert.id, ()))],
        )


class AlertsOut(BaseModel):
    alerts: list[AlertOut]  # soonest due first, then those that wait for items, newest first
    kinds: list[str]  # what the plugged sources can bring; empty: alerts ring only at times
    timezone: str  # the household's clock, which `times` are in
