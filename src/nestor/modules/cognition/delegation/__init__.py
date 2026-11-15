"""Delegation: long tasks handed to executors (Hermes, Codex…) while the conversation goes on.

Tasks are durable: the journal records them, so they survive the end of a conversation and a
restart, and their result is delivered once to whoever asked. While it works, an executor may reach Nestor's MCP
server for its task (`ExecutorKeys`, `Assignment`).
"""

from nestor.modules.cognition.delegation.events import (
    ExecutorCalled,
    ExecutorKeyIssued,
    ExecutorKeyRevoked,
    TaskAttached,
    TaskCancelRequested,
    TaskDelivered,
    TaskEnded,
    TaskFileAdded,
    TaskProgressed,
    TaskStarted,
)
from nestor.modules.cognition.delegation.keys import ExecutorKeys
from nestor.modules.cognition.delegation.ports import Executor, RemoteExecutor
from nestor.modules.cognition.delegation.types import (
    RESUME,
    Assignment,
    NestorAccess,
    NestorTools,
    Notify,
    Outcome,
    Progress,
    TaskStatus,
)

__all__ = [
    "RESUME",
    "Assignment",
    "Executor",
    "ExecutorCalled",
    "ExecutorKeyIssued",
    "ExecutorKeyRevoked",
    "ExecutorKeys",
    "NestorAccess",
    "NestorTools",
    "Notify",
    "Outcome",
    "Progress",
    "RemoteExecutor",
    "TaskAttached",
    "TaskCancelRequested",
    "TaskDelivered",
    "TaskEnded",
    "TaskFileAdded",
    "TaskProgressed",
    "TaskStarted",
    "TaskStatus",
]
