"""The household's alerts, rebuilt from the journal: which are active, when each is next due, and why each rang."""

import asyncio
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, time

from nestor.core import Component, Day, PersonId, new_id, utc_now
from nestor.modules.channels import Exchange
from nestor.modules.initiative.alerts.events import AlertCreated, AlertEnded, AlertRang
from nestor.modules.initiative.alerts.ports import InboundEventSource
from nestor.modules.initiative.alerts.types import Alert, AlertEnd, Incoming, Ring, RingCause, Trigger
from nestor.modules.journal import Journal

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
RECENT = 10  # the last rings of each alert kept to say why it rang


class AlertBook(Component):
    """The only writer of alert events. An alert due while Nestor was stopped rings once when it is back, however many
    times it was due meanwhile, then follows its times again."""

    name = "alert-book"

    def __init__(
        self,
        journal: Journal,
        sources: Iterable[InboundEventSource] = (),
        *,
        timezone: str = "UTC",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.journal, self.timezone, self.clock = journal, timezone, clock
        sources = tuple(sources)
        # what the connected sources can bring, each kind with what they follow under it by name
        self.kinds: dict[str, tuple[str, ...]] = {}
        for source in sources:
            for kind in source.kinds:
                self.kinds[kind] = (*self.kinds.get(kind, ()), *source.follows.get(kind, ()))
        # kinds whose every source says exactly what happened: they ring without the triage model
        self.structured = frozenset(
            kind for kind in self.kinds if all(s.structured for s in sources if kind in s.kinds)
        )
        self.alerts: dict[str, Alert] = {}
        self.rings: dict[str, list[Ring]] = {}  # of each active alert, the last ones, oldest first
        self.rang: Counter[str] = Counter()  # how many times each active alert rang
        self._since: dict[str, datetime] = {}  # when each was created or last rang: it is next due after
        self.changed = asyncio.Event()  # set on every change, for whoever waits for the next one

    async def start(self) -> None:
        for event in await self.journal.history(AlertCreated, AlertRang, AlertEnded):
            self._take(event)
        await self.settle()

    async def create(self, alert: Alert, *, exchange: Exchange | None = None) -> Alert:
        event = AlertCreated(
            source=self.name,
            at=self.clock(),
            session=alert.created_in.session if alert.created_in else None,
            alert_id=alert.id,
            title=alert.title,
            instruction=alert.instruction,
            at_moment=alert.at,
            times=tuple(t.strftime("%H:%M") for t in sorted(alert.times)),
            days=alert.days,
            kinds=alert.kinds,
            condition=alert.condition,
            frequency=alert.frequency,
            until=alert.until,
            urgent=alert.urgent,
            owner=alert.owner,
            created_in=alert.created_in,
            exchange=exchange,
        )
        await self.journal.publish(event)
        self._take(event)
        return self.alerts[alert.id]

    async def ring(
        self,
        alert: Alert,
        cause: RingCause,
        *,
        due_at: datetime | None = None,
        item: Incoming | None = None,
        summary: str = "",
    ) -> Ring:
        event = AlertRang(
            source=self.name,
            at=self.clock(),
            alert_id=alert.id,
            ring_id=new_id()[:8],
            cause=cause,
            due_at=due_at,
            item_id=item.id if item else None,
            item_title=item.title if item else None,
            item_kind=item.kind if item else None,
            item_source=item.source if item else None,
            summary=summary,
        )
        await self.journal.publish(event)
        self._take(event)
        return _ring(event)

    async def end(self, alert_id: str, reason: AlertEnd, *, by: PersonId | None = None) -> bool:
        if alert_id not in self.alerts:
            return False
        event = AlertEnded(source=self.name, at=self.clock(), alert_id=alert_id, reason=reason, by=by)
        await self.journal.publish(event)
        self._take(event)
        return True

    async def settle(self) -> None:
        """End what can no longer ring: alerts whose `until` passed, and moments already rung."""
        now = self.clock()
        for alert in tuple(self.alerts.values()):
            if alert.until is not None and alert.until <= now:
                await self.end(alert.id, AlertEnd.EXPIRED)
            elif alert.trigger is not Trigger.EVENTS and self.next_due(alert) is None:
                await self.end(alert.id, AlertEnd.DONE)

    def next_due(self, alert: Alert) -> datetime | None:
        return alert.next_due(self._since[alert.id], self.timezone)

    def due(self) -> list[tuple[Alert, datetime]]:
        """The alerts whose time has come, with the time each was due."""
        now = self.clock()
        return [(a, due) for a in self.alerts.values() if (due := self.next_due(a)) is not None and due <= now]

    def wakes(self) -> list[datetime]:
        """When something next changes on the clock: an alert due, or one whose `until` passes."""
        return [
            moment
            for alert in self.alerts.values()
            for moment in (self.next_due(alert), alert.until)
            if moment is not None
        ]

    def upcoming(self) -> list[Alert]:
        """Every alert, soonest due first; those that wait for items after, newest first."""
        due = {a.id: self.next_due(a) for a in self.alerts.values()}
        newest = sorted(self.alerts.values(), key=lambda a: a.created_at, reverse=True)
        return sorted(newest, key=lambda a: (due[a.id] is None, due[a.id] or EPOCH))

    def _take(self, event: object) -> None:
        if isinstance(event, AlertCreated):
            self.alerts[event.alert_id] = _alert(event)
            self._since[event.alert_id] = event.at  # the event's time: due from its creation on
        elif isinstance(event, AlertRang) and (alert := self.alerts.get(event.alert_id)):
            if event.due_at is not None:
                self._since[alert.id] = max(event.due_at, event.at)
            self.rang[alert.id] += 1
            self.rings[alert.id] = [*self.rings.get(alert.id, ()), _ring(event)][-RECENT:]
        elif isinstance(event, AlertEnded):
            self.alerts.pop(event.alert_id, None)
            self._since.pop(event.alert_id, None)
            self.rings.pop(event.alert_id, None)
            self.rang.pop(event.alert_id, None)
        self.changed.set()


def _alert(event: AlertCreated) -> Alert:
    return Alert(
        id=event.alert_id,
        title=event.title,
        instruction=event.instruction,
        at=event.at_moment,
        times=tuple(time.fromisoformat(t) for t in event.times),
        days=tuple(Day(d) for d in event.days),
        kinds=event.kinds,
        condition=event.condition,
        frequency=event.frequency,
        until=event.until,
        urgent=event.urgent,
        owner=event.owner,
        created_in=event.created_in,
        created_at=event.at,
    )


def _ring(event: AlertRang) -> Ring:
    return Ring(
        id=event.ring_id,
        at=event.at,
        cause=event.cause,
        due_at=event.due_at,
        item_id=event.item_id,
        item_title=event.item_title,
        item_kind=event.item_kind,
        item_source=event.item_source,
        summary=event.summary,
    )
