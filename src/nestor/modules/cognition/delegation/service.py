"""Durable delegated tasks: started from the conversation, followed in the background, rebuilt
from the journal after a restart.

The journal is the only record of a task. On start, the manager replays it: remote work that was
running is followed again; work that cannot be resumed is reported as interrupted, never
silently dropped. On shutdown, remote work is left running (it will be followed again), local
work is stopped.
"""

import asyncio
import contextlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from nestor.core import Component, ContractError, Event, PersonId, new_id, utc_now
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.delegation.events import (
    TaskAttached,
    TaskCancelRequested,
    TaskEnded,
    TaskProgressed,
    TaskStarted,
)
from nestor.modules.cognition.delegation.ports import Executor, RemoteExecutor
from nestor.modules.cognition.delegation.types import Notify, Outcome, Progress, TaskStatus
from nestor.modules.journal import Journal

INTERRUPTED = "interrupted: Nestor stopped while the task was running and this executor cannot resume it"


@dataclass(slots=True, kw_only=True)
class Task:
    id: str
    objective: str
    executor: str
    origin: Address
    requested_by: PersonId | None
    notify: Notify
    started_at: datetime
    ref: str | None = None
    steps: list[str] = field(default_factory=list)
    outcome: Outcome | None = None
    job: asyncio.Task[None] | None = field(default=None, repr=False)
    detached: bool = False

    @property
    def status(self) -> TaskStatus:
        return self.outcome.status if self.outcome else TaskStatus.RUNNING

    def snapshot(self) -> dict[str, object]:
        """What the agent needs to answer "how is it going?": no result, which is announced separately."""
        report: dict[str, object] = {
            "task_id": self.id,
            "objective": self.objective,
            "executor": self.executor,
            "status": self.status.value,
            "elapsed_s": round((utc_now() - self.started_at).total_seconds()),
        }
        if self.status is TaskStatus.RUNNING:
            report["last_steps"] = self.steps[-3:]
        return report


class TaskManager(Component):
    name = "task-manager"

    def __init__(self, journal: Journal, executors: Iterable[Executor], *, cancel_timeout_s: float = 20.0) -> None:
        self.journal = journal
        self.executors: Mapping[str, Executor] = {e.name: e for e in executors}
        self.tasks: dict[str, Task] = {}
        self._cancel_timeout_s = cancel_timeout_s
        self._writes: asyncio.Queue[Event] = asyncio.Queue()
        self._writer: asyncio.Task[None] | None = None

    @property
    def default_executor(self) -> Executor | None:
        return next(iter(self.executors.values()), None)

    async def start(self) -> None:
        """Rebuild the tasks from the journal and pick up the ones that were running."""
        self._writer = asyncio.create_task(self._write(), name="task-manager writer")
        attached = {e.task_id: e.ref for e in await self.journal.history(TaskAttached)}
        ended = {e.task_id: e for e in await self.journal.history(TaskEnded)}
        for event in await self.journal.history(TaskStarted):
            task = self.tasks[event.task_id] = _task(event, attached.get(event.task_id))
            if done := ended.get(task.id):
                task.outcome = Outcome(done.status, done.result, done.error)
                continue
            executor = self.executors.get(task.executor)
            if isinstance(executor, RemoteExecutor) and task.ref:
                task.job = asyncio.create_task(self._follow(task, executor), name=f"task {task.id}")
            else:
                await self._end(task, Outcome.failed(INTERRUPTED))

    async def close(self) -> None:
        for task in self.running():
            if isinstance(self.executors.get(task.executor), RemoteExecutor) and task.ref and task.job:
                task.detached = True  # still running remotely: followed again on next start
                task.job.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task.job
            else:
                await self.cancel(task.id)
        if self._writer is not None:
            await self._writes.join()
            self._writer.cancel()
            self._writer = None

    async def delegate(
        self,
        objective: str,
        *,
        origin: Address,
        requested_by: PersonId | None = None,
        notify: Notify = Notify.AUTO,
        executor: str | None = None,
        exchange: Exchange | None = None,
    ) -> Task:
        if self._writer is None:
            raise ContractError("the task manager must be started before delegating")
        chosen = self.executors.get(executor) if executor else self.default_executor
        if chosen is None:
            raise ContractError(f"no executor named {executor!r}" if executor else "no executor is plugged in")
        event = TaskStarted(
            source=self.name,
            session=origin.session,
            task_id=new_id()[:8],
            objective=objective,
            executor=chosen.name,
            origin=origin,
            requested_by=requested_by,
            notify=notify,
            exchange=exchange,
        )
        await self.journal.publish(event)
        task = self.tasks[event.task_id] = _task(event, None)
        task.job = asyncio.create_task(self._run(task, chosen), name=f"task {task.id}")
        return task

    async def cancel(self, task_id: str) -> Outcome:
        """Ask the executor to stop; the outcome says whether the stop was confirmed."""
        task = self.tasks.get(task_id)
        if task is None:
            return Outcome.failed(f"unknown task {task_id!r}")
        if task.outcome is not None:
            return task.outcome
        assert task.job is not None  # a running task always has its job
        await self.journal.publish(TaskCancelRequested(source=self.name, session=task.origin.session, task_id=task.id))
        task.job.cancel()
        done, _ = await asyncio.wait({task.job}, timeout=self._cancel_timeout_s)
        if not done:
            return Outcome.failed("stop requested, not confirmed by the executor")
        if task.outcome is None:  # cancelled before it even started: nothing ran
            await self._end(task, Outcome.cancelled())
        assert task.outcome is not None
        return task.outcome

    async def wait(self, task_id: str) -> Outcome:
        task = self.tasks[task_id]
        if task.job is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(task.job)
        return task.outcome or Outcome.failed("task ended without an outcome")

    def running(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.status is TaskStatus.RUNNING]

    def recent(self, count: int = 3) -> list[Task]:
        return [t for t in self.tasks.values() if t.status is not TaskStatus.RUNNING][-count:]

    async def _run(self, task: Task, executor: Executor) -> None:
        if not isinstance(executor, RemoteExecutor):
            try:
                outcome = await executor.run(task.objective, self._progress(task))
            except asyncio.CancelledError:
                outcome = Outcome.cancelled()  # the cancellation went through: nothing remote ran
            except Exception as error:  # a broken executor must not take the assistant down
                outcome = Outcome.failed(f"{type(error).__name__}: {error}")
            await self._end(task, outcome)
            return
        try:
            ref = await executor.submit(task.objective)
        except asyncio.CancelledError:
            await self._end(task, Outcome.cancelled())
            return
        except Exception as error:
            await self._end(task, Outcome.failed(str(error)))
            return
        task.ref = ref
        await self.journal.publish(
            TaskAttached(source=self.name, session=task.origin.session, task_id=task.id, ref=ref)
        )
        await self._follow(task, executor)

    async def _follow(self, task: Task, executor: RemoteExecutor) -> None:
        assert task.ref is not None
        try:
            outcome = await executor.follow(task.ref, self._progress(task))
        except asyncio.CancelledError:
            if task.detached:
                raise
            confirmed = await asyncio.shield(executor.stop(task.ref))
            outcome = Outcome.cancelled() if confirmed else Outcome.failed("stop requested, not confirmed")
        except Exception as error:
            outcome = Outcome.failed(f"{type(error).__name__}: {error}")
        await self._end(task, outcome)

    def _progress(self, task: Task) -> Progress:
        def step(text: str) -> None:
            task.steps.append(text)
            self._writes.put_nowait(
                TaskProgressed(source=self.name, session=task.origin.session, task_id=task.id, step=text)
            )

        return Progress(step)

    async def _end(self, task: Task, outcome: Outcome) -> None:
        await self._writes.join()  # progress first: the journal keeps the order things happened in
        task.outcome = outcome
        await self.journal.publish(
            TaskEnded(
                source=self.name,
                session=task.origin.session,
                task_id=task.id,
                status=outcome.status,
                result=outcome.result,
                error=outcome.error,
                duration_s=round((utc_now() - task.started_at).total_seconds(), 1),
            )
        )

    async def _write(self) -> None:
        while True:
            event = await self._writes.get()
            try:
                await self.journal.publish(event)
            finally:
                self._writes.task_done()


def _task(event: TaskStarted, ref: str | None) -> Task:
    return Task(
        id=event.task_id,
        objective=event.objective,
        executor=event.executor,
        origin=event.origin,
        requested_by=event.requested_by,
        notify=event.notify,
        started_at=event.at,
        ref=ref,
    )
