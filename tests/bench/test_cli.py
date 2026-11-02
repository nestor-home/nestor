"""`nestor bench` from the command line: list, run (live and replayed), compare, report, in the person's
language, with the watch-triage suite and its deterministic fake model (no network)."""

import sys
from pathlib import Path

import pytest

from nestor.bench import BenchError, Suite, Suites
from nestor.bench.results import write_run
from nestor.cli import main

from .kit import Quiz, quiz_runs, variant


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    for algorithm in ("gate", "batch"):
        (tmp_path / f"{algorithm}.yaml").write_text(
            f"triage_model: {{kind: watch-triage-fake}}\nbench: {{name: fake-{algorithm}, algorithm: {algorithm}}}\n"
        )
    return tmp_path


def bench(*args: str) -> int:
    return main(["bench", *args])


def test_the_installed_suites_are_listed_with_their_description(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert bench("list") == 0
    assert "watch-triage: which incoming mails match a watch" in capsys.readouterr().out


def test_a_run_prints_the_comparison_and_writes_results_reports_and_the_cache(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bench("run", "watch-triage", "--variant", "gate.yaml", "--variant", "batch.yaml") == 0
    out = capsys.readouterr().out
    assert out.startswith(
        "watch-triage: 151 cases \N{MULTIPLICATION SIGN} 2 variants \N{MULTIPLICATION SIGN} 1 repetition\n"
    )
    assert "fake-gate: answered by fake/word-overlap-1" in out
    runs = sorted((here / "bench-results" / "watch-triage").iterdir())
    assert [p.name.split("-", 1)[1] for p in runs] == ["compare.html", "fake-batch", "fake-gate"]
    assert {p.name for p in runs[1].iterdir()} == {"results.json", "report.html"}
    assert any((here / ".bench-cache").rglob("*.json"))


def test_a_replayed_run_reports_the_same_quality_and_says_it_was_replayed(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bench("run", "watch-triage", "--variant", "gate.yaml", "--results", "live")
    live = [line for line in capsys.readouterr().out.splitlines() if line.startswith("matches")]
    assert (
        bench("run", "watch-triage", "--variant", "gate.yaml", "--replay", "--results", "again", "--concurrency", "2")
        == 0
    )
    out = capsys.readouterr().out
    assert "replayed from the cache" in out
    assert [line for line in out.splitlines() if line.startswith("matches")] == live


def test_runs_are_compared_and_reported_again_later(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bench("run", "watch-triage", "--variant", "gate.yaml", "--variant", "batch.yaml")
    gate, batch = sorted(p for p in (here / "bench-results" / "watch-triage").iterdir() if p.is_dir())[::-1]
    capsys.readouterr()
    assert bench("compare", str(gate), str(batch / "results.json"), "--out", "both.html") == 0
    assert "fake-gate" in capsys.readouterr().out
    assert "<svg" in (here / "both.html").read_text()
    (gate / "report.html").unlink()
    assert bench("report", str(gate)) == 0
    out = capsys.readouterr().out
    assert "Missed matches\n" in out
    assert "dropped by the keywords" in out
    assert (gate / "report.html").exists()


def test_the_command_speaks_the_language_of_the_environment(here: Path, capsys: pytest.CaptureFixture[str],
                                                           monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    bench("run", "watch-triage", "--variant", "gate.yaml")
    out = capsys.readouterr().out
    assert "151 cas \N{MULTIPLICATION SIGN} 1 variante \N{MULTIPLICATION SIGN} 1 répétition" in out
    assert "correspondances, rappel" in out


def test_a_failure_is_said_in_words_with_status_2(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert bench("run", "nope", "--variant", "gate.yaml") == 2
    assert "nestor bench: no suite named nope (installed: watch-triage)" in capsys.readouterr().err
    assert bench("run", "watch-triage", "--variant", "gate.yaml", "--replay") == 2
    assert "run it once without --replay" in capsys.readouterr().err
    assert bench("report", "nowhere") == 2


def test_a_repetition_count_below_one_is_refused(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        bench("run", "watch-triage", "--variant", "gate.yaml", "--repeat", "0")


def test_an_entry_point_that_is_not_a_suite_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class Entry:
        name, value, dist = "broken", "pkg:thing", None

        def load(self) -> object:
            return object()

    monkeypatch.setattr("nestor.bench.catalogue.entry_points", lambda group: [Entry()])
    with pytest.raises(Exception, match="not a nestor bench Suite"):
        Suites.installed()


def test_two_suites_cannot_share_a_name() -> None:
    suite = Suites.installed().get("watch-triage")
    assert isinstance(suite, Suite)
    with pytest.raises(Exception, match="two suites"):
        Suites([suite, suite])
    with pytest.raises(BenchError):
        Suites().get("watch-triage")


def test_a_terminal_sees_the_cases_counted_on_one_line(
    here: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    bench("run", "watch-triage", "--variant", "gate.yaml")
    err = capsys.readouterr().err
    assert err.startswith("\r1/151\r2/151")
    assert err.endswith("\r151/151\n")


async def test_a_run_where_nothing_went_wrong_reports_no_case_to_read(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    [run] = await quiz_runs(here, variant(here, Quiz()))
    write_run(run, here / "quiz")
    assert bench("report", str(here / "quiz" / "results.json")) == 0
    assert "Missed" not in capsys.readouterr().out
    assert "Nothing to read" in (here / "quiz" / "report.html").read_text()
