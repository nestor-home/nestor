"""Events of delegated tasks."""

from nestor.core import Event
from nestor.modules.cognition.delegation.types import TaskStatus


class TaskStarted(Event, event_type="task.started"):
    task_id: str
    objective: str
    executor: str


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
