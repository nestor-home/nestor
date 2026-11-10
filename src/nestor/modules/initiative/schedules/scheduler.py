"""Wakes the agent when a schedule is due: the instruction is a notification for whoever set it, which the courier
delivers like a task's result. The agent does what it asks with its tools and tells them what they need to know, or
nothing (a check that found nothing)."""

import asyncio
import contextlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.core import Component
from nestor.modules.conversation import About, Notification, Source
from nestor.modules.household import Household, Person
from nestor.modules.initiative.delivery import Courier
from nestor.modules.initiative.schedules.book import ScheduleBook
from nestor.modules.initiative.schedules.types import Schedule

log = logging.getLogger("nestor.schedules")
IDLE_S = 3600.0  # the longest sleep between two looks at the clock, against drift and clock changes


class Scheduler(Component):
    name = "scheduler"

    def __init__(self, book: ScheduleBook, household: Household, courier: Courier) -> None:
        self.book, self.household, self.courier = book, household, courier
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._run(), name="scheduler")

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def wake_due(self) -> int:
        """Run every schedule due now, each once; returns how many ran."""
        due = self.book.due()
        for schedule, due_at in due:
            await self.book.fired(schedule.id, due_at)  # before it runs: never twice
            owner = self.household.person(schedule.owner) if schedule.owner else None
            notification = Notification(
                self._instruction(schedule, due_at, owner), About(Source.SCHEDULE, schedule.id), quiet=True
            )
            try:  # where it was set, or wherever its owner is reached; a delivery nothing took is journaled
                await self.courier.deliver(owner, notification, origin=schedule.created_in)
            except Exception:  # one wake-up failing never stops the others
                log.exception("wake-up %s failed", schedule.id)
        return len(due)

    def _instruction(self, schedule: Schedule, due_at: datetime, owner: Person | None) -> str:
        local = due_at.astimezone(ZoneInfo(self.book.timezone))
        whose = f" {owner.name} set" if owner else ""
        return f"A wake-up{whose} is due now ({local:%A %H:%M}): {schedule.instruction}"

    async def _run(self) -> None:
        while True:
            self.book.changed.clear()
            await self.wake_due()
            upcoming = [d for s in self.book.schedules.values() if (d := self.book.next_due(s)) is not None]
            wait = min([(min(upcoming) - self.book.clock()).total_seconds(), IDLE_S] if upcoming else [IDLE_S])
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.book.changed.wait(), timeout=max(wait, 0.0))
