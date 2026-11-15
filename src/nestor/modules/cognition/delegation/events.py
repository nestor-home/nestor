"""Events of delegated tasks: the journal is the only record of a task, so it survives restarts."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address, Exchange
from nestor.modules.cognition.delegation.types import Notify, TaskStatus
from nestor.modules.journal import BlobRef


class TaskStarted(Event, event_type="task.started"):
    """`exchange` is the conversation and turn that delegated it, when one did; `thread`, what its result continues
    (a recurring wake-up that delegated it: `Notification.thread`); `capability`, the digest of the value its executor
    calls Nestor's MCP server with for it (never the value), when it reaches it."""

    task_id: str
    objective: str
    executor: str
    origin: Address  # the channel conversation the task was asked in
    requested_by: PersonId | None = None
    notify: Notify = Notify.AUTO
    exchange: Exchange | None = None
    thread: str | None = None
    capability: str | None = None


class TaskAttached(Event, event_type="task.attached"):
    """The executor's reference for remote work: what lets Nestor follow it again after a restart."""

    task_id: str
    ref: str


class TaskProgressed(Event, event_type="task.progress"):
    task_id: str
    step: str


class TaskCancelRequested(Event, event_type="task.cancel.requested"):
    task_id: str


class TaskEnded(Event, event_type="task.ended"):
    """Terminal state; `status` is never RUNNING. A requested but unconfirmed stop ends as FAILED."""

    task_id: str
    status: TaskStatus
    result: str | None = None
    error: str | None = None
    duration_s: float
    files: tuple[BlobRef, ...] = ()  # what the executor made, to go with the answer that brings the result


class TaskDelivered(Event, event_type="task.delivered"):
    """The outcome reached the requester: it is never delivered again, even after a restart."""

    task_id: str
    address: Address


class TaskFileAdded(Event, event_type="task.file.added"):
    """A file the executor handed back while it worked (`attach_file`): it goes with the result."""

    task_id: str
    file: BlobRef
    name: str


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

    executor: str  # empty when the key matched none
    task_id: str | None  # None when the call matched no running task of that executor
    tool: str
    ok: bool
