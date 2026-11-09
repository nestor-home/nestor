"""The household's wake-ups, rebuilt from the journal: which are active, and when each is next due."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, time

from nestor.core import Component, PersonId, new_id, utc_now
from nestor.modules.channels import Address, Exchange
from nestor.modules.initiative.schedules.events import ScheduleCancelled, ScheduleCreated, ScheduleFired
from nestor.modules.initiative.schedules.types import Day, Schedule
from nestor.modules.journal import Journal

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ScheduleBook(Component):
    """The only writer of schedule events. A wake-up missed while Nestor was stopped fires once when it
    is back, however many times it was due meanwhile, then follows its times again."""

    name = "schedule-book"

    def __init__(self, journal: Journal, timezone: str = "UTC", *, clock: Callable[[], datetime] = utc_now) -> None:
        self.journal, self.timezone, self.clock = journal, timezone, clock
        self.schedules: dict[str, Schedule] = {}
        self._since: dict[str, datetime] = {}  # when each was created or last fired: it is next due after
        self.changed = asyncio.Event()  # set on every change, for whoever waits for the next one

    async def start(self) -> None:
        for event in await self.journal.history(ScheduleCreated, ScheduleFired, ScheduleCancelled):
            self._take(event)

    async def create(
        self,
        instruction: str,
        *,
        owner: PersonId | None,
        created_in: Address | None = None,
        at: datetime | None = None,
        times: tuple[time, ...] = (),
        days: tuple[Day, ...] = (),
        exchange: Exchange | None = None,
    ) -> Schedule:
        schedule = Schedule(
            id=new_id(), instruction=instruction, owner=owner, created_in=created_in, at=at, times=times, days=days
        )  # validated before anything is written
        event = ScheduleCreated(
            source=self.name,
            at=self.clock(),
            session=created_in.session if created_in else None,
            schedule_id=schedule.id,
            instruction=instruction,
            owner=owner,
            created_in=created_in,
            once_at=at,
            times=tuple(t.strftime("%H:%M") for t in sorted(times)),
            days=days,
            exchange=exchange,
        )
        await self.journal.publish(event)
        self._take(event)
        return self.schedules[schedule.id]

    async def cancel(self, schedule_id: str, *, by: PersonId | None) -> None:
        event = ScheduleCancelled(source=self.name, at=self.clock(), schedule_id=schedule_id, by=by)
        await self.journal.publish(event)
        self._take(event)

    async def fired(self, schedule_id: str, due_at: datetime) -> None:
        event = ScheduleFired(source=self.name, at=self.clock(), schedule_id=schedule_id, due_at=due_at)
        await self.journal.publish(event)
        self._take(event)

    def upcoming(self) -> list[Schedule]:
        """Every wake-up, soonest due first; one-offs already past last."""
        due = {s.id: self.next_due(s) for s in self.schedules.values()}
        return sorted(self.schedules.values(), key=lambda s: (due[s.id] is None, due[s.id] or s.at or EPOCH))

    def next_due(self, schedule: Schedule) -> datetime | None:
        return schedule.next_due(self._since[schedule.id], self.timezone)

    def due(self) -> list[tuple[Schedule, datetime]]:
        """The wake-ups due now, with the time each was due."""
        now = self.clock()
        return [(s, due) for s in self.schedules.values() if (due := self.next_due(s)) is not None and due <= now]

    def _take(self, event: object) -> None:
        if isinstance(event, ScheduleCreated):
            self.schedules[event.schedule_id] = Schedule(
                id=event.schedule_id,
                instruction=event.instruction,
                owner=event.owner,
                created_in=event.created_in,
                at=event.once_at,
                times=tuple(time.fromisoformat(t) for t in event.times),
                days=tuple(Day(d) for d in event.days),
            )
            self._since[event.schedule_id] = event.at  # the event's time: due from its creation on
        elif isinstance(event, ScheduleFired) and (schedule := self.schedules.get(event.schedule_id)):
            if schedule.recurring:
                self._since[schedule.id] = max(event.due_at, event.at)
            else:
                self._drop(schedule.id)
        elif isinstance(event, ScheduleCancelled):
            self._drop(event.schedule_id)
        self.changed.set()

    def _drop(self, schedule_id: str) -> None:
        self.schedules.pop(schedule_id, None)
        self._since.pop(schedule_id, None)
