"""Events of alerts: created, an item sorted against them, rung (before Nestor follows it, with why), ended (with
why)."""

from datetime import datetime, time

from nestor.core import Day, Event, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.initiative.alerts.types import Alert, AlertEnd, Frequency, RingCause


class AlertCreated(Event, event_type="alert.created"):
    """Its trigger is `at`, else `times` ("08:00", household's clock) on `days` (every day when empty), else `kinds`.
    `exchange` is the conversation and turn that asked for it, when one did."""

    alert_id: str
    title: str  # the short name the household knows it by
    instruction: str
    at_moment: datetime | None = None
    times: tuple[str, ...] = ()
    days: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    condition: str | None = None
    frequency: Frequency = Frequency.ONCE
    until: datetime | None = None
    urgent: bool = False
    owner: PersonId | None = None
    created_in: Address | None = None
    exchange: Exchange | None = None

    @property
    def alert(self) -> Alert:
        return Alert(
            id=self.alert_id,
            title=self.title,
            instruction=self.instruction,
            at=self.at_moment,
            times=tuple(time.fromisoformat(t) for t in self.times),
            days=tuple(Day(d) for d in self.days),
            kinds=self.kinds,
            condition=self.condition,
            frequency=self.frequency,
            until=self.until,
            urgent=self.urgent,
            owner=self.owner,
            created_in=self.created_in,
            created_at=self.at,
        )


class AlertSorted(Event, event_type="alert.sorted"):
    """An item read by the triage model against the alerts it may concern: those it matched, or none when it stayed
    unsorted (the model could not be reached or read: nothing rings). `item_source` is what brought the item: a
    connection's id, or a source's name."""

    item_id: str
    item_title: str
    item_source: str
    asked: tuple[str, ...]
    matched: tuple[str, ...] = ()
    unsorted: bool = False


class AlertRang(Event, event_type="alert.rang"):
    """Written before Nestor follows it, so that a crash midway never rings it twice. Why: its time came (`due_at`),
    an event of a kind it follows arrived, or the triage model matched an item (`summary` says how); `item_source` as
    in `AlertSorted`."""

    alert_id: str
    ring_id: str
    cause: RingCause
    due_at: datetime | None = None
    item_id: str | None = None
    item_title: str | None = None
    item_kind: str | None = None
    item_source: str | None = None
    summary: str = ""


class AlertEnded(Event, event_type="alert.ended"):
    """`by` is who cancelled it, when someone did."""

    alert_id: str
    reason: AlertEnd
    by: PersonId | None = None
