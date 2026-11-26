"""Events of delegated tasks: the journal is the only record of a task and its turns, so they survive restarts."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.delegation.types import Notify, TurnStatus
from nestor.modules.journal import FileRef


class TaskCreated(Event, event_type="task.created"):
    """A task, handed to `executor` for `owner` (`None`: for nobody in particular, an alert's), from `origin`, where
    what it comes back with is told; `thread`, what that continues (an alert that rings again: `Notification.thread`).
    It starts its first turn, given in `origin`: the fields after `thread` are that turn's, as `TurnStarted` gives a
    later one."""

    task_id: str
    title: str  # the short name the household knows it by
    executor: str
    owner: PersonId | None = None
    origin: Address  # the channel conversation it was asked in
    thread: str | None = None
    turn_id: str
    instruction: str
    by: PersonId | None = None
    given: tuple[FileRef, ...] = ()
    notify: Notify = Notify.AUTO
    exchange: Exchange | None = None
    capability: str | None = None
    asked: bool = False


class TaskRenamed(Event, event_type="task.renamed"):
    task_id: str
    title: str
    by: PersonId | None = None


class TaskArchived(Event, event_type="task.archived"):
    """Put away, by someone or after `Executor.archive_after_days` without activity (`by` `None`); an instruction
    opens it again."""

    task_id: str
    by: PersonId | None = None


class TurnStarted(Event, event_type="task.turn.started"):
    """An instruction that opens a later turn, from `by`, with the files sent with it (`given`). `origin` is the
    channel conversation it was given in, where what the turn comes back with is told (`None`: given outside any, from
    the admin; the task's own origin then), and `exchange` the conversation and turn of it that gave it, when one did;
    `capability`, the digest of the value its executor calls Nestor's MCP server with for it (never the value);
    `asked`, whether a person asked for it in their own turn, rather than Nestor (an alert)."""

    task_id: str
    turn_id: str
    instruction: str
    origin: Address | None = None
    by: PersonId | None = None
    given: tuple[FileRef, ...] = ()
    notify: Notify = Notify.AUTO
    exchange: Exchange | None = None
    capability: str | None = None
    asked: bool = False  # by a person, in their own turn: what it comes back with is always told


class TurnAttached(Event, event_type="task.turn.attached"):
    """The executor's handle on the turn: what follows remote work again after a restart, and what an instruction is
    steered to; with the `executor_session` the next turn continues, when the executor knows it as the turn starts."""

    task_id: str
    turn_id: str
    ref: str
    executor_session: str | None = None


class TurnRetried(Event, event_type="task.turn.retried"):
    """The executor no longer knew the session the turn was given (`error`, as it said it): the turn runs again at
    once, once, in a new session, told the turns before; `capability`, the digest of its new value."""

    task_id: str
    turn_id: str
    error: str
    capability: str | None = None


class TurnStepped(Event, event_type="task.turn.step"):
    """What the executor says it does (`report_progress`, or the step it streams)."""

    task_id: str
    turn_id: str
    step: str


class TaskSteered(Event, event_type="task.steered"):
    """An instruction given while a turn worked: `taken` when the executor brought it into the turn; otherwise the
    turn ended (stopped for it, or on its own meanwhile) and the instruction opens the next."""

    task_id: str
    turn_id: str
    instruction: str
    by: PersonId | None = None
    taken: bool


class TurnStopRequested(Event, event_type="task.turn.stop-requested"):
    task_id: str
    turn_id: str
    by: PersonId | None = None


class TurnFileAdded(Event, event_type="task.turn.file-added"):
    """A file the executor handed back while the turn worked (`attach_file`): it goes with what the turn brings."""

    task_id: str
    turn_id: str
    file: FileRef


class TaskNoted(Event, event_type="task.noted"):
    """What the executor keeps for the task (`note`): read back by Nestor, never a memory of a person."""

    task_id: str
    text: str


class TurnEnded(Event, event_type="task.turn.ended"):
    """How the turn ended: never `RUNNING`; a requested but unconfirmed stop ends as `FAILED`. `executor_session` is
    what the next turn continues; `files`, what the executor made, to go with the answer that brings the outcome."""

    task_id: str
    turn_id: str
    status: TurnStatus
    result: str | None = None
    question: str | None = None
    error: str | None = None
    duration_s: float
    files: tuple[FileRef, ...] = ()
    executor_session: str | None = None


class TurnDelivered(Event, event_type="task.turn.delivered"):
    """What the turn came back with reached its owner: it is never delivered again, even after a restart."""

    task_id: str
    turn_id: str
    address: Address


class TaskReminded(Event, event_type="task.reminded"):
    """The owner was reminded of the question the task waits on (the `count`-th time)."""

    task_id: str
    turn_id: str
    count: int


class ExecutorKeyIssued(Event, event_type="executor.key.issued"):
    """A new key for an executor to call Nestor's MCP server with; the one before no longer works. Never the key."""

    executor: str
    by: str | None = None  # the account that asked, or None when Nestor issued it to an executor it launches


class ExecutorKeyRevoked(Event, event_type="executor.key.revoked"):
    executor: str
    by: str | None = None


class ExecutorCalled(Event, event_type="executor.called"):
    """An executor called a tool of Nestor's MCP server for one of its tasks; what the tool did is journaled by its
    module."""

    executor: str
    task_id: str | None  # None when the call matched no working turn of that executor
    tool: str
    ok: bool
