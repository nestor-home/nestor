"""Durable delegated tasks: each a thread of turns with its executor, started from a conversation, directed and taken
up again from any, followed in the background, rebuilt from the journal after a restart.

The journal is the only record of a task. On start, the manager replays it: a remote turn that was working is followed
again; a turn that cannot be resumed is reported as interrupted, never silently dropped. On shutdown, remote turns are
left working (they will be followed again), local ones are stopped.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from functools import partial

from nestor.core import Component, ContractError, Event, PersonId, new_id, shorten, utc_now
from nestor.modules.channels import Address, Attachment, Exchange, unique_name
from nestor.modules.cognition.delegation.events import (
    ExecutorCalled,
    TaskArchived,
    TaskCreated,
    TaskNoted,
    TaskRenamed,
    TaskSteered,
    TurnAttached,
    TurnDelivered,
    TurnEnded,
    TurnFileAdded,
    TurnRetried,
    TurnStarted,
    TurnStepped,
    TurnStopRequested,
)
from nestor.modules.cognition.delegation.keys import ExecutorKeys, capability, digest
from nestor.modules.cognition.delegation.ports import Executor, RemoteExecutor
from nestor.modules.cognition.delegation.types import (
    CONTINUE,
    READ_TURNS,
    RESUME,
    STEER,
    STEPS,
    TURN_CHARS,
    Assignment,
    Handle,
    NestorTools,
    Notify,
    Outcome,
    Progress,
    TaskState,
    TurnStatus,
)
from nestor.modules.cognition.tools import title_of
from nestor.modules.journal import BlobStore, FileRef, Journal

logger = logging.getLogger(__name__)

INTERRUPTED = "interrupted: Nestor stopped while the turn worked and this executor cannot resume it"
NOTE_CHARS = 2000  # a note
NOTES = 50  # kept per task: the oldest give way
SWEEP_S = 3600.0  # how often ready tasks are looked at for archiving
ORDER = {TaskState.WAITING: 0, TaskState.WORKING: 1, TaskState.READY: 2, TaskState.ARCHIVED: 3}


class Directed(StrEnum):
    """What an instruction did to a task."""

    STEERED = "steered"  # brought into the turn that works
    STARTED = "started"  # opened a new turn
    BUSY = "busy"  # not given: the turn that works could not be stopped for it


class ExecutorUnavailable(ContractError):
    """The task's executor is no longer plugged in: it cannot be given an instruction."""


@dataclass(frozen=True, slots=True)
class Steer:
    """An instruction a turn took while it worked."""

    instruction: str
    by: PersonId | None
    at: datetime


@dataclass(frozen=True, slots=True)
class Delivery:
    """Where and when what a turn came back with reached its owner."""

    at: datetime
    address: Address


@dataclass(slots=True, kw_only=True)
class Turn:
    id: str
    instruction: str
    by: PersonId | None
    origin: Address  # the conversation its instruction was given in: where what it comes back with is told
    started_at: datetime
    given: tuple[FileRef, ...] = ()
    notify: Notify = Notify.AUTO
    exchange: Exchange | None = None
    capability: str | None = None  # the digest of what its executor calls Nestor's MCP server with for it
    asked: bool = False
    ref: str | None = None  # the executor's handle on it
    retried: bool = False  # in a new session, once, its own lost (`TurnRetried`)
    steps: list[str] = field(default_factory=list)  # the latest `STEPS` (the journal keeps them all)
    files: list[FileRef] = field(default_factory=list)  # handed back while it worked (`attach_file`)
    steered: list[Steer] = field(default_factory=list)  # what it took while it worked
    outcome: Outcome | None = None
    ended_at: datetime | None = None
    delivered: Delivery | None = None
    job: asyncio.Task[None] | None = field(default=None, repr=False)
    progress: Progress | None = field(default=None, repr=False)

    @property
    def status(self) -> TurnStatus:
        return self.outcome.status if self.outcome else TurnStatus.RUNNING

    @property
    def came_back(self) -> str:
        """What it came back with: its report, else its question, else why it failed; nothing while it works."""
        outcome = self.outcome
        return (outcome.result or outcome.question or outcome.error or "") if outcome else ""


@dataclass(slots=True, kw_only=True)
class Task:
    id: str
    title: str  # the short name the household knows it by
    executor: str
    owner: PersonId | None
    origin: Address  # where it was asked: its first turn, and every turn given outside a conversation, come back there
    created_at: datetime
    last_activity: datetime
    thread: str | None = None
    session: str | None = None  # what the next turn continues, as the executor named it
    turns: list[Turn] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # the latest `NOTES`
    archived: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)  # an instruction at a time

    @property
    def turn(self) -> Turn:
        """The latest turn: a task always has one."""
        return self.turns[-1]

    def turn_of(self, turn_id: str) -> Turn | None:
        return next((t for t in self.turns if t.id == turn_id), None)

    def before(self, turn: Turn) -> list[Turn]:
        """Its turns before `turn`."""
        return self.turns[: self.turns.index(turn)]

    def named(self, given: Sequence[FileRef]) -> tuple[FileRef, ...]:
        """`given`, each named apart from every other file of the task (sent or made: they share its folder)."""
        return _named(given, (f for turn in self.turns for f in (*turn.given, *turn.files)))

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
    def now(self) -> str | None:
        """What its executor says it does, while it works."""
        steps = self.turn.steps
        return steps[-1] if self.state is TaskState.WORKING and steps else None

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
        if self.now:
            found["now"] = self.now
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
        self.tasks: dict[str, Task] = {}
        self._stop_timeout_s, self._sweep_s = stop_timeout_s, sweep_s
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
            TurnRetried,
            TaskSteered,
            TurnFileAdded,
            TaskNoted,
            TurnEnded,
            TurnDelivered,
        ):
            self._replay(event)
        for task in self.tasks.values():
            turn = task.turn
            if turn.outcome is not None:
                continue
            executor = self.executors.get(task.executor)
            if isinstance(executor, RemoteExecutor) and turn.ref:
                self._launch(task, turn, partial(executor.resume, turn.ref))  # it went on while Nestor was away
            else:
                await self._end(task, turn, Outcome.failed(INTERRUPTED))
        self._sweeper = asyncio.create_task(self._sweep(), name="task-manager archiving")

    async def close(self) -> None:
        """Stop the turns that work here; leave those that work elsewhere going, to follow them again on start."""
        if self._sweeper is not None:
            self._sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sweeper
            self._sweeper = None
        for task in self.working():
            turn = task.turn
            executor = self.executors.get(task.executor)
            if executor is not None and RESUME in executor.capabilities and turn.ref and turn.job and turn.progress:
                turn.progress.detach()
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
        task_id = new_id()[:8]
        named = _named(given, ())
        assignment = await self._assignment(chosen, task_id, instruction, named)
        created = TaskCreated(
            source=self.name,
            session=origin.session,
            task_id=task_id,
            title=title,
            executor=chosen.name,
            owner=owner,
            origin=origin,
            thread=thread,
            turn_id=new_id()[:8],
            instruction=instruction,
            by=owner,
            given=named,
            notify=notify,
            exchange=exchange,
            capability=digest(assignment.task) if assignment.task else None,
            asked=asked,
        )
        await self.journal.publish(created)
        task = self._replay(created)
        self._launch(task, task.turn, partial(chosen.run, assignment))
        return task

    async def direct(
        self,
        task_id: str,
        instruction: str,
        *,
        by: PersonId | None,
        origin: Address | None = None,
        given: Sequence[FileRef] = (),
        notify: Notify = Notify.AUTO,
        exchange: Exchange | None = None,
        asked: bool = False,
    ) -> Directed:
        """Give a task an instruction, from the conversation at `origin` (`None`: from none, the admin): brought into
        the turn that works when its executor takes it (`STEER`), else that turn is stopped and the instruction opens
        the next once the stop is confirmed (`BUSY` when it is not: nothing is given); with no turn working, it opens
        the next, in the session of the turns before (an answer to its question, a follow-up days later). An archived
        task opens again."""
        task = self._task(task_id)
        executor = self.executors.get(task.executor)
        if executor is None:
            raise ExecutorUnavailable(f"the executor {task.executor!r} of this task is no longer plugged in")
        async with task.lock:
            turn = task.turn
            interrupts = False
            if turn.status is TurnStatus.RUNNING:
                # files cannot join a turn that works: the instruction then opens the next one
                steerable = STEER in executor.capabilities and turn.ref is not None and not given
                if steerable and await executor.steer(turn.ref or "", instruction):  # taken, whatever came after
                    await self._steered(task, turn, instruction, by, taken=True)
                    return Directed.STEERED
                if turn.status is TurnStatus.RUNNING:
                    await self._stop(task, turn, by=by)
                    if turn.status in (TurnStatus.RUNNING, TurnStatus.FAILED):  # still working, or not confirmed
                        return Directed.BUSY
                    interrupts = turn.status is TurnStatus.STOPPED
                await self._steered(task, turn, instruction, by, taken=False)
            named = task.named(given)
            assignment = await self._assignment(
                executor,
                task.id,
                instruction,
                named,
                before=task.turns,
                session=task.session,
                interrupts=interrupts,
            )
            started = TurnStarted(
                source=self.name,
                session=task.origin.session,
                task_id=task.id,
                turn_id=new_id()[:8],
                instruction=instruction,
                origin=origin,
                by=by,
                given=named,
                notify=notify,
                exchange=exchange,
                capability=digest(assignment.task) if assignment.task else None,
                asked=asked,
            )
            await self.journal.publish(started)
            self._replay(started)
            self._launch(task, task.turn, partial(executor.run, assignment))
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
        named = title_of(title)
        if named is None:
            raise ContractError("a task needs a short title")
        renamed = TaskRenamed(source=self.name, session=task.origin.session, task_id=task.id, title=named, by=by)
        await self.journal.publish(renamed)
        return self._replay(renamed)

    async def archive(self, task_id: str, *, by: PersonId | None = None) -> Task:
        """Put a task away, its turn stopped first if one works; an instruction opens it again."""
        task = self._task(task_id)
        if task.turn.status is TurnStatus.RUNNING:
            await self._stop(task, task.turn, by=by)
        if not task.archived:
            archived = TaskArchived(source=self.name, session=task.origin.session, task_id=task.id, by=by)
            await self.journal.publish(archived)
            self._replay(archived)
        return task

    async def admit(self, executor: str, capability: str, tool: str) -> Task | None:
        """The task whose working turn `capability` is for, `None` for anything else (another executor's, a turn
        that ended), whatever is wrong; journaled as a call of `tool` either way (`ExecutorCalled`)."""
        wanted = digest(capability)
        task = next((t for t in self.working() if t.executor == executor and t.turn.capability == wanted), None)
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
        noted = TaskNoted(source=self.name, session=task.origin.session, task_id=task.id, text=kept)
        await self.journal.publish(noted)
        self._replay(noted)
        return kept

    async def add_file(self, task: Task, turn_id: str, file: Attachment) -> FileRef:
        """A file `task`'s executor hands back while its turn `turn_id` works: kept, journaled, and sent with what it
        brings. Refused once that turn ended."""
        if self._blobs is None:
            raise ContractError("files cannot be kept here")
        kept = FileRef(await self._blobs.put(file.data, file.media_type), file.file_name)
        if task.turn.id != turn_id or task.turn.status is not TurnStatus.RUNNING:  # as it is journaled
            raise ContractError(f"the turn {turn_id!r} of task {task.id!r} no longer works")
        added = TurnFileAdded(
            source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn_id, file=kept
        )
        await self.journal.publish(added)
        self._replay(added)
        return kept

    async def delivered(self, task: Task, turn: Turn, address: Address) -> None:
        """What `turn` came back with reached its owner at `address`: it is never delivered again."""
        delivered = TurnDelivered(
            source=self.name, session=address.session, task_id=task.id, turn_id=turn.id, address=address
        )
        await self.journal.publish(delivered)
        self._replay(delivered)

    async def wait(self, task_id: str) -> Outcome:
        """The outcome of the task's latest turn, once it ended."""
        turn = self._task(task_id).turn
        if turn.job is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(turn.job)
        return turn.outcome or Outcome.failed("the turn ended without an outcome")

    def working(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.state is TaskState.WORKING]

    def of(self, person: PersonId | None = None, *, archived: bool = False) -> list[Task]:
        """The tasks `person` owns (every task without one), archived or not: those not archived waiting on their
        owner first, then working, then the latest active first; the archived ones, the latest first."""
        found = [
            t
            for t in self.tasks.values()
            if (person is None or t.owner == person) and (t.state is TaskState.ARCHIVED) == archived
        ]
        return sorted(found, key=lambda t: (ORDER[t.state], -t.last_activity.timestamp()))

    def _task(self, task_id: str) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise ContractError(f"no task {task_id!r}")
        return task

    async def _assignment(
        self,
        executor: Executor,
        task_id: str,
        instruction: str,
        given: tuple[FileRef, ...],
        *,
        before: Sequence[Turn] = (),
        session: str | None = None,
        interrupts: bool = False,
    ) -> Assignment:
        """What `executor` is given for a turn of a task: the `session` to go on in, or what the turns `before` were
        when it keeps none; the task's folder and the files sent with the instruction, read only by an executor that
        places them; and with Nestor's MCP server when it reaches it, a capability for the turn."""
        reader = self._blobs.get if self._blobs else None
        session = session if CONTINUE in executor.capabilities else None
        earlier = _earlier(before) if before and not session else ""
        token, access = None, None
        if self._keys is not None and executor.nestor_tools is NestorTools.CONFIGURED:
            token = capability()  # its own configuration holds the server and its key
        elif self._keys is not None and executor.nestor_tools is NestorTools.PASSED:
            access = await self._keys.access(executor.name)
            token = capability() if access else None
        return Assignment(
            instruction, session, earlier, f"task-{task_id}", token, access, given, reader, interrupts=interrupts
        )

    def _launch(self, task: Task, turn: Turn, work: Callable[[Progress], Awaitable[Outcome]]) -> None:
        turn.progress = self._progress(task, turn)
        turn.job = asyncio.create_task(self._run(task, turn, work, turn.progress), name=f"task {task.id}")

    async def _run(
        self, task: Task, turn: Turn, work: Callable[[Progress], Awaitable[Outcome]], progress: Progress
    ) -> None:
        """The turn's work to its end, journaled; cancelled while Nestor closes on remote work, left going. A turn
        whose session the executor no longer knows runs again at once, once, in a new session."""
        try:
            outcome = await work(progress)
            if outcome.session_lost and not turn.retried and (again := await self._anew(task, turn, outcome)):
                outcome = await again(progress)
        except asyncio.CancelledError:
            if progress.detached:
                raise
            outcome = Outcome.stopped()  # the stop went through before anything remote ran
        except Exception as error:  # a broken executor must not take the assistant down
            outcome = Outcome.failed(f"{type(error).__name__}: {error}")
        await self._end(task, turn, outcome)

    async def _anew(self, task: Task, turn: Turn, lost: Outcome) -> Callable[[Progress], Awaitable[Outcome]] | None:
        """The work of `turn` again, in a new session, told the turns before it; journaled. `None` without its
        executor."""
        executor = self.executors.get(task.executor)
        if executor is None:
            return None
        assignment = await self._assignment(executor, task.id, turn.instruction, turn.given, before=task.before(turn))
        await self._writes.join()  # what it said before, first
        retried = TurnRetried(
            source=self.name,
            session=task.origin.session,
            task_id=task.id,
            turn_id=turn.id,
            error=lost.error or "session lost",
            capability=digest(assignment.task) if assignment.task else None,
        )
        await self.journal.publish(retried)
        self._replay(retried)
        logger.warning(
            "task %s: its executor lost its session (%s), the turn runs again in a new one", task.id, lost.error
        )
        return partial(executor.run, assignment)

    async def _steered(self, task: Task, turn: Turn, instruction: str, by: PersonId | None, *, taken: bool) -> None:
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

    async def _stop(self, task: Task, turn: Turn, *, by: PersonId | None) -> Outcome:
        assert turn.job is not None  # a working turn always has its job
        await self.journal.publish(
            TurnStopRequested(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, by=by)
        )
        turn.job.cancel()
        done, _ = await asyncio.wait({turn.job}, timeout=self._stop_timeout_s)
        if not done:
            return Outcome.failed("stop requested, not confirmed by the executor")
        if turn.outcome is None:  # cancelled before it even started: nothing ran
            await self._end(task, turn, Outcome.stopped())
        assert turn.outcome is not None
        return turn.outcome

    def _progress(self, task: Task, turn: Turn) -> Progress:
        def step(text: str) -> None:
            turn.steps.append(text)
            del turn.steps[:-STEPS]
            task.last_activity = utc_now()
            self._writes.put_nowait(
                TurnStepped(source=self.name, session=task.origin.session, task_id=task.id, turn_id=turn.id, step=text)
            )

        def attach(handle: Handle) -> None:
            attached = TurnAttached(
                source=self.name,
                session=task.origin.session,
                task_id=task.id,
                turn_id=turn.id,
                ref=handle.ref,
                executor_session=handle.session,
            )
            self._replay(attached)
            self._writes.put_nowait(attached)

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
            executor_session=None if outcome.session_lost else outcome.session or task.session,
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
        """Apply one of the task's events to its state: when it happens, and when the journal is read on start. An
        event of one turn changes that turn, never another; one of a turn the task does not have is ignored."""
        match event:
            case TaskCreated():
                task = self.tasks[event.task_id] = Task(
                    id=event.task_id,
                    title=event.title,
                    executor=event.executor,
                    owner=event.owner,
                    origin=event.origin,
                    created_at=event.at,
                    last_activity=event.at,
                    thread=event.thread,
                    turns=[_opened(event, event.origin)],
                )
            case TaskRenamed():
                task = self.tasks[event.task_id]
                task.title = event.title
            case TaskArchived():
                task = self.tasks[event.task_id]
                task.archived = True
            case TurnStarted():
                task = self.tasks[event.task_id]
                task.turns.append(_opened(event, event.origin or task.origin))
                task.archived = False  # an instruction opens it again
            case TaskNoted():
                task = self.tasks[event.task_id]
                task.notes.append(event.text)
                del task.notes[:-NOTES]
            case TurnAttached() | TurnRetried() | TaskSteered() | TurnFileAdded() | TurnEnded() | TurnDelivered():
                task = self.tasks[event.task_id]
                turn = task.turn_of(event.turn_id)
                if turn is None:
                    logger.warning(
                        "task %s: %s of a turn it does not have (%s)", task.id, event.event_type, event.turn_id
                    )
                    return task
                if isinstance(event, TurnDelivered):  # not an activity of the task
                    turn.delivered = Delivery(event.at, event.address)
                    return task
                _apply(task, turn, event)
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
                idle = now - task.last_activity
                if days is not None and task.state is TaskState.READY and idle > timedelta(days=days):
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


def _apply(task: Task, turn: Turn, event: TurnAttached | TurnRetried | TaskSteered | TurnFileAdded | TurnEnded) -> None:
    """What an event of `turn` changes; the session the next turn continues only from the latest."""
    latest = turn is task.turn
    match event:
        case TurnAttached():
            turn.ref = event.ref
            if latest:
                task.session = event.executor_session or task.session
        case TurnRetried():
            turn.retried, turn.ref, turn.capability = True, None, event.capability
            if latest:
                task.session = None
        case TaskSteered():
            if event.taken:
                turn.steered.append(Steer(event.instruction, event.by, event.at))
        case TurnFileAdded():
            turn.files.append(event.file)
        case TurnEnded():
            turn.outcome = Outcome(
                event.status, event.result, event.question, event.error, session=event.executor_session
            )
            turn.ended_at = event.at
            turn.files = list(event.files)
            if latest:
                task.session = event.executor_session


def _named(given: Iterable[FileRef], files: Iterable[FileRef]) -> tuple[FileRef, ...]:
    """`given`, each named apart from `files` and from one another; a file sent again under the name it already has
    keeps it."""
    kept = {f.name: f.blob.digest for f in files}
    named: list[FileRef] = []
    for file in given:
        name = file.name if kept.get(file.name) == file.blob.digest else unique_name(file.name, kept)
        kept[name] = file.blob.digest
        named.append(FileRef(file.blob, name))
    return tuple(named)


def _opened(event: TaskCreated | TurnStarted, origin: Address) -> Turn:
    """The turn an instruction opens, given in the conversation at `origin`."""
    return Turn(
        id=event.turn_id,
        instruction=event.instruction,
        by=event.by,
        origin=origin,
        started_at=event.at,
        given=event.given,
        notify=event.notify,
        exchange=event.exchange,
        capability=event.capability,
        asked=event.asked,
    )


def _earlier(turns: Sequence[Turn]) -> str:
    """The latest turns before, for an executor that keeps no session: each instruction and what came back,
    shortened."""
    shown = turns[-READ_TURNS:]
    first = len(turns) - len(shown) + 1
    return "\n".join(
        f"{n}. Asked: {shorten(turn.instruction, TURN_CHARS)}\n"
        f"   Came back ({turn.status.value}): {shorten(turn.came_back, TURN_CHARS)}"
        for n, turn in enumerate(shown, first)
    )
