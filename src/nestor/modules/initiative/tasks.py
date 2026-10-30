"""Announces the outcome of delegated tasks to whoever asked, once, even across restarts."""

import asyncio
import contextlib

from nestor.core import Component
from nestor.modules.cognition.delegation import Notify, TaskDelivered, TaskEnded, TaskStarted, TaskStatus
from nestor.modules.household import Household, Person
from nestor.modules.initiative.delivery import Courier
from nestor.modules.journal import Journal, Subscription


class TaskAnnouncer(Component):
    """Listens for ended tasks and has the courier deliver them. On start it also delivers the ones
    that ended while nobody was listening (crash between the end and the delivery)."""

    name = "task-announcer"

    def __init__(self, journal: Journal, household: Household, courier: Courier) -> None:
        self.journal, self.household, self.courier = journal, household, courier
        self._subscription: Subscription | None = None
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._subscription = self.journal.subscribe(TaskEnded)
        delivered = {e.task_id for e in await self.journal.history(TaskDelivered)}
        for ended in await self.journal.history(TaskEnded):
            if ended.task_id not in delivered:
                await self.announce(ended)
        self._worker = asyncio.create_task(self._listen(self._subscription), name="task announcer")

    async def close(self) -> None:
        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None
        if self._worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def announce(self, ended: TaskEnded) -> None:
        if ended.status is TaskStatus.CANCELLED:
            return  # the person cancelled it and was told so
        started = next(e for e in await self.journal.history(TaskStarted) if e.task_id == ended.task_id)
        person = self.household.person(started.requested_by) if started.requested_by else None
        written = started.notify is Notify.MESSAGE
        address = await self.courier.deliver(
            person,
            _instruction(started, ended, person, written=written),
            about=f"task {ended.task_id} {ended.status.value}",
            origin=started.origin,
            written=written,
        )
        if address is not None:
            await self.journal.publish(
                TaskDelivered(source=self.name, session=address.session, task_id=ended.task_id, address=address)
            )

    async def _listen(self, subscription: Subscription) -> None:
        async for event in subscription:
            if isinstance(event, TaskEnded):
                await self.announce(event)


def _instruction(started: TaskStarted, ended: TaskEnded, person: Person | None, *, written: bool) -> str:
    outcome = f"Result: {ended.result}" if ended.status is TaskStatus.COMPLETED else f"Failure: {ended.error}"
    who = person.name if person else "the person"
    asked = " (they asked for it in writing)" if written else ""
    return (
        f"A task you delegated has ended ({ended.status.value}).\nObjective: {started.objective}\n{outcome}\n"
        f"Tell {who} now, unprompted and briefly, in your own words{asked}. Do not mention internal identifiers."
    )
