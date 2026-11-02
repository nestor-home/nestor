"""Embeddings: models that turn text into vectors, and the index that finds the nearest. Optional: without an
embedder, search is by words only."""

from nestor.modules.cognition.embedding.ports import Embedder, VectorIndex
from nestor.modules.cognition.embedding.types import EmbeddingSpace, Vector

__all__ = ["Embedder", "EmbeddingSpace", "Vector", "VectorIndex"]
