"""Embeddings in SQLite: one sqlite-vec table per embedding space."""

from nestor.adapters.storage.sqlite.cognition.vectors import SQLiteVectorIndex

__all__ = ["SQLiteVectorIndex"]
