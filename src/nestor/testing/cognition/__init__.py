"""Doubles and contract suites for the cognition module."""

from nestor.testing.cognition.delegation import (
    ExecutorContract,
    FakeRemote,
    RemoteExecutorContract,
    ScriptedExecutor,
    ScriptedRemoteExecutor,
)
from nestor.testing.cognition.embedding import ConceptEmbedder, EmbeddingModelContract, VectorIndexContract
from nestor.testing.cognition.model import LanguageModelContract, ScriptedModel

__all__ = [
    "ConceptEmbedder",
    "EmbeddingModelContract",
    "ExecutorContract",
    "FakeRemote",
    "LanguageModelContract",
    "RemoteExecutorContract",
    "ScriptedExecutor",
    "ScriptedModel",
    "ScriptedRemoteExecutor",
    "VectorIndexContract",
]
