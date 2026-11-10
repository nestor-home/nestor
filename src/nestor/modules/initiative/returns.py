"""What comes back to a conversation by itself, as a tool's result comes back to a model: a delegated task that ended,
a tool call that went on in the background. Each is delivered once to whoever asked, even across restarts."""

import asyncio
import contextlib
import json

from nestor.core import Component, Event, PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.delegation import Notify, TaskDelivered, TaskEnded, TaskStarted, TaskStatus
from nestor.modules.cognition.tools import ToolDeferred, ToolReturned
from nestor.modules.conversation import About, Notification, Source
from nestor.modules.household import Household, Person
from nestor.modules.initiative.delivery.courier import Courier
from nestor.modules.journal import Journal, Subscription

INTERRUPTED = json.dumps({"error": "Nestor restarted before it answered: it did not finish"})


class ToolResultDelivered(Event, event_type="agent.tool.result-delivered"):
    """The result of a deferred call reached whoever asked, at `address`."""

    call_id: str
    tool: str
    address: Address


class Returns(Component):
    """Listens for ended tasks and for the results of deferred calls, and has the courier deliver them to the
    conversation they came from. On start it also delivers those that came back while nobody was listening, and says
    which calls a restart cut short."""

    name = "returns"

    def __init__(self, journal: Journal, household: Household, courier: Courier) -> None:
        self.journal, self.household, self.courier = journal, household, courier
        self._subscription: Subscription | None = None
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._subscription = self.journal.subscribe(TaskEnded, ToolReturned)
        delivered = {e.task_id for e in await self.journal.history(TaskDelivered)}
        for ended in await self.journal.history(TaskEnded):
            if ended.task_id not in delivered:
                await self.task_ended(ended)
        returned = {e.call_id: e for e in await self.journal.history(ToolReturned)}
        told = {e.call_id for e in await self.journal.history(ToolResultDelivered)}
        for deferred in await self.journal.history(ToolDeferred):
            if deferred.call_id in told:
                continue
            if (result := returned.get(deferred.call_id)) is not None:
                await self.tool_returned(result)
            else:  # it ran in the process that stopped: it never will
                await self.journal.publish(
                    ToolReturned(
                        source=self.name,
                        session=deferred.session,
                        call_id=deferred.call_id,
                        name=deferred.name,
                        output=INTERRUPTED,
                        ok=False,
                        duration_s=0.0,
                        exchange=deferred.exchange,
                    )
                )  # delivered as it comes back through the subscription
        self._worker = asyncio.create_task(self._listen(self._subscription), name="returns")

    async def close(self) -> None:
        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None
        if self._worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def task_ended(self, ended: TaskEnded) -> None:
        if ended.status is TaskStatus.CANCELLED:
            return  # the person cancelled it and was told so
        started = next(e for e in await self.journal.history(TaskStarted) if e.task_id == ended.task_id)
        person = self._person(started.requested_by)
        written = started.notify is Notify.MESSAGE
        address = await self.courier.deliver(
            person,
            Notification(
                _task_instruction(started, ended, written=written),
                About(Source.TASK, ended.task_id, ended.status.value),
            ),
            origin=started.origin,
            written=written,
        )
        if address is not None:
            await self.journal.publish(
                TaskDelivered(source=self.name, session=address.session, task_id=ended.task_id, address=address)
            )

    async def tool_returned(self, returned: ToolReturned) -> None:
        calls = await self.journal.history(ToolDeferred, session=returned.session)
        deferred = next((e for e in calls if e.call_id == returned.call_id), None)
        if deferred is None:
            return  # a call that answered in its turn
        person = self._person(deferred.person)
        status = "returned" if returned.ok else "failed"
        address = await self.courier.deliver(
            person,
            Notification(_tool_instruction(deferred, returned), About(Source.TOOL, returned.call_id, status)),
            origin=deferred.address,
        )
        if address is not None:
            await self.journal.publish(
                ToolResultDelivered(
                    source=self.name,
                    session=address.session,
                    call_id=returned.call_id,
                    tool=returned.name,
                    address=address,
                )
            )

    def _person(self, person: PersonId | None) -> Person | None:
        return self.household.person(person) if person else None

    async def _listen(self, subscription: Subscription) -> None:
        async for event in subscription:
            if isinstance(event, TaskEnded):
                await self.task_ended(event)
            elif isinstance(event, ToolReturned):
                await self.tool_returned(event)


def _task_instruction(started: TaskStarted, ended: TaskEnded, *, written: bool) -> str:
    outcome = f"Result: {ended.result}" if ended.status is TaskStatus.COMPLETED else f"Failure: {ended.error}"
    asked = "\nThey asked for it in writing." if written else ""
    return f"A task you delegated has ended ({ended.status.value}).\nObjective: {started.objective}\n{outcome}{asked}"


def _tool_instruction(deferred: ToolDeferred, returned: ToolReturned) -> str:
    arguments = json.dumps(dict(deferred.arguments), ensure_ascii=False, default=str)
    outcome = f"Result: {returned.output}" if returned.ok else f"Failure: {returned.output}"
    return (
        f"A tool you called earlier was still running; it has now {'answered' if returned.ok else 'failed'}.\n"
        f"Call: {deferred.name} {arguments}\n{outcome}\nTell them what it means for what they asked."
    )
