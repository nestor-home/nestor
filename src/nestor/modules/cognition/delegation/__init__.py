"""Delegation: tasks handed to executors (Hermes, Codex, Claude Code…) while the conversation goes on.

A task is a durable thread with its executor, a turn at a time: started from a conversation, given more instructions
while it works (steering) or after (an answer to its question, a follow-up days later), stopped, renamed, archived.
The journal records it, so it survives the end of a conversation and a restart, and what each turn comes back with is
delivered once to its owner. While a turn works, its executor may reach Nestor's MCP server for it (`ExecutorKeys`,
`Assignment`).
"""

from nestor.modules.cognition.delegation.events import (
    ExecutorCalled,
    ExecutorKeyIssued,
    ExecutorKeyRevoked,
    TaskArchived,
    TaskCreated,
    TaskNoted,
    TaskReminded,
    TaskRenamed,
    TaskSteered,
    TurnAttached,
    TurnDelivered,
    TurnEnded,
    TurnFileAdded,
    TurnStarted,
    TurnStepped,
    TurnStopRequested,
)
from nestor.modules.cognition.delegation.keys import ExecutorKeys
from nestor.modules.cognition.delegation.ports import Executor, RemoteExecutor
from nestor.modules.cognition.delegation.service import Delivery, Directed, Steer, Task, TaskManager, Turn
from nestor.modules.cognition.delegation.types import (
    CONTINUE,
    READ_TURNS,
    RESUME,
    STEER,
    STEPS,
    TURN_CHARS,
    Assignment,
    Handle,
    NestorAccess,
    NestorTools,
    Notify,
    Outcome,
    Progress,
    TaskState,
    TurnStatus,
    step_line,
)

__all__ = [
    "CONTINUE",
    "READ_TURNS",
    "RESUME",
    "STEER",
    "STEPS",
    "TURN_CHARS",
    "Assignment",
    "Delivery",
    "Directed",
    "Executor",
    "ExecutorCalled",
    "ExecutorKeyIssued",
    "ExecutorKeyRevoked",
    "ExecutorKeys",
    "Handle",
    "NestorAccess",
    "NestorTools",
    "Notify",
    "Outcome",
    "Progress",
    "RemoteExecutor",
    "Steer",
    "Task",
    "TaskArchived",
    "TaskCreated",
    "TaskManager",
    "TaskNoted",
    "TaskReminded",
    "TaskRenamed",
    "TaskState",
    "TaskSteered",
    "Turn",
    "TurnAttached",
    "TurnDelivered",
    "TurnEnded",
    "TurnFileAdded",
    "TurnStarted",
    "TurnStatus",
    "TurnStepped",
    "TurnStopRequested",
    "step_line",
]
