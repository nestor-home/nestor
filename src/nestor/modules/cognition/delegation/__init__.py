"""Delegation: long tasks handed to executors (Hermes, Codex…) while the conversation goes on."""

from nestor.modules.cognition.delegation.events import TaskCancelRequested, TaskEnded, TaskProgressed, TaskStarted
from nestor.modules.cognition.delegation.ports import Executor
from nestor.modules.cognition.delegation.types import Outcome, Progress, TaskStatus

__all__ = [
    "Executor",
    "Outcome",
    "Progress",
    "TaskCancelRequested",
    "TaskEnded",
    "TaskProgressed",
    "TaskStarted",
    "TaskStatus",
]
