"""Values of delegated tasks: status, outcome, progress reporting and how to deliver the result."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from nestor.core import Capability
from nestor.modules.channels import Attachment

RESUME = Capability("delegation.resume")


class TaskStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Notify(StrEnum):
    """Where the requester wants the result."""

    AUTO = "auto"  # in the conversation if they are still in it, else where they can be reached
    MESSAGE = "message"  # in writing, wherever they are ("écris-moi quand c'est fini")


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a task ended: its report, or why it failed. `files` are what the executor made for the requester (a
    document, a picture): they go with the answer that brings the result, where the channel can send them."""

    status: TaskStatus
    result: str | None = None
    error: str | None = None
    files: tuple[Attachment, ...] = ()

    @classmethod
    def completed(cls, result: str, files: tuple[Attachment, ...] = ()) -> "Outcome":
        return cls(TaskStatus.COMPLETED, result=result, files=files)

    @classmethod
    def failed(cls, error: str) -> "Outcome":
        return cls(TaskStatus.FAILED, error=error)

    @classmethod
    def cancelled(cls) -> "Outcome":
        return cls(TaskStatus.CANCELLED)


def _ignore(_: str) -> None:
    return None


class Progress:
    """How an executor reports while it works: steps (`progress("searching…")`) and, for remote
    work, the handle that lets Nestor follow it again after a restart (`progress.attach(ref)`)."""

    def __init__(self, on_step: Callable[[str], None] = _ignore, on_attach: Callable[[str], None] = _ignore) -> None:
        self._on_step, self._on_attach = on_step, on_attach

    def __call__(self, step: str) -> None:
        self._on_step(step)

    def attach(self, ref: str) -> None:
        self._on_attach(ref)
