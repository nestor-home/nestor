"""What comes back to a conversation by itself, as a tool's result comes back to a model: a turn of a delegated task
that ended (its report, its question, its failure), a tool call that went on in the background. Each is delivered once
to whoever asked, even across restarts; a question a task waits on is recalled a few times, then waits in the admin.

What a person asked for is always told, whatever it found: they wait for it. What Nestor started by itself (an alert
that delegates) may end in silence when there is nothing new; a failure and a question are always told."""

import asyncio
import contextlib
import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta

from nestor.core import Component, Event, PersonId, utc_now
from nestor.modules.channels import Address
from nestor.modules.cognition.delegation import (
    Notify,
    Task,
    TaskManager,
    TaskReminded,
    TurnEnded,
    TurnStatus,
)
from nestor.modules.cognition.tools import ToolDeferred, ToolReturned
from nestor.modules.conversation import About, Notification, Source
from nestor.modules.household import Household, Person
from nestor.modules.initiative.delivery.courier import Courier
from nestor.modules.initiative.delivery.events import DeliveryWithheld
from nestor.modules.journal import Journal, Subscription

INTERRUPTED = json.dumps({"error": "Nestor restarted before it answered: it did not finish"})
REMINDERS = (timedelta(hours=3), timedelta(hours=24), timedelta(hours=48))  # after a task asked; then it just waits
TICK_S = 60.0  # how often questions are looked at for a reminder


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

    def __init__(
        self,
        journal: Journal,
        household: Household,
        courier: Courier,
        tasks: TaskManager,
        *,
        reminders: Sequence[timedelta] = REMINDERS,
        tick_s: float = TICK_S,
    ) -> None:
        self.journal, self.household, self.courier, self.tasks = journal, household, courier, tasks
        self._reminders, self._tick_s = tuple(reminders), tick_s
        self._reminded: dict[str, int] = {}  # by turn: how many reminders of its question were given
        self._subscription: Subscription | None = None
        self._worker: asyncio.Task[None] | None = None
        self._recaller: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._subscription = self.journal.subscribe(TurnEnded, ToolReturned)
        past = await self.journal.history(
            DeliveryWithheld, TaskReminded, TurnEnded, ToolDeferred, ToolReturned, ToolResultDelivered
        )
        withheld = [e for e in past if isinstance(e, DeliveryWithheld)]  # nothing to tell: done too
        for event in past:
            if isinstance(event, TaskReminded):
                self._reminded[event.turn_id] = max(self._reminded.get(event.turn_id, 0), event.count)
        for ended in (e for e in past if isinstance(e, TurnEnded)):
            await self.turn_ended(ended)
        returned = {e.call_id: e for e in past if isinstance(e, ToolReturned)}
        told = {e.call_id for e in past if isinstance(e, ToolResultDelivered)}
        for deferred in (e for e in past if isinstance(e, ToolDeferred)):
            if deferred.call_id in told or _withheld(withheld, About(Source.TOOL, deferred.call_id)):
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
        self._recaller = asyncio.create_task(self._recall(), name="returns: questions")

    async def close(self) -> None:
        if self._recaller is not None:
            self._recaller.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recaller
            self._recaller = None
        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None
        if self._worker is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def turn_ended(self, ended: TurnEnded) -> None:
        """Tell the task's owner what its turn came back with (its report, its question, its failure) in the
        conversation the turn's instruction was given in. Once: never a turn already told or with nothing to tell (the
        same end may be read from the journal on start and heard live). A stopped turn is not told: whoever stopped it
        was told so."""
        task = self.tasks.tasks.get(ended.task_id)
        turn = task.turn_of(ended.turn_id) if task else None
        if ended.status is TurnStatus.STOPPED or task is None or turn is None or turn.delivered is not None:
            return
        about = _about(ended)
        if _withheld(await self.journal.history(DeliveryWithheld), about):
            return
        written = turn.notify is Notify.MESSAGE
        sent = await self.courier.deliver(
            self._person(task.owner),
            Notification(
                turn_instruction(task, turn.instruction, ended, written=written),
                about,
                must_tell=_must_tell(ok=ended.status is TurnStatus.COMPLETED, asked=turn.asked),
                files=ended.files,
                thread=task.thread,
            ),
            origin=turn.origin,
            written=written,
        )
        if sent is not None and sent.said:
            await self.tasks.delivered(task, turn, sent.address)

    async def remind(self, now: datetime | None = None) -> None:
        """Recall to their owners the questions tasks wait on, at each reminder due and not given yet."""
        now = now or utc_now()
        for task in list(self.tasks.tasks.values()):
            if task.question is None:
                continue
            turn = task.turn
            assert turn.ended_at is not None  # a question ends its turn
            due = sum(1 for after in self._reminders if now - turn.ended_at >= after)
            if due <= self._reminded.get(turn.id, 0):
                continue
            sent = await self.courier.deliver(
                self._person(task.owner),
                Notification(
                    reminder_instruction(task),
                    About(Source.TASK, task.id, "waiting", turn.id),
                    must_tell=True,
                    thread=task.thread,
                ),
                origin=turn.origin,  # where the question was given
            )
            if sent is not None:
                await self.journal.publish(
                    TaskReminded(
                        source=self.name, session=sent.address.session, task_id=task.id, turn_id=turn.id, count=due
                    )
                )
                self._reminded[turn.id] = due

    async def tool_returned(self, returned: ToolReturned) -> None:
        calls = await self.journal.history(ToolDeferred, session=returned.session)
        deferred = next((e for e in calls if e.call_id == returned.call_id), None)
        if deferred is None:
            return  # a call that answered in its turn
        person = self._person(deferred.person)
        about = About(Source.TOOL, returned.call_id, "returned" if returned.ok else "failed")
        sent = await self.courier.deliver(
            person,
            Notification(
                _tool_instruction(deferred, returned),
                about,
                must_tell=_must_tell(ok=returned.ok, asked=deferred.asked),
                files=returned.files,
                thread=deferred.thread,
                seen=returned.seen,
            ),
            origin=deferred.address,
        )
        if sent is not None and sent.said:
            await self.journal.publish(
                ToolResultDelivered(
                    source=self.name,
                    session=sent.address.session,
                    call_id=returned.call_id,
                    tool=returned.name,
                    address=sent.address,
                )
            )

    def _person(self, person: PersonId | None) -> Person | None:
        return self.household.person(person) if person else None

    async def _listen(self, subscription: Subscription) -> None:
        async for event in subscription:
            if isinstance(event, TurnEnded):
                await self.turn_ended(event)
            elif isinstance(event, ToolReturned):
                await self.tool_returned(event)

    async def _recall(self) -> None:
        while True:
            await asyncio.sleep(self._tick_s)
            await self.remind()


def _about(ended: TurnEnded) -> About:
    """What telling a turn's end is about: the task, and that turn of it."""
    return About(Source.TASK, ended.task_id, ended.status.value, ended.turn_id)


def _withheld(withheld: Iterable[DeliveryWithheld], about: About) -> bool:
    """Whether the agent already had nothing to tell about it."""
    return any(e.about.same(about) for e in withheld)


def _must_tell(*, ok: bool, asked: bool) -> bool:
    """A failure, a question, or what a person asked for in their own turn, is always told: only what Nestor started
    by itself and came back well may end in silence."""
    return not ok or asked


def turn_instruction(task: Task, instruction: str, ended: TurnEnded, *, written: bool) -> str:
    """What the agent reads when a turn of a task it handed over ends."""
    head = f'Task {task.id} ("{task.title}", {task.executor})'
    match ended.status:
        case TurnStatus.ASKED:
            done = f"\nWhat it did so far: {ended.result}" if ended.result else ""
            said = (
                f"{head} needs them to go on. Its question: {ended.question}{done}\nAsk them; pass their answer with "
                f"continue_task(task={task.id!r}), with any file they send for it."
            )
        case TurnStatus.COMPLETED:
            said = f"{head} came back.\nAsked: {instruction}\nReport: {ended.result}"
        case _:
            said = f"{head} failed.\nAsked: {instruction}\nFailure: {ended.error}"
    asked = "\nWrite it to them: they asked to get it as a message." if written else ""
    return f"{said}{asked}"


def reminder_instruction(task: Task) -> str:
    """What the agent reads when a task still waits on its owner's answer."""
    return (
        f'Task {task.id} ("{task.title}", {task.executor}) still waits for their answer to: {task.question}\n'
        f"Remind them in a few words; their answer goes on with continue_task(task={task.id!r})."
    )


def _tool_instruction(deferred: ToolDeferred, returned: ToolReturned) -> str:
    arguments = json.dumps(dict(deferred.arguments), ensure_ascii=False, default=str)
    outcome = f"Result: {returned.output}" if returned.ok else f"Failure: {returned.output}"
    return (
        f"A tool you called earlier was still running; it has now {'answered' if returned.ok else 'failed'}.\n"
        f"Call: {deferred.name} {arguments}\n{outcome}\nTell them what it means for what they asked."
    )
