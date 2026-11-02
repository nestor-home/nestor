"""Doubles and contract suites for embeddings: an embedder that knows a few concepts, and the behaviour every
`Embedder` and `VectorIndex` adapter must show."""

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager

from nestor.core import ProviderError
from nestor.modules.cognition.embedding import Embedder, EmbeddingSpace, Vector, VectorIndex

_WORD = re.compile(r"\w+")


def _fold(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.casefold())
    return _WORD.findall("".join(c for c in plain if not unicodedata.combining(c)))


class ConceptEmbedder(Embedder):
    """Deterministic: a text's vector counts the concepts its words stand for, so that different words of one
    meaning come close ("jambon" and "végétarienne" both stand for `meat`). Words it does not know count for
    nothing; a text with none is a vector of zeros but one, so that every vector has a direction."""

    name = "concept-embedder"

    def __init__(self, concepts: Mapping[str, str], *, model: str = "concepts", fail: bool = False) -> None:
        self._concepts = {word: concept for word, concept in concepts.items()}
        self._axes = {c: i for i, c in enumerate(sorted(set(concepts.values())))}
        self._space = EmbeddingSpace(model=model, dimensions=len(self._axes) + 1)
        self.fail = fail
        self.embedded: list[str] = []  # every text embedded, documents and questions

    @property
    def space(self) -> EmbeddingSpace:
        return self._space

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> Vector:
        return self._vector(text)

    def _vector(self, text: str) -> Vector:
        if self.fail:
            raise ProviderError(self.name, "embedder down", transient=True)
        self.embedded.append(text)
        vector = [0.0] * self._space.dimensions
        vector[-1] = 0.01  # nothing known: still a direction
        for word in _fold(text):
            if (concept := self._concepts.get(word)) is not None:
                vector[self._axes[concept]] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector]


class EmbedderContract:
    """Behaviour every `Embedder` adapter must show. Mix into a `Test…` class and implement `embedder()` and
    `unavailable_embedder()`."""

    def embedder(self) -> Embedder:
        raise NotImplementedError

    def unavailable_embedder(self) -> Embedder:
        raise NotImplementedError

    async def test_one_vector_per_text_in_order_of_the_space_dimension(self) -> None:
        async with self.embedder() as embedder:
            vectors = await embedder.embed_documents(["Léa est végétarienne.", "Le code du portail", "Bonjour"])
            question = await embedder.embed_query("Que mange Léa ?")
        assert len(vectors) == 3
        assert all(len(v) == embedder.space.dimensions for v in [*vectors, question])

    async def test_nothing_to_embed_is_no_vector(self) -> None:
        async with self.embedder() as embedder:
            assert await embedder.embed_documents([]) == []

    async def test_a_provider_failure_is_a_provider_error(self) -> None:
        async with self.unavailable_embedder() as embedder:
            try:
                await embedder.embed_query("Bonjour")
            except ProviderError:
                return
        raise AssertionError("an unreachable provider must raise ProviderError")


class VectorIndexContract:
    """Behaviour every `VectorIndex` adapter must show. Mix into a `Test…` class and implement `index()`, a
    started index on fresh storage (an async context manager)."""

    SPACE = EmbeddingSpace(model="m", dimensions=3)
    OTHER = EmbeddingSpace(model="m2", dimensions=2)

    def index(self) -> AbstractAsyncContextManager[VectorIndex]:
        """A started index on fresh storage, closed on leaving."""
        raise NotImplementedError

    async def test_the_nearest_items_of_a_kind_come_first(self) -> None:
        async with self.index() as index:
            await index.put(self.SPACE, "memory", "east", "f1", [1.0, 0.0, 0.0])
            await index.put(self.SPACE, "memory", "north", "f2", [0.0, 1.0, 0.0])
            await index.put(self.SPACE, "episode", "e", "f3", [1.0, 0.0, 0.0])
            found = await index.nearest(self.SPACE, "memory", [0.9, 0.2, 0.0], 5)
        assert [item for item, _ in found] == ["east", "north"]
        assert found[0][1] < found[1][1], "nearest first, by cosine distance"

    async def test_an_item_put_again_is_replaced_and_its_fingerprint_kept(self) -> None:
        async with self.index() as index:
            await index.put(self.SPACE, "memory", "a", "old", [1.0, 0.0, 0.0])
            await index.put(self.SPACE, "memory", "a", "new", [0.0, 0.0, 1.0])
            assert await index.fingerprints(self.SPACE, "memory") == {"a": "new"}
            assert [i for i, _ in await index.nearest(self.SPACE, "memory", [0.0, 0.0, 1.0], 5)] == ["a"]

    async def test_a_deleted_item_leaves_every_space_and_other_spaces_can_be_dropped(self) -> None:
        async with self.index() as index:
            await index.put(self.SPACE, "memory", "a", "f", [1.0, 0.0, 0.0])
            await index.put(self.OTHER, "memory", "a", "f", [1.0, 0.0])
            await index.put(self.OTHER, "memory", "b", "f", [0.0, 1.0])
            await index.delete("memory", "a")
            assert await index.fingerprints(self.SPACE, "memory") == {}
            assert await index.fingerprints(self.OTHER, "memory") == {"b": "f"}
            await index.keep_only(self.SPACE)
            assert await index.fingerprints(self.OTHER, "memory") == {}, "a dropped space starts empty"
