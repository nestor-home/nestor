"""Runs on disk and their reports: everything survives the round trip, the page is self-contained."""

import dataclasses
import json
import re
from pathlib import Path

import pytest

from nestor.bench import BenchError, Better, Metric, Unit
from nestor.bench.report import page, table, value_text
from nestor.bench.results import Run, read_run, write_run
from nestor.core.i18n import Message

from .kit import Quiz, quiz_runs, variant


def render(message: Message) -> str:
    args = ", ".join(f"{k}={v}" for k, v in sorted(message.args.items()))
    return f"{message.id}({args})" if args else message.id


@pytest.fixture
async def runs(tmp_path: Path) -> list[Run]:
    suite = Quiz()
    wrong = "models: {m: {kind: oracle, replies: {two plus two: '<b>5</b>'}}}\nbench: {name: <script>x</script>}\n"
    return await quiz_runs(tmp_path, variant(tmp_path, suite), variant(tmp_path, suite, "wrong", wrong))


async def test_a_run_reads_back_as_it_was_written(tmp_path: Path, runs: list[Run]) -> None:
    for run in runs:
        written = write_run(run, tmp_path / "out" / run.folder_name())
        assert read_run(written.parent) == run
        assert read_run(written) == run


async def test_a_folder_name_is_safe_whatever_the_variant_is_called(runs: list[Run]) -> None:
    assert re.fullmatch(r"\d{8}T\d{6}-[A-Za-z0-9._-]+", runs[1].folder_name())


@pytest.mark.parametrize("content", ["not json", json.dumps({"format": 99}), json.dumps({"format": 1})])
def test_something_that_is_not_a_run_is_refused(tmp_path: Path, content: str) -> None:
    (tmp_path / "results.json").write_text(content)
    with pytest.raises(BenchError, match="bench-results-unreadable"):
        read_run(tmp_path)


async def test_the_table_aligns_runs_side_by_side_and_marks_the_best(runs: list[Run]) -> None:
    lines = table(runs, render).splitlines()
    accuracy = next(line for line in lines if line.startswith("bench-watch-triage-matches-f1"))
    assert accuracy.split()[1:] == ["1.000*", "0.000"]
    assert len({len(line) for line in lines[2:5]}) == 1, "header, rule and rows have the same width"
    assert any(line.startswith("bench-table-best") for line in lines)


async def test_the_table_warns_when_runs_did_not_use_the_same_dataset(runs: list[Run]) -> None:
    other = dataclasses.replace(runs[1], dataset=dataclasses.replace(runs[1].dataset, sha256="0" * 64))
    assert "bench-different-datasets" in table([runs[0], other], render)
    assert "bench-different-datasets" not in table(runs, render)


async def test_the_html_page_loads_nothing_from_the_network_and_escapes_what_it_shows(runs: list[Run]) -> None:
    html = page(runs, render, lang="fr")
    assert not re.search(r"""(src|href)\s*=\s*["']?https?:""", html)
    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert '<html lang="fr">' in html
    assert html.count("<figure>") == sum(m.value is not None for m in runs[0].summary.metrics)


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (None, Unit.RATIO, "-"),
        (0.91234, Unit.RATIO, "0.912"),
        (0.4321, Unit.DURATION, "432 ms"),
        (12.5, Unit.DURATION, "12.5 s"),
        (3.0, Unit.COUNT, "3"),
        (2.5, Unit.COUNT, "2.50"),
        (0.00123, Unit.COST, "0.0012"),
        (26_534_365, Unit.BYTES, "26.5 MB"),
    ],
)
def test_values_are_shown_in_their_unit(value: float | None, unit: Unit, text: str) -> None:
    assert value_text(value, unit) == text


async def test_a_tie_or_a_metric_without_direction_marks_no_best(runs: list[Run]) -> None:
    tied = Metric(id="same", label="same", value=1.0, unit=Unit.COUNT, better=Better.LOWER)
    plain = Metric(id="plain", label="plain", value=1.0, unit=Unit.COUNT)
    first = dataclasses.replace(runs[0], summary=dataclasses.replace(runs[0].summary, metrics=(tied, plain)))
    second = dataclasses.replace(first, variant="other", summary=dataclasses.replace(first.summary, metrics=(tied,)))
    shown = table([first, second], render)
    assert "*" not in shown.split("bench-table-header")[1].split("bench-table-run")[0]
    assert re.search(r"^plain\s+1\s+-$", shown, re.MULTILINE)
