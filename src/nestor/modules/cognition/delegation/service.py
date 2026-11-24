"""Durable delegated tasks: each a thread of turns with its executor, started from a conversation, directed and taken
up again from any, followed in the background, rebuilt from the journal after a restart.

The journal is the only record of a task. On start, the manager replays it: a remote turn that was working is followed
again; a turn that cannot be resumed is reported as interrupted, never silently dropped. On shutdown, remote turns are
left working (they will be followed again), local ones are stopped.
"""

import asyncio
import contextlib
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from nestor.core import Component, ContractError, Event, PersonId, new_id, utc_now
from nestor.modules.channels import Address, Attachment, Exchange
from nestor.modules.cognition.delegation.events import (
    ExecutorCalled,
    TaskArchived,
    TaskCreated,
    TaskNoted,
    TaskRenamed,
    TaskSteered,
    TurnAttached,
    TurnEnded,
    TurnFileAdded,
    TurnStarted,
    TurnStepped,
    TurnStopRequested,
)
from nestor.modules.cognition.delegation.keys import ExecutorKeys, capability, digest
from nestor.modules.cognition.delegation.ports import Executor, RemoteExecutor
from nestor.modules.cognition.delegation.types import (
    CONTINUE,
    STEER,
    Assignment,
    NestorTools,
    Notify,
    Outcome,
    Progress,
    TaskState,
    TurnStatus,
)
from nestor.modules.journal import BlobStore, FileRef, Journal

logger = logging.getLogger(__name__)

INTERRUPTED = "interrupted: Nestor stopped while the turn worked and this executor cannot resume it"
STOPPED_FOR = "Your previous turn was stopped for this new instruction:\n{instruction}"
NOTE_CHARS = 2000  # a note
NOTES = 50  # kept per task: the oldest give way
STEPS = 200  # kept per turn in memory (the journal keeps them all)
EARLIER_CHARS = 600  # of each earlier turn's instruction and report, for an executor that keeps no session
SWEEP_S = 3600.0  # how often ready tasks are looked at for archiving


class Directed(StrEnum):
    """What an instruction did to a task."""

    STEERED = "steered"  # brought into the turn that works
    STARTED = "started"  # opened a new turn


@dataclass(frozen=True, slots=True)
class Steer:
    """An instruction a turn took while it worked."""

    instruction: str
    by: PersonId | None
    at: datetime


@dataclass(slots=True, kw_only=True)
class Turn:
    id: str
    instruction: str
    by: PersonId | None
    started_at: datetime
    given: tuple[FileRef, ...] = ()
    notify: Notify = Notify.AUTO
    exchange: Exchange | None = None
    capability: str | None = None  # the digest of what its executor calls Nestor's MCP server with for it
    asked: bool = False
    ref: str | None = None  # the executor's handle on it
    steps: list[str] = field(default_factory=list)
    files: list[FileRef] = field(default_factory=list)  # handed back while it worked (`attach_file`)
    steered: list[Steer] = field(default_factory=list)  # what it took while it worked
    outcome: Outcome | None = None
    ended_at: datetime | None = None
    job: asyncio.Task[None] | None = field(default=None, repr=False)
    detached: bool = False

    @property
    def status(self) -> TurnStatus:
        return self.outcome.status if self.outcome else TurnStatus.RUNNING


@dataclass(slots=True, kw_only=True)
class Task:
    id: str
    title: str  # the short name the household knows it by
    executor: str
    owner: PersonId | None
    origin: Address  # where what it comes back with is told
    created_at: datetime
    thread: str | None = None
    session: str | None = None  # what the next turn continues, as the executor named it
    turns: list[Turn] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    archived: bool = False
    last_activity: datetime | None = None

    @property
    def turn(self) -> Turn:
        """The latest turn: a task always has one."""
        return self.turns[-1]

    @property
    def state(self) -> TaskState:
        if self.turn.status is TurnStatus.RUNNING:
            return TaskState.WORKING
        if self.archived:
            return TaskState.ARCHIVED
        return TaskState.WAITING if self.turn.status is TurnStatus.ASKED else TaskState.READY

    @property
    def question(self) -> str | None:
        """What it waits on its owner for."""
        outcome = self.turn.outcome
        return outcome.question if self.state is TaskState.WAITING and outcome else None

    @property
    def given(self) -> tuple[FileRef, ...]:
        """Every file sent with its instructions, the first first."""
        return tuple(f for turn in self.turns for f in turn.given)

    def summary(self) -> dict[str, object]:
        """What the agent needs to say how it stands: no report, which is told when it comes back."""
        turn = self.turn
        found: dict[str, object] = {
            "task_id": self.id,
            "title": self.title,
            "executor": self.executor,
            "state": self.state.value,
            "since_s": round((utc_now() - (turn.ended_at or turn.started_at)).total_seconds()),
        }
        if self.state is TaskState.WORKING and turn.steps:
            found["now"] = turn.steps[-1]
        if self.question:
            found["question"] = self.question
        return found


class TaskManager(Component):
    name = "task-manager"

    def __init__(
        self,
        journal: Journal,
        executors: Iterable[Executor],
        *,
        blobs: BlobStore | None = None,
        keys: ExecutorKeys | None = None,
        stop_timeout_s: float = 20.0,
        sweep_s: float = SWEEP_S,
    ) -> None:
        """`blobs` keeps the files executors make; without it they are left out. `keys`: executors reach Nestor's
        MCP server for their tasks; without them, none does."""
        self.journal, self._blobs, self._keys = journal, blobs, keys
        self.executors: Mapping[str, Executor] = {e.name: e for e in executors}
        self.tasks: dict[str, Task] = {}  # each with its first turn: none is seen without one
        self._opening: dict[str, Task] = {}  # created, their first turn not recorded yet
        self._capable: dict[str, tuple[Task, Turn]] = {}  # by the digest of a turn's capability
        self._stop_timeout_s, self._sweep_s = stop_timeout_s, sweep_s
        self._locks: dict[str, asyncio.Lock] = {}  # one instruction at a time per task
        self._writes: asyncio.Queue[Event] = asyncio.Queue()
        self._writer: asyncio.Task[None] | None = None
        self._sweeper: asyncio.Task[None] | None = None

    @property
    def default_executor(self) -> Executor | None:
        return next(iter(self.executors.values()), None)

    async def start(self) -> None:
        """Rebuild the tasks from the journal and pick up the turns that were working."""
        self._writer = asyncio.create_task(self._write(), name="task-manager writer")
        for event in await self.journal.history(
            TaskCreated,
            TaskRenamed,
            TaskArchived,
            TurnStarted,
            TurnAttached,
            TaskSteered,
            TurnFileAdded,
            TaskNoted,
            TurnEnded,
        ):
            self._replay(event)
        for task_id in self._opening:  # created, then Nestor stopped before its first turn was recorded
            logger.warning("task %s was never started: left out", task_id)
        self._opening.clear()
        for task in self.tasks.values():
            turn = task.turn
            if turn.outcome is not None:
                continue
            executor = self.executors.get(task.executor)
            if isinstance(executor, RemoteExecutor) and turn.ref:
                turn.job = asyncio.create_task(self._follow(task, turn, executor), name=f"task {task.id}")
            else:
                await self._end(task, turn, Outcome.failed(INTERRUPTED, session=task.session))
        self._sweeper = asyncio.create_task(self._sweep(), name="task-manager archiving")

    async def close(self) -> None:
        if self._sweeper is not None:
            self._sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sweeper
            self._sweeper = None
        for task in self.working():
            turn = task.turn
            if isinstance(self.executors.get(task.executor), RemoteExecutor) and turn.ref and turn.job:
                turn.detached = True  # still working remotely: followed again on next start
                turn.job.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await turn.job
            else:
                await self.stop(task.id)
        if self._writer is not None:
            await self._writes.join()
            self._writer.cancel()
            self._writer = None

    async def start_task(
        self,
        instruction: str,
        *,
        title: str,
        origin: Address,
        owner: PersonId | None = None,
        executor: str | None = None,
        exchange: Exchange | None = None,
        thread: str | None = None,
        given: Sequence[FileRef] = (),
        notify: Notify = Notify.AUTO,
        asked: bool = False,
    ) -> Task:
        """A new task for `owner`, its first turn started. `title`: the short name the household knows it by;
        `given`: the files sent with the instruction; `asked`: a person asked for it in their own turn, so what it
        comes back with is always told."""
        if self._writer is None:
            raise ContractError("the task manager must be started before delegating")
        chosen = self.executors.get(executor) if executor else self.default_executor
        if chosen is None:
            raise ContractError(f"no executor named {executor!r}" if executor else "no executor is plugged in")
        created = TaskCreated(
            source=self.name,
            session=origin.session,
            task_id=new_id()[:8],
            title=title,
            executor=chosen.name,
            owner=owner,
            origin=origin,
            thread=thread,
        )
        await self.journal.publish(created)
        task = self._replay(created)
        await self._turn(
            task, chosen, instruction, by=owner, given=given, notify=notify, exchange=exchange, asked=asked
        )
        return task

    async def direct(
        self,
        task_id: str,
        instruction: str,
        *,
        by: PersonId | None,
        given: Sequence[FileRef] = (),
        notify: Notify = Notify.AUTO,
        exchange: Exchange | None = None,
        asked: bool = False,
    ) -> Directed:
        """Give a task an instruction: brought into the turn that works when its executor can take it (`STEER`), else
        that turn is stopped and the instruction opens the next; with no turn working, it opens the next, in the
        session of the turns before (an answer to its question, a follow-up days later). An archived task opens
        again."""
        task = self._task(task_id)
        executor = self.executors.get(task.executor)
        if executor is None:
            raise ContractError(f"the executor {task.executor!r} of this task is no longer plugged in")
        async with self._locks.setdefault(task.id, asyncio.Lock()):
            turn = task.turn
            if turn.status is TurnStatus.RUNNING:
                # files cannot join a turn that works: the instruction then opens the next one
                steerable = STEER in executor.capabilities and turn.ref is not None and not given
                taken = steerable and await executor.steer(turn.ref or "", instruction)
                taken = taken and turn.status is TurnStatus.RUNNING
                steered = TaskSteered(
                    source=self.name,
                    session=task.origin.session,
                    task_id=task.id,
                    turn_id=turn.id,
                    instruction=instruction,
                    by=by,
                    taken=taken,
                )
                await self.journal.publish(steered)
                self._replay(steered)
                if taken:
                    return Directed.STEERED
                if turn.status is TurnStatus.RUNNING:
                    await self._stop(task, turn, by=by)
                instruction = STOPPED_FOR.format(instruction=instruction)
            await self._turn(
                task, executor, instruction, by=by, given=given, notify=notify, exchange=exchange, asked=asked
            )
            return Directed.STARTED

    async def stop(self, task_id: str, *, by: PersonId | None = None) -> Outcome:
        """Ask the executor to stop the turn that works; the outcome says whether the stop was confirmed. The task
        stays, ready to go on."""
        task = self._task(task_id)
        turn = task.turn
        if turn.outcome is not None:
            return turn.outcome
        return await self._stop(task, turn, by=by)

    async def rename(self, task_id: str, title: str, *, by: PersonId | None = None) -> Task:
        task = self._task(task_id)
        title = " ".join(title.split())
        if not title:
            raise ContractError("a task needs a title")
        await self.journal.publish(
            TaskRenamed(source=self.name, session=task.origin.session, task_id=task.id, title=title, by=by)
        )
        task.title = title
        return task

    async def archive(self, task_id: str, *, by: PersonId | None = None) -> Task:
        """Put a task away, its turn stopped first if one works; an instruction opens it again."""
        task = self._task(task_id)
        if task.turn.status is TurnStatus.RUNNING:
            await self._stop(task, task.turn, by=by)
        if not task.archived:
            await self.journal.publish(
                TaskArchived(source=self.name, session=task.origin.session, task_id=task.id, by=by)
            )
            task.archived = True
        return task

    async def admit(self, executor: str, capability: str, tool: str) -> Task | None:
        """The task whose working turn `capability` is for, `None` for anything else (another executor's, a turn
        that ended), whatever is wrong; journaled as a call of `tool` either way (`ExecutorCalled`)."""
        found = self._capable.get(digest(capability))
        task = None
        if found is not None:
            candidate, turn = found
            if candidate.executor == executor and turn.status is TurnStatus.RUNNING and candidate.turn is turn:
                task = candidate
        call = ExecutorCalled(
            source=self.name,
            session=task.origin.session if task else None,
            executor=executor,
            task_id=task.id if task else None,
            tool=tool,
            ok=task is not None,
        )
        await self.journal.publish(call)
        if self._keys is not None:
            self._keys.used(executor, call.at)
        return task

    def report(self, task: Task, step: str) -> None:
        """A step of `task`'s working turn, said by its executor through Nestor's MCP server."""
        self._progress(task, task.turn)(step)

    async def note(self, task: Task, text: str) -> str:
        """Keep what the executor wants the task to remember; the oldest notes give way past `NOTES`."""
        kept = text.strip()[:NOTE_CHARS]
        if not kept:
            raise ContractError("an empty note")
        await self.journal.publish(TaskNoted(source=self.name, session=task.origin.session, task_id=task.id, text=kept))
        task.notes = [*task.notes, kept][-NOTES:]
        return kept

    async def add_file(self, task: Task, file: Attachment) -> FileRef:
        """A file `task`'s executor hands back while its turn works: kept, journaled, and sent with what it brings."""
        if self._blobs is None:
            raise ContractError("files cannot be kept here")
        kept = FileRef(await self._blobs.put(file.data, file.media_type), file.file_name)
        turn = task.turn
        turn.files.append(kept)
        await self.journal.publish(
            TurnFileAdded(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, file=kept)
        )
        return kept

    async def wait(self, task_id: str) -> Outcome:
        """The outcome of the task's latest turn, once it ended."""
        turn = self._task(task_id).turn
        if turn.job is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(turn.job)
        return turn.outcome or Outcome.failed("the turn ended without an outcome")

    def working(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.state is TaskState.WORKING]

    def of(self, person: PersonId | None) -> list[Task]:
        """The tasks `person` owns, not archived, the latest active first."""
        found = [t for t in self.tasks.values() if t.owner == person and t.state is not TaskState.ARCHIVED]
        return sorted(found, key=_active, reverse=True)

    def _task(self, task_id: str) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise ContractError(f"no task {task_id!r}")
        return task

    async def _turn(
        self,
        task: Task,
        executor: Executor,
        instruction: str,
        *,
        by: PersonId | None,
        given: Sequence[FileRef],
        notify: Notify,
        exchange: Exchange | None,
        asked: bool,
    ) -> Turn:
        assignment = await self._assignment(task, executor, instruction, tuple(given))
        started = TurnStarted(
            source=self.name,
            session=task.origin.session,
            task_id=task.id,
            turn_id=new_id()[:8],
            instruction=instruction,
            by=by,
            given=tuple(given),
            notify=notify,
            exchange=exchange,
            capability=digest(assignment.task) if assignment.task else None,
            asked=asked,
        )
        await self.journal.publish(started)
        self._replay(started)
        turn = task.turn
        turn.job = asyncio.create_task(self._run(task, turn, executor, assignment), name=f"task {task.id}")
        return turn

    async def _assignment(
        self, task: Task, executor: Executor, instruction: str, given: tuple[FileRef, ...]
    ) -> Assignment:
        """What `executor` is given for a turn: the session to go on in, or what the turns before were when it keeps
        none; the task's folder and the files sent with the instruction, read only by an executor that places them;
        and with Nestor's MCP server when it reaches it, a capability for the turn."""
        reader = self._blobs.get if self._blobs else None
        session = task.session if CONTINUE in executor.capabilities else None
        earlier = "" if session or not task.turns else _earlier(task.turns)
        token, access = None, None
        if self._keys is not None and executor.nestor_tools is NestorTools.CONFIGURED:
            token = capability()  # its own configuration holds the server and its key
        elif self._keys is not None and executor.nestor_tools is NestorTools.PASSED:
            access = await self._keys.access(executor.name)
            token = capability() if access else None
        return Assignment(instruction, session, earlier, f"task-{task.id}", token, access, given, reader)

    async def _stop(self, task: Task, turn: Turn, *, by: PersonId | None) -> Outcome:
        assert turn.job is not None  # a working turn always has its job
        await self.journal.publish(
            TurnStopRequested(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, by=by)
        )
        turn.job.cancel()
        done, _ = await asyncio.wait({turn.job}, timeout=self._stop_timeout_s)
        if not done:
            return Outcome.failed("stop requested, not confirmed by the executor")
        if turn.outcome is None:  # stopped before it even started: nothing ran
            await self._end(task, turn, Outcome.stopped(session=task.session))
        assert turn.outcome is not None
        return turn.outcome

    async def _run(self, task: Task, turn: Turn, executor: Executor, assignment: Assignment) -> None:
        if not isinstance(executor, RemoteExecutor):
            try:
                outcome = await executor.run(assignment, self._progress(task, turn))
            except asyncio.CancelledError:
                outcome = Outcome.stopped(session=task.session)  # the stop went through: nothing remote ran
            except Exception as error:  # a broken executor must not take the assistant down
                outcome = Outcome.failed(f"{type(error).__name__}: {error}", session=task.session)
            await self._end(task, turn, outcome)
            return
        try:
            ref = await executor.submit(assignment)
        except asyncio.CancelledError:
            await self._end(task, turn, Outcome.stopped(session=task.session))
            return
        except Exception as error:
            await self._end(task, turn, Outcome.failed(str(error), session=task.session))
            return
        await self._attached(task, turn, ref)
        await self._follow(task, turn, executor)

    async def _follow(self, task: Task, turn: Turn, executor: RemoteExecutor) -> None:
        assert turn.ref is not None
        try:
            outcome = await executor.follow(turn.ref, self._progress(task, turn))
        except asyncio.CancelledError:
            if turn.detached:
                raise
            confirmed = await asyncio.shield(executor.stop(turn.ref))
            session = task.session or executor.session_of(turn.ref)
            outcome = Outcome.stopped(session=session) if confirmed else Outcome.failed("stop not confirmed")
        except Exception as error:
            outcome = Outcome.failed(f"{type(error).__name__}: {error}", session=task.session)
        await self._end(task, turn, outcome)

    async def _attached(self, task: Task, turn: Turn, ref: str) -> None:
        turn.ref = ref
        await self.journal.publish(
            TurnAttached(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, ref=ref)
        )

    def _progress(self, task: Task, turn: Turn) -> Progress:
        def step(text: str) -> None:
            turn.steps = [*turn.steps, text][-STEPS:]
            task.last_activity = utc_now()
            self._writes.put_nowait(
                TurnStepped(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, step=text)
            )

        def attach(ref: str) -> None:  # a local executor's handle (Claude Code's session): what it is steered to
            turn.ref = ref
            self._writes.put_nowait(
                TurnAttached(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, ref=ref)
            )

        return Progress(step, attach)

    async def _end(self, task: Task, turn: Turn, outcome: Outcome) -> None:
        await self._writes.join()  # progress first: the journal keeps the order things happened in
        made, lost = await self._keep(task, outcome.files)
        result = outcome.result
        if lost:
            result = f"{result or ''}\nFiles not kept: {'; '.join(lost)}".strip()
        ended = TurnEnded(
            source=self.name,
            session=task.origin.session,
            task_id=task.id,
            turn_id=turn.id,
            status=outcome.status,
            result=result,
            question=outcome.question,
            error=outcome.error,
            duration_s=round((utc_now() - turn.started_at).total_seconds(), 1),
            files=(*turn.files, *made),
            executor_session=outcome.session or task.session,
        )
        await self.journal.publish(ended)
        self._replay(ended)

    async def _keep(self, task: Task, made: tuple[Attachment, ...]) -> tuple[tuple[FileRef, ...], list[str]]:
        """The files kept in the blob store, and those that could not be, with why: the turn ends either way."""
        kept: list[FileRef] = []
        lost: list[str] = []
        for file in made:
            name = file.file_name
            if self._blobs is None:
                lost.append(f"{name} (nowhere to keep it)")
                continue
            try:
                kept.append(FileRef(await self._blobs.put(file.data, file.media_type), name))
            except Exception as error:  # a full disk must not lose the turn's end
                logger.warning("task %s: a file could not be kept (%s)", task.id, error)
                lost.append(f"{name} ({type(error).__name__})")
        return tuple(kept), lost

    def _replay(self, event: Event) -> Task:
        """Apply one of the task's events to its state: when it happens, and when the journal is read on start."""
        match event:
            case TaskCreated():
                task = self._opening[event.task_id] = Task(
                    id=event.task_id,
                    title=event.title,
                    executor=event.executor,
                    owner=event.owner,
                    origin=event.origin,
                    created_at=event.at,
                    thread=event.thread,
                    last_activity=event.at,
                )
                return task
            case TaskRenamed():
                task = self.tasks[event.task_id]
                task.title = event.title
            case TaskArchived():
                task = self.tasks[event.task_id]
                task.archived = True
            case TurnStarted():
                task = self.tasks.get(event.task_id) or self.tasks.setdefault(
                    event.task_id, self._opening.pop(event.task_id)
                )
                turn = Turn(
                    id=event.turn_id,
                    instruction=event.instruction,
                    by=event.by,
                    started_at=event.at,
                    given=event.given,
                    notify=event.notify,
                    exchange=event.exchange,
                    capability=event.capability,
                    asked=event.asked,
                )
                task.turns.append(turn)
                task.archived = False  # an instruction opens it again
                if turn.capability:
                    self._capable[turn.capability] = (task, turn)
            case TurnAttached():
                task = self.tasks[event.task_id]
                task.turn.ref = event.ref
            case TaskSteered():
                task = self.tasks[event.task_id]
                if event.taken:
                    task.turn.steered.append(Steer(event.instruction, event.by, event.at))
            case TurnFileAdded():
                task = self.tasks[event.task_id]
                task.turn.files.append(event.file)
            case TaskNoted():
                task = self.tasks[event.task_id]
                task.notes = [*task.notes, event.text][-NOTES:]
            case TurnEnded():
                task = self.tasks[event.task_id]
                turn = task.turn
                turn.outcome = Outcome(
                    event.status, event.result, event.question, event.error, session=event.executor_session
                )
                turn.ended_at = event.at
                turn.files = list(event.files)
                task.session = event.executor_session
                if turn.capability:
                    self._capable.pop(turn.capability, None)
            case _:
                raise ContractError(f"not an event of a task: {type(event).__name__}")
        task.last_activity = event.at
        return task

    async def _sweep(self) -> None:
        """Archive the ready tasks left alone longer than their executor keeps them (`archive_after_days`)."""
        while True:
            now = utc_now()
            for task in list(self.tasks.values()):
                executor = self.executors.get(task.executor)
                days = executor.archive_after_days if executor else None
                idle = task.last_activity or task.created_at
                if days is not None and task.state is TaskState.READY and now - idle > timedelta(days=days):
                    with contextlib.suppress(Exception):  # the next sweep tries again
                        await self.archive(task.id)
            await asyncio.sleep(self._sweep_s)

    async def _write(self) -> None:
        while True:
            event = await self._writes.get()
            try:
                await self.journal.publish(event)
            finally:
                self._writes.task_done()


def _active(task: Task) -> datetime:
    return task.last_activity or task.created_at


def _earlier(turns: Sequence[Turn]) -> str:
    """The turns before, for an executor that keeps no session: each instruction and what came back, shortened."""

    def cut(text: str | None) -> str:
        line = " ".join((text or "").split())
        return line if len(line) <= EARLIER_CHARS else f"{line[:EARLIER_CHARS]}…"

    lines = []
    for n, turn in enumerate(turns, 1):
        outcome = turn.outcome
        back = cut(outcome.result or outcome.question or outcome.error) if outcome else ""
        lines.append(f"{n}. Asked: {cut(turn.instruction)}\n   Came back ({turn.status.value}): {back}")
    return "\n".join(lines)
