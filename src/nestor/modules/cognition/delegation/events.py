"""Events of delegated tasks: the journal is the only record of a task, so it survives restarts."""

from nestor.core import Event, PersonId
from nestor.modules.channels import Address
from nestor.modules.cognition.delegation.types import Notify, TaskStatus


class TaskStarted(Event, event_type="task.started"):
    task_id: str
    objective: str
    executor: str
    origin: Address  # the conversation the task was asked in
    requested_by: PersonId | None = None
    notify: Notify = Notify.AUTO


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


class TaskDelivered(Event, event_type="task.delivered"):
    """The outcome reached the requester: it is never delivered again, even after a restart."""

    task_id: str
    address: Address
