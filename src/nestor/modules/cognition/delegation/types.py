"""Values of delegated tasks: status, outcome and progress reporting."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Outcome:
    status: TaskStatus
    result: str | None = None
    error: str | None = None

    @classmethod
    def completed(cls, result: str) -> "Outcome":
        return cls(TaskStatus.COMPLETED, result=result)

    @classmethod
    def failed(cls, error: str) -> "Outcome":
        return cls(TaskStatus.FAILED, error=error)

    @classmethod
    def cancelled(cls) -> "Outcome":
        return cls(TaskStatus.CANCELLED)


type Progress = Callable[[str], None]
