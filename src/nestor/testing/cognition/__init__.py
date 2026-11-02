"""Doubles and contract suites for the cognition module."""

from nestor.testing.cognition.delegation import (
    ExecutorContract,
    FakeRemote,
    RemoteExecutorContract,
    ScriptedExecutor,
    ScriptedRemoteExecutor,
)
from nestor.testing.cognition.embedding import ConceptEmbedder, EmbedderContract, VectorIndexContract
from nestor.testing.cognition.model import ConversationModelContract, ScriptedModel

__all__ = [
    "ConceptEmbedder",
    "ConversationModelContract",
    "EmbedderContract",
    "ExecutorContract",
    "FakeRemote",
    "RemoteExecutorContract",
    "ScriptedExecutor",
    "ScriptedModel",
    "ScriptedRemoteExecutor",
    "VectorIndexContract",
]
