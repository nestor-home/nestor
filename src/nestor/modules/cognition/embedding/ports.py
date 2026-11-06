"""The embedding ports: the embedding model type, which turns text into vectors, and an index that finds the
nearest ones.

Vectors are a projection: the texts they come from live elsewhere (the journal, the memory store), so an index
can always be rebuilt, for instance after switching to another model.
"""

from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping, Sequence

from nestor.core import Component, Model, ModelType
from nestor.modules.cognition.embedding.types import EmbeddingSpace, Indexed, Vector


class EmbeddingModel(Model, ABC):
    """Turns texts into vectors of its `space`.

    Contract (checked by `nestor.testing.cognition.EmbeddingModelContract`):
    - `embed_documents` returns one vector per text, in order, each of `space.dimensions`;
    - `embed_query` embeds a question: many models expect it worded or prefixed apart from documents;
    - a provider failure raises `ProviderError`, never a vendor exception.
    """

    type = ModelType.EMBEDDING

    @property
    @abstractmethod
    def space(self) -> EmbeddingSpace: ...

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> Vector: ...


class VectorIndex(Component, ABC):
    """Vectors by space and kind of item (`memory`, later `episode`…), each kept with the fingerprint of the
    text it was computed from, so that only changed texts are embedded again.

    Contract (checked by `nestor.testing.cognition.VectorIndexContract`):
    - `put` inserts or replaces items' vectors in a space, all at once; `delete` removes items from every space;
    - `nearest` lists the closest items of a kind, nearest first, with their cosine distance;
    - `fingerprints` maps each item of a kind indexed in a space to its text's fingerprint;
    - `keep_only` drops every other space.
    """

    @abstractmethod
    async def put(self, space: EmbeddingSpace, kind: str, items: Sequence[Indexed]) -> None: ...

    @abstractmethod
    async def delete(self, kind: str, items: Collection[str]) -> None: ...

    @abstractmethod
    async def nearest(
        self, space: EmbeddingSpace, kind: str, vector: Vector, limit: int
    ) -> list[tuple[str, float]]: ...

    @abstractmethod
    async def fingerprints(self, space: EmbeddingSpace, kind: str) -> Mapping[str, str]: ...

    @abstractmethod
    async def keep_only(self, space: EmbeddingSpace) -> None: ...
