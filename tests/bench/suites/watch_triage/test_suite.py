"""The watch-triage suite: its dataset, its scoring, and an end-to-end run on the fake model."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.bench import BenchError, CaseResult
from nestor.bench.recording import Cache
from nestor.bench.runner import Plan, read_dataset, run_suite
from nestor.bench.suites.watch_triage import suite
from nestor.bench.variants import load_variant
from nestor.core.i18n import Message
from nestor.runtime.plugins import Registry
from nestor.testing.i18n import EchoLocalizer


def test_the_shipped_dataset_holds_bilingual_mails_and_imperfect_watches() -> None:
    dataset, info = read_dataset(suite, suite.dataset())
    assert info.cases >= 150
    assert len(dataset.shared) >= 10
    assert {c.data["lang"] for c in dataset.cases} == {"en", "fr"}
    labels = [label for c in dataset.cases for label in c.data["expected"].items()]
    for watch in dataset.shared:
        assert sum(w == watch.id for w, _ in labels) >= 2, f"{watch.id} is matched by fewer than two mails"
    assert sum(label == "urgent" for _, label in labels) >= 10
    assert sum(not c.data["expected"] for c in dataset.cases) > 100, "most mail matches nothing"


def records(*lines: dict[str, object]) -> list[dict[str, object]]:
    return [{"dataset": "watch-triage", "version": 1}, {"watch": "w-a", "what": "a"}, *lines]


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([{"dataset": "other", "version": 1}], "bench-watch-triage-no-header"),
        (records({"case": "m1"}), "bench-watch-triage-bad-record"),
        (records({"case": "m1", "title": "t", "expected": {"w-b": "match"}}), "bench-watch-triage-bad-label"),
        (records({"case": "m1", "title": "t", "expected": {"w-a": "maybe"}}), "bench-watch-triage-bad-label"),
        (records({"case": "m1", "title": "t", "expected": ["w-a"]}), "bench-watch-triage-bad-label"),
    ],
)
def test_a_dataset_the_suite_cannot_score_is_refused(lines: list[dict[str, object]], message: str) -> None:
    with pytest.raises(BenchError) as raised:
        suite.load(lines)
    assert raised.value.message.id == message


def decided(case: str, repetition: int, **decisions: Mapping[str, object]) -> CaseResult:
    output = {"decisions": [{"watch": w, **d} for w, d in decisions.items()]}
    return CaseResult(case=case, repetition=repetition, output=output)


def test_scores_count_every_mail_and_watch_pair_and_name_what_went_wrong() -> None:
    dataset = suite.load(
        records(
            {"watch": "w-b", "what": "b"},
            {"case": "m1", "title": "for a", "expected": {"w-a": "urgent"}},
            {"case": "m2", "title": "for b", "expected": {"w-b": "match"}},
            {"case": "m3", "title": "for none"},
        )
    )
    results = [
        decided("m1", 0, **{"w-a": {"matches": True, "urgent": False}}),
        decided("m2", 0, **{"w-b": {"matches": False}}),
        decided("m3", 0, **{"w-a": {"matches": True}}),
        decided("m1", 1, **{"w-a": {"matches": True, "urgent": True}}),
        decided("m2", 1, **{"w-b": {"matches": False}}),
        decided("m3", 1, **{"w-a": {"unsorted": True}}),
    ]
    summary = suite.summarise(dataset, results)
    metrics = {m.id: m.value for m in summary.metrics}
    assert metrics["matches-precision"] == pytest.approx(2 / 3)
    assert metrics["matches-recall"] == pytest.approx(2 / 4)
    assert (metrics["urgent-precision"], metrics["urgent-recall"]) == (1.0, 0.5)
    assert (metrics["missed"], metrics["false-alarms"], metrics["unsorted"]) == (1.0, 0.5, 0.5)
    found = {(f.group, f.case, f.detail.args["times"]) for f in summary.findings}
    assert found == {
        ("bench-watch-triage-missed-list", "m2", 2),
        ("bench-watch-triage-false-alarms-list", "m3", 1),
        ("bench-watch-triage-not-urgent-list", "m1", 1),
    }


async def test_every_algorithm_runs_end_to_end_on_the_fake_model_the_same_way_twice(tmp_path: Path) -> None:
    registry = Registry(suite.plugins)
    variants = []
    for algorithm in ("batch", "per-watch"):
        path = tmp_path / f"{algorithm}.yaml"
        path.write_text(json.dumps({"triage_model": {"kind": "watch-triage-fake"}, "bench": {"algorithm": algorithm}}))
        variants.append(load_variant(path, suite, registry, EchoLocalizer(), environ={}))
    dataset, info = read_dataset(suite, suite.dataset())
    first = await run_suite(suite, dataset, info, variants, Plan(), Cache(tmp_path / "cache"))
    again = await run_suite(suite, dataset, info, variants, Plan(seed=3), Cache(tmp_path / "cache"))
    quality = [[m for m in run.summary.metrics if "latency" not in m.id] for run in first]
    assert quality == [[m for m in run.summary.metrics if "latency" not in m.id] for run in again]
    calls = {run.variant: next(m.value or 0 for m in run.summary.metrics if m.id == "calls-per-case") for run in first}
    assert calls["batch"] == 1 < calls["per-watch"]
    assert all(run.served_models == ("fake/word-overlap-1",) for run in first)
    words = FluentLocalizer(catalogue_dirs(["nestor"]))
    shown = [Message.of(m.label) for run in first for m in run.summary.metrics]
    shown += [m for run in first for f in run.summary.findings for m in (Message.of(f.group), f.detail)]
    for locale in ("en", "fr"):
        assert all(words.format(m, locale) != m.id for m in shown), "every metric and finding is worded"
