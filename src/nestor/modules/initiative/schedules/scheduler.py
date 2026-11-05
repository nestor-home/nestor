"""Wakes the agent when a schedule is due: it runs the instruction as a background turn, with its tools."""

import asyncio
import contextlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from nestor.core import Component
from nestor.modules.channels import Address
from nestor.modules.conversation import Agent, Notification
from nestor.modules.household import Household
from nestor.modules.initiative.schedules.book import ScheduleBook
from nestor.modules.initiative.schedules.types import Schedule

log = logging.getLogger("nestor.schedules")
IDLE_S = 3600.0  # the longest sleep between two looks at the clock, against drift and clock changes


class Scheduler(Component):
    name = "scheduler"

    def __init__(self, book: ScheduleBook, agent: Agent, household: Household) -> None:
        self.book, self.agent, self.household = book, agent, household
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
            try:
                await self.agent.background(
                    schedule.created_in or Address("schedule", schedule.id),
                    self.household.person(schedule.owner) if schedule.owner else None,
                    Notification(self._instruction(schedule, due_at), f"schedule {schedule.id}"),
                )
            except Exception:  # one wake-up failing never stops the others
                log.exception("wake-up %s failed", schedule.id)
        return len(due)

    def _instruction(self, schedule: Schedule, due_at: datetime) -> str:
        local = due_at.astimezone(ZoneInfo(self.book.timezone))
        owner = self.household.person(schedule.owner).name if schedule.owner else None
        whose = f", set for {owner}" if owner else ""
        return (
            f"A wake-up you scheduled{whose} is due now ({local:%A %H:%M}): {schedule.instruction}\n"
            "Nobody reads what you write here: do it with your tools, and to tell someone, use message_person."
        )

    async def _run(self) -> None:
        while True:
            self.book.changed.clear()
            await self.wake_due()
            upcoming = [d for s in self.book.schedules.values() if (d := self.book.next_due(s)) is not None]
            wait = min([(min(upcoming) - self.book.clock()).total_seconds(), IDLE_S] if upcoming else [IDLE_S])
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.book.changed.wait(), timeout=max(wait, 0.0))
