"""The memory-recall suite end to end on a tiny household, with Nestor's own stores and a concept embedder: what a
turn finds, what it must never carry, and what a strategy that searches nothing misses."""

import json
from pathlib import Path

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.bench.recording import Cache
from nestor.bench.results import Run
from nestor.bench.runner import Plan, read_dataset, run_suite
from nestor.bench.suites.memory_recall import MemoryRecall
from nestor.bench.variants import load_variant
from nestor.core.i18n import Message
from nestor.modules.cognition.embedding import EmbeddingModel
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Registry
from nestor.testing.cognition import ConceptEmbedder
from nestor.testing.i18n import EchoLocalizer

HOUSEHOLD = [
    {"dataset": "memory-recall", "version": 1},
    {"memory": "m-veggie", "about": "lea", "text": "Léa est végétarienne."},
    {"memory": "m-tennis", "about": "hugo", "text": "Hugo joue au tennis le samedi."},
    {"episode": "e-lea", "people": ["lea"], "ended": "2026-10-18T20:10", "address": "telegram:7",
     "summary": "Léa a parlé d'un restaurant italien.", "topics": ["restaurant"]},
    {"episode": "e-hugo", "people": ["hugo"], "ended": "2026-10-19T20:10", "address": "telegram:8",
     "summary": "Hugo a parlé d'un restaurant japonais.", "topics": ["restaurant"]},
    {"case": "c-direct", "speaker": "hugo", "said": "Léa est végétarienne ?", "expected": ["m-veggie"],
     "kind": "direct"},
    {"case": "c-meaning", "speaker": "hugo", "said": "Je mets du jambon pour tout le monde ?",
     "expected": ["m-veggie"], "kind": "paraphrase"},
    {"case": "c-episode", "speaker": "lea", "said": "Tu te souviens du restaurant ?", "expected": ["e-lea"],
     "kind": "episode"},
    {"case": "c-private", "speaker": "lea", "said": "Et le restaurant japonais de Hugo ?", "avoid": ["e-hugo"],
     "kind": "private"},
]  # fmt: skip


class ConceptSettings(AdapterSettings):
    pass


CONCEPTS = Plugin(
    Family.MODEL,
    "concepts",
    ConceptSettings,
    lambda settings, name, services: ConceptEmbedder({"jambon": "meat", "vegetarienne": "meat"}),
    serves=EmbeddingModel,
)
SEARCHING = "models: {sens: {type: embedding, provider: concepts}}\n"
SEARCHING += "memory: {strategy: search, recent_episodes: 0, embedder: sens}\n"
NOTHING = "{strategy: recent, recent: 0, recent_episodes: 0, found_episodes: 0}"  # remembers, never carries
BLIND = f"models: {{sens: {{type: embedding, provider: concepts}}}}\nmemory: {NOTHING}\n"


async def bench(folder: Path, name: str, text: str) -> Run:
    suite = MemoryRecall()
    cases = folder / "cases.jsonl"
    cases.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in HOUSEHOLD))
    (folder / f"{name}.yaml").write_text(text)
    variant = load_variant(folder / f"{name}.yaml", suite, Registry([CONCEPTS]), EchoLocalizer(), environ={})
    dataset, info = read_dataset(suite, cases)
    (run,) = await run_suite(suite, dataset, info, [variant], Plan(), Cache(folder / "cache"))
    return run


async def test_a_turn_finds_what_matters_never_someone_elses_conversation_and_a_blind_strategy_says_what_it_missed(
    tmp_path: Path,
) -> None:
    searching = await bench(tmp_path, "searching", SEARCHING)
    got = {m.id: m.value for m in searching.summary.metrics}
    assert (got["recall"], got["complete"]) == (1.0, 1.0)
    assert got["recall-paraphrase"] == 1.0, "found by meaning: no word in common"
    assert got["others-conversations-injected"] == 0, "Hugo's conversation never reaches Léa's turn"
    assert searching.summary.findings == ()

    blind = await bench(tmp_path, "blind", BLIND)
    got = {m.id: m.value for m in blind.summary.metrics}
    assert got["recall"] == 0.0
    assert {f.case for f in blind.summary.findings} == {"c-direct", "c-meaning", "c-episode"}

    words = FluentLocalizer(catalogue_dirs(["nestor"]))
    shown = [Message.of(m.label) for m in searching.summary.metrics]
    shown += [m for f in blind.summary.findings for m in (Message.of(f.group), f.detail)]
    for locale in ("en", "fr"):
        assert all(words.format(m, locale) != m.id for m in shown), "every metric and finding is worded"


def test_the_shipped_dataset_can_be_scored() -> None:
    suite = MemoryRecall()
    dataset, info = read_dataset(suite, suite.dataset())
    assert info.cases == len(dataset.cases) > 0
    assert {c.data["kind"] for c in dataset.cases} >= {"paraphrase", "private", "episode"}
