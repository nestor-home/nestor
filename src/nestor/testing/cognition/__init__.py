"""Doubles and contract suites for the cognition module."""

from nestor.testing.cognition.delegation import ExecutorContract, ScriptedExecutor
from nestor.testing.cognition.model import ConversationModelContract, ScriptedModel

__all__ = ["ConversationModelContract", "ExecutorContract", "ScriptedExecutor", "ScriptedModel"]
