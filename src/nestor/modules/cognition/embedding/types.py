"""An embedding space: which vectors can be compared with which."""

import hashlib
from dataclasses import dataclass
from typing import NamedTuple

type Vector = list[float]


def fingerprint(text: str) -> str:
    """A short stable digest: of an embedded text, to embed it again only when it changes; of a space."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class Indexed(NamedTuple):
    item: str
    fingerprint: str  # of the text the vector was computed from
    vector: Vector


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
        return fingerprint(f"{self.model}\0{self.dimensions}\0{self.query_prefix}\0{self.document_prefix}")
