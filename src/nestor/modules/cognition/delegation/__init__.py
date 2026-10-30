"""Delegation: long tasks handed to executors (Hermes, Codex…) while the conversation goes on.

Tasks are durable: the journal records them, so they survive the end of a conversation and a
restart, and their result is delivered once to whoever asked.
"""

from nestor.modules.cognition.delegation.events import (
    TaskAttached,
    TaskCancelRequested,
    TaskDelivered,
    TaskEnded,
    TaskProgressed,
    TaskStarted,
)
from nestor.modules.cognition.delegation.ports import Executor, RemoteExecutor
from nestor.modules.cognition.delegation.types import RESUME, Notify, Outcome, Progress, TaskStatus

__all__ = [
    "RESUME",
    "Executor",
    "Notify",
    "Outcome",
    "Progress",
    "RemoteExecutor",
    "TaskAttached",
    "TaskCancelRequested",
    "TaskDelivered",
    "TaskEnded",
    "TaskProgressed",
    "TaskStarted",
    "TaskStatus",
]
