"""Running a suite: every case against every variant and repetition, measured, recorded and replayable."""

import json
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

from nestor.bench import BenchError, Trial
from nestor.bench.recording import Cache, MeasuredModel, Recording
from nestor.bench.results import Run
from nestor.bench.runner import Plan, _commit, read_dataset, run_suite
from nestor.core import ContractError
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    Message,
    ModelRequest,
    TextDelta,
    ToolCall,
    ToolCallRequested,
)

from .kit import BUILT, Oracle, Quiz, QuizKnobs, quiz_runs, variant, write_cases


def metric(run: Run, id: str) -> float | None:
    return next(m.value for m in run.summary.metrics if m.id == id)


async def test_every_case_runs_against_every_variant_and_repetition(tmp_path: Path) -> None:
    suite = Quiz()
    right = variant(tmp_path, suite)
    wrong = variant(
        tmp_path, suite, "wrong", "models: {m: {type: language, provider: oracle, replies: {two plus two: '5'}}}\n"
    )
    runs = await quiz_runs(tmp_path, right, wrong, plan=Plan(repeat=2))
    assert [r.variant for r in runs] == ["right", "wrong"]
    assert [(r.case, r.repetition) for r in runs[0].results] == [
        ("c1", 0), ("c2", 0), ("c3", 0), ("c1", 1), ("c2", 1), ("c3", 1),
    ]  # fmt: skip
    assert metric(runs[0], "accuracy") == 1.0
    assert metric(runs[1], "accuracy") == 0.0
    assert [f.case for f in runs[1].summary.findings] == ["c1", "c2", "c3", "c1", "c2", "c3"]


async def test_a_run_records_the_model_that_answered_tokens_cost_and_calls(tmp_path: Path) -> None:
    suite = Quiz()
    text = "models: {m: {type: language, provider: oracle, served: oracle/v1-2026-10, replies: {two plus two: '4'}}}\n"
    [run] = await quiz_runs(tmp_path, variant(tmp_path, suite, "served", text))
    assert run.served_models == ("oracle/v1-2026-10",)
    first = run.results[1].calls[0]
    assert (first.role, first.input_tokens, first.output_tokens, first.cost) == ("watches", 12, 1, 0.001)
    assert metric(run, "calls-per-case") == 1
    assert metric(run, "cost-per-1000-cases") == pytest.approx(1.0)
    assert sum(c.cold for r in run.results for c in r.calls) == 1, "only the very first call opens the connection"


async def test_a_replayed_run_scores_the_same_without_calling_the_model(tmp_path: Path) -> None:
    suite = Quiz()
    [live] = await quiz_runs(tmp_path, variant(tmp_path, suite))
    BUILT.clear()
    [replayed] = await quiz_runs(tmp_path, variant(tmp_path, suite), plan=Plan(replay=True))
    assert BUILT[0].requests == []
    timeless = {"case-latency-p50", "case-latency-p95"}  # the cases themselves are timed again
    assert [m for m in replayed.summary.metrics if m.id not in timeless] == [
        m for m in live.summary.metrics if m.id not in timeless
    ]
    assert (metric(replayed, "case-latency-p95") or 0) >= (metric(live, "call-latency-p95") or 1)
    assert all(c.replayed for r in replayed.results for c in r.calls)
    assert replayed.replay


async def test_replaying_a_case_never_recorded_stops_the_run_and_names_it(tmp_path: Path) -> None:
    suite = Quiz()
    await quiz_runs(tmp_path, variant(tmp_path, suite))
    with pytest.raises(BenchError) as raised:
        await quiz_runs(tmp_path, variant(tmp_path, suite), plan=Plan(replay=True, repeat=2))
    assert raised.value.message.id == "bench-no-recording"
    assert raised.value.message.args["role"] == "watches"


async def test_another_seed_or_model_is_not_answered_from_the_recordings_of_the_first(tmp_path: Path) -> None:
    suite = Quiz()
    await quiz_runs(tmp_path, variant(tmp_path, suite))
    with pytest.raises(BenchError):
        await quiz_runs(tmp_path, variant(tmp_path, suite), plan=Plan(replay=True, seed=1))
    other = "models: {m: {type: language, provider: oracle, served: other, replies: {}}}\n"
    with pytest.raises(BenchError):
        await quiz_runs(tmp_path, variant(tmp_path, suite, "other", other), plan=Plan(replay=True))


async def test_a_provider_outage_is_counted_and_never_recorded_as_an_answer(tmp_path: Path) -> None:
    suite = Quiz()
    text = (
        "models: {m: {type: language, provider: oracle, fail_on: two plus two, replies: {capital of France: Paris}}}\n"
    )
    [run] = await quiz_runs(tmp_path, variant(tmp_path, suite, "flaky", text))
    assert metric(run, "provider-errors") == 1
    assert run.results[1].output == {"reply": ""}
    assert "overloaded" in (run.results[1].calls[0].error or "")
    with pytest.raises(BenchError):  # the failed call left nothing to replay
        await quiz_runs(tmp_path, variant(tmp_path, suite, "flaky", text), plan=Plan(replay=True))


async def test_the_order_of_cases_follows_the_seed(tmp_path: Path) -> None:
    suite = Quiz()

    async def order(seed: int) -> list[str]:
        BUILT.clear()
        await quiz_runs(tmp_path, variant(tmp_path, suite), plan=Plan(seed=seed, concurrency=1))
        return [r.messages[-1].content for r in BUILT[0].requests]

    assert await order(7) == await order(7)
    assert sorted(await order(7)) == sorted(await order(8))
    assert {tuple(await order(s)) for s in range(6)} != {tuple(await order(0))}


async def test_two_variants_with_the_same_name_are_refused(tmp_path: Path) -> None:
    suite = Quiz()
    with pytest.raises(BenchError) as raised:
        await quiz_runs(tmp_path, variant(tmp_path, suite), variant(tmp_path, suite))
    assert raised.value.message.id == "bench-same-variant-name"


def test_a_dataset_line_that_is_not_a_json_object_is_refused_with_its_number(tmp_path: Path) -> None:
    path = write_cases(tmp_path)
    path.write_text(path.read_text() + "\n[1, 2]\n")
    with pytest.raises(BenchError) as raised:
        read_dataset(Quiz(), path)
    assert raised.value.message.args["line"] == 5
    path.write_text('{"case": "c1"\n')
    with pytest.raises(BenchError, match="bench-dataset-invalid-line"):
        read_dataset(Quiz(), path)
    with pytest.raises(BenchError, match="bench-dataset-unreadable"):
        read_dataset(Quiz(), tmp_path / "missing.jsonl")


def test_the_dataset_hash_changes_with_its_content(tmp_path: Path) -> None:
    path = write_cases(tmp_path)
    _, first = read_dataset(Quiz(), path)
    path.write_text(path.read_text().replace("Paris", "Lyon"))
    _, second = read_dataset(Quiz(), path)
    assert first.sha256 != second.sha256
    assert (first.cases, first.version) == (3, 1)


async def test_a_damaged_recording_is_reported_with_its_file(tmp_path: Path) -> None:
    suite = Quiz()
    await quiz_runs(tmp_path, variant(tmp_path, suite))
    for file in (tmp_path / "cache").rglob("*.json"):
        file.write_text(json.dumps({"outputs": "nope"}))
    with pytest.raises(BenchError) as raised:
        await quiz_runs(tmp_path, variant(tmp_path, suite), plan=Plan(replay=True))
    assert raised.value.message.id == "bench-cache-unreadable"


def test_a_source_git_does_not_track_has_no_commit_and_a_changed_one_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {"ls-files": (1, ""), "rev-parse": (0, "a" * 40), "status": (0, " M cli.py")}

    def git(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        code, out = answers[command[3]]
        return subprocess.CompletedProcess(command, code, out, "")

    monkeypatch.setattr("nestor.bench.runner.subprocess.run", git)
    assert _commit() is None
    answers["ls-files"] = (0, "runner.py")
    assert _commit() == "a" * 40 + "+dirty"
    answers["status"] = (0, "")
    assert _commit() == "a" * 40


async def test_results_name_the_nestor_version_and_the_commit_of_this_source(tmp_path: Path) -> None:
    suite = Quiz()
    dataset, info = read_dataset(suite, write_cases(tmp_path))
    [run] = await run_suite(suite, dataset, info, [variant(tmp_path, suite)], Plan(), Cache(tmp_path / "c"))
    assert run.nestor == version("nestor-home")
    assert run.commit is not None and len(run.commit.removesuffix("+dirty")) == 40, "this source is tracked by git"


def test_a_recording_keeps_tool_calls_and_a_reply_without_usage(tmp_path: Path) -> None:
    outputs = (
        TextDelta("Je regarde."),
        ToolCallRequested(ToolCall("call-1", "create_watch", {"what": "le colis"})),
        Finished(FinishReason.TOOL_CALLS),
    )
    cache = Cache(tmp_path)
    cache.write("ab" * 32, Recording(outputs=outputs, latency_s=0.2, first_output_s=0.1, cold=True))
    assert cache.read("ab" * 32) == Recording(outputs=outputs, latency_s=0.2, first_output_s=0.1, cold=True)


async def test_a_measured_model_called_outside_a_case_is_a_mistake_of_the_suite(tmp_path: Path) -> None:
    model = MeasuredModel(Oracle({}, "x"), role="model", described={}, cache=Cache(tmp_path), replay=False)
    with pytest.raises(ContractError, match="outside of a bench case"):
        await anext(model.stream(ModelRequest(messages=(Message.user("?"),))))


async def test_a_trial_refuses_a_model_its_suite_did_not_declare(tmp_path: Path) -> None:
    suite = Quiz()
    trial = Trial(
        variant="v", knobs=QuizKnobs(), config=variant(tmp_path, suite).config, models={}, repetition=0, seed=0
    )
    with pytest.raises(ContractError, match="did not declare"):
        trial.model("watches")
