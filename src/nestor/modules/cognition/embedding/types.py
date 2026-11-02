"""An embedding space: which vectors can be compared with which."""

import hashlib
from dataclasses import dataclass

type Vector = list[float]


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingSpace:
    """What a vector means: the model that served it, its dimension, and the prefixes questions and documents
    were given. Two spaces never mix; a profile's name in `models` plays no part, so renaming a model keeps its
    vectors and changing what it serves starts a new space."""

    model: str
    dimensions: int
    query_prefix: str = ""
    document_prefix: str = ""

    @property
    def id(self) -> str:
        """A short stable identifier, safe in a table name."""
        key = f"{self.model}\0{self.dimensions}\0{self.query_prefix}\0{self.document_prefix}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
