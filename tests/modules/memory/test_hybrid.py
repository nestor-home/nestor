"""Hybrid recall: memories found by words and by meaning, fused; vectors kept in step with the memories, rebuilt
for a new model, and search by words when the embedder is down."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from nestor.core import PersonId, ProviderError
from nestor.modules.cognition.embedding import Vector
from nestor.modules.memory import Memories
from nestor.modules.memory import index as index_module
from nestor.modules.memory.service import fused
from nestor.runtime.app import open_memories
from nestor.testing.cognition import ConceptEmbedder

MATHILDE = PersonId("mathilde")
CONCEPTS = {
    "jambon": "meat",
    "viande": "meat",
    "vegetarienne": "meat",
    "saucisse": "meat",
    "portail": "gate",
    "code": "gate",
    "cle": "gate",
}


async def settled(memories: Memories) -> None:
    """Until the vectors caught up with the memories: they are embedded in the background."""
    assert memories.index is not None
    await memories.index.settled()


async def remembered(memories: Memories) -> dict[str, str]:
    texts = ("Mathilde est végétarienne.", "Le portail s'ouvre avec le code 1234.", "Le chat s'appelle Moustache.")
    ids = {}
    for text in texts:
        ids[text.split()[1]] = (await memories.remember(text, about=MATHILDE if "Mathilde" in text else None)).id
    await settled(memories)
    return ids


async def test_a_paraphrase_without_a_word_in_common_is_found_by_meaning(tmp_path: Path) -> None:
    embedder = ConceptEmbedder(CONCEPTS)
    async with embedder, open_memories(tmp_path, embedder) as memories:
        ids = await remembered(memories)
        by_meaning = await memories.recall("Je mets du jambon ?", limit=2)
        by_words = await memories.recall("Moustache", limit=1)
    assert by_meaning[0].id == ids["est"], "found by meaning, ranked first"
    assert [m.id for m in by_words] == [ids["chat"]], "and still by words"


async def test_without_an_embedder_or_while_it_is_down_memories_are_found_by_their_words(tmp_path: Path) -> None:
    embedder = ConceptEmbedder(CONCEPTS)
    async with embedder, open_memories(tmp_path, embedder) as memories:
        ids = await remembered(memories)
        embedder.fail = True
        assert [m.id for m in await memories.recall("code du portail")] == [ids["portail"]]
        assert await memories.recall("jambon") == [], "no word in common, no meaning: nothing"
        await memories.remember("Le code du garage est 5678.")  # remembered all the same, embedded later
        await settled(memories)  # the attempt failed: it is tried again at the next change or start
    async with open_memories(tmp_path) as words_only:
        assert len(await words_only.recall("code")) == 2


async def test_vectors_follow_corrections_and_forgetting(tmp_path: Path) -> None:
    embedder = ConceptEmbedder(CONCEPTS)
    async with embedder, open_memories(tmp_path, embedder) as memories:
        ids = await remembered(memories)
        await memories.correct(ids["chat"], "Le chat mange de la viande crue.")
        await settled(memories)
        assert ids["chat"] in [m.id for m in await memories.recall("saucisse", limit=3)]
        await memories.forget(ids["est"])
        await settled(memories)
        assert ids["est"] not in [m.id for m in await memories.recall("jambon", limit=3)]


async def test_a_new_model_embeds_every_memory_again_and_an_unchanged_one_is_never_embedded_twice(
    tmp_path: Path,
) -> None:
    first = ConceptEmbedder(CONCEPTS, model="first")
    async with first, open_memories(tmp_path, first) as memories:
        await remembered(memories)
        assert memories.index is not None
        assert await memories.index.reconcile() == 0, "every memory already has its vector"
    second = ConceptEmbedder(CONCEPTS, model="second")
    async with second, open_memories(tmp_path, second) as memories:
        await settled(memories)  # reconciled at start: another space, everything again
        assert memories.index is not None
        assert len(await memories.index.vectors.fingerprints(second.space, "memory")) == 3
        assert len(await memories.index.vectors.fingerprints(first.space, "memory")) == 0, "the old space is dropped"
        assert (await memories.recall("jambon", limit=1))[0].text == "Mathilde est végétarienne."


def test_fusion_ranks_first_what_both_lists_found() -> None:
    from nestor.modules.memory import Memory

    a, b, c = (Memory(id=i, text=i) for i in "abc")
    assert [m.id for m in fused([[a, b], [c, b]])] == ["b", "a", "c"]


class Flaky(ConceptEmbedder):
    """Fails its documents call number `failing` (1-based) with `error`, then works again."""

    def __init__(self, failing: int, error: Exception) -> None:
        super().__init__(CONCEPTS)
        self.calls, self.failing, self.error = 0, failing, error

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        self.calls += 1
        if self.calls == self.failing:
            raise self.error
        return await super().embed_documents(texts)


async def test_the_batches_embedded_before_a_failure_are_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(index_module, "BATCH", 2)
    async with open_memories(tmp_path) as plain:
        for n in range(5):
            await plain.remember(f"Souvenir numéro {n}.")
    embedder = Flaky(failing=2, error=ProviderError("flaky", "rate limited", transient=True))
    async with embedder, open_memories(tmp_path, embedder) as memories:
        await settled(memories)  # reconciled at start: the first batch went in, the second failed
        assert memories.index is not None
        assert len(await memories.index.vectors.fingerprints(embedder.space, "memory")) == 2
        assert await memories.index.reconcile() == 3, "only what is missing is embedded again"


async def test_an_unexpected_failure_never_stops_the_index_from_keeping_up(tmp_path: Path) -> None:
    embedder = Flaky(failing=1, error=RuntimeError("a bug somewhere"))  # nothing to embed at start
    async with embedder, open_memories(tmp_path, embedder) as memories:
        await settled(memories)
        first = await memories.remember("Mathilde est végétarienne.")  # its catch-up fails unexpectedly
        await settled(memories)
        await memories.remember("Le portail s'ouvre avec le code 1234.")
        await settled(memories)  # the worker is still there
        assert memories.index is not None
        indexed = await memories.index.vectors.fingerprints(embedder.space, "memory")
    assert first.id not in indexed and len(indexed) == 1, "the failed one waits for the next start"
