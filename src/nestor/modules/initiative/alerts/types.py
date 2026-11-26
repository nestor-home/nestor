"""Alerts and what rings them: a time, a rhythm, or items arriving from outside (a mail, a webhook's event)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from nestor.core import ContractError, Day, PersonId, new_id, utc_now
from nestor.modules.channels import Address


@dataclass(frozen=True, slots=True, kw_only=True)
class Incoming:
    """Something that arrived from outside. Its text is data, never instructions; `data` is what a structured source
    (a webhook) brought, parsed."""

    source: str  # the connection or source it came through: "gmail-mathis", "webhook"
    kind: str  # "mail", "feed", or a webhook's own kind: "dishwasher"
    title: str
    body: str = ""
    sender: str | None = None
    owner: PersonId | None = None  # whose mailbox or account it came to
    data: Mapping[str, object] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    at: datetime = field(default_factory=utc_now)


class Trigger(StrEnum):
    """What rings an alert."""

    AT = "at"  # once, at a moment
    TIMES = "times"  # at times of day, on some days
    EVENTS = "events"  # items of some kinds arriving


class Frequency(StrEnum):
    """How often an alert rings before it ends by itself (`until` may end it earlier)."""

    ONCE = "once"  # ends when it rings
    EVERY_TIME = "every_time"  # rings each time, until cancelled or `until`
    UNTIL_RUNG = "until_rung"  # rings each time until something was told: a check that found nothing goes on


class AlertEnd(StrEnum):
    """Why an alert ended."""

    RANG = "rang"  # it rang (once), or something was told (until rung)
    CANCELLED = "cancelled"
    EXPIRED = "expired"  # its `until` passed
    DONE = "done"  # nothing can ring it anymore: a moment that passed


class RingCause(StrEnum):
    """What made an alert ring."""

    DUE = "due"  # its time came
    EVENT = "event"  # an item of a kind it follows arrived, which says exactly what happened (a webhook's event)
    MATCH = "match"  # the triage model read an item as what it waits for, or its condition as met


@dataclass(frozen=True, slots=True, kw_only=True)
class Alert:
    """A durable commitment: when its trigger fires (a moment `at`, `times` on `days`, or an item of `kinds`), and its
    `condition` holds if it has one, Nestor follows `instruction` for `owner`. `urgent` is set once, at creation."""

    title: str  # the short name the household knows it by: "Colis de la poussette"
    instruction: str  # what Nestor does when it rings, in its words: "tell Mathis the parcel arrived"
    at: datetime | None = None  # aware
    times: tuple[time, ...] = ()  # in the household's clock
    days: tuple[Day, ...] = ()  # every day when empty
    kinds: tuple[str, ...] = ()
    condition: str | None = None  # in plain language: "the price is under 135 $"
    frequency: Frequency = Frequency.ONCE
    until: datetime | None = None
    urgent: bool = False
    owner: PersonId | None = None
    created_in: Address | None = None
    id: str = field(default_factory=lambda: new_id()[:8])
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if sum((self.at is not None, bool(self.times), bool(self.kinds))) != 1:
            raise ContractError("an alert rings at a moment (`at`), at `times`, or on `kinds` of items: exactly one")
        if self.days and not self.times:
            raise ContractError("`days` go with `times`")

    @property
    def trigger(self) -> Trigger:
        return Trigger.AT if self.at is not None else Trigger.TIMES if self.times else Trigger.EVENTS

    def next_due(self, after: datetime, timezone: str) -> datetime | None:
        """The first time it is due strictly after `after` (aware); `None` for items, and once a moment has passed."""
        if self.at is not None:
            return self.at if self.at > after else None
        if not self.times:
            return None
        zone = ZoneInfo(timezone)
        local = after.astimezone(zone)
        for offset in range(8):
            day = local.date() + timedelta(days=offset)
            if self.days and list(Day)[day.weekday()] not in self.days:
                continue
            for moment in sorted(self.times):
                due = datetime.combine(day, moment, tzinfo=zone)
                if due > after:
                    return due
        return None


@dataclass(frozen=True, slots=True, kw_only=True)
class Ring:
    """One time an alert rang, and why: its time came (`due_at`), or an item arrived (`item_*`), read by the triage
    model as what it waits for when `cause` is a match (`summary` says how)."""

    id: str
    at: datetime
    cause: RingCause
    due_at: datetime | None = None
    item_id: str | None = None
    item_title: str | None = None
    item_kind: str | None = None
    item_source: str | None = None
    summary: str = ""

    def why(self, timezone: str) -> str:
        """The reason, in English, for the model."""
        if self.cause is RingCause.DUE and self.due_at is not None:
            return f"it was due at {self.due_at.astimezone(ZoneInfo(timezone)):%A %d %B %H:%M}"
        if self.cause is RingCause.EVENT:
            return f"an event of kind {self.item_kind} arrived from {self.item_source}: {self.item_title}"
        return f"“{self.item_title}” ({self.item_kind}) matched: {self.summary or 'what it waits for'}"
