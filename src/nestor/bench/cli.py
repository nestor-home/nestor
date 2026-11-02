"""`nestor bench`: list the suites, run one against variants, compare runs, report on one.

    nestor bench list
    nestor bench run watch-triage --variant a.yaml --variant b.yaml [--repeat 3] [--cases mine.jsonl] [--replay]
    nestor bench compare bench-results/watch-triage/<run> bench-results/watch-triage/<run>
    nestor bench report bench-results/watch-triage/<run>

Results go to `./bench-results/<suite>/<started>-<variant>/` and recorded replies to `./.bench-cache/`.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

from nestor.bench.catalogue import Suites
from nestor.bench.errors import BenchError
from nestor.bench.recording import Cache
from nestor.bench.report import Render, findings_text, page, table
from nestor.bench.results import REPORT, Run, read_run, write_run
from nestor.bench.runner import Plan, read_dataset, run_suite
from nestor.bench.variants import load_variant
from nestor.core import utc_now
from nestor.core.i18n import Locale, Localizer, Message
from nestor.runtime.plugins import Registry

RESULTS = Path("bench-results")
CACHE = Path(".bench-cache")

type Words = Callable[..., str]


def add_commands(bench: argparse.ArgumentParser, words: Words) -> None:
    actions = bench.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help=words("bench-list-help"))
    run = actions.add_parser("run", help=words("bench-run-help"), description=words("bench-run-description"))
    run.add_argument("suite", help=words("bench-suite-help"))
    run.add_argument("--variant", action="append", required=True, type=Path, metavar="YAML",
                     help=words("bench-variant-help"))  # fmt: skip
    run.add_argument("--repeat", type=_positive, default=1, metavar="N", help=words("bench-repeat-help"))
    run.add_argument("--cases", type=Path, metavar="JSONL", help=words("bench-cases-help"))
    run.add_argument("--replay", action="store_true", help=words("bench-replay-help"))
    run.add_argument("--seed", type=int, default=0, help=words("bench-seed-help"))
    run.add_argument("--concurrency", type=_positive, default=4, metavar="N", help=words("bench-concurrency-help"))
    run.add_argument("--results", type=Path, default=RESULTS, metavar="FOLDER", help=words("bench-results-help"))
    run.add_argument("--cache", type=Path, default=CACHE, metavar="FOLDER", help=words("bench-cache-help"))
    compare = actions.add_parser("compare", help=words("bench-compare-help"))
    compare.add_argument("runs", nargs="+", type=Path, metavar="RUN", help=words("bench-runs-help"))
    compare.add_argument("--out", type=Path, metavar="HTML", help=words("bench-out-help"))
    report = actions.add_parser("report", help=words("bench-report-help"))
    report.add_argument("run", type=Path, metavar="RUN", help=words("bench-runs-help"))


def main(args: argparse.Namespace, suites: Suites, render: Render, localizer: Localizer, locale: Locale) -> int:
    try:
        if args.action == "list":
            for suite in suites:
                print(
                    render(
                        Message.of(
                            "bench-list-line", suite=suite.name, description=render(Message.of(suite.description))
                        )
                    )
                )
            return 0
        if args.action == "run":
            return _run(args, suites, render, localizer, locale)
        if args.action == "compare":
            runs = [read_run(path) for path in args.runs]
            print(table(runs, render))
            out = args.out or args.runs[0].parent / f"{utc_now():%Y%m%dT%H%M%S}-compare.html"
            _write_page(out, runs, render, locale)
            return 0
        run = read_run(args.run)
        print(table([run], render))
        if run.summary.findings:
            print(f"\n{findings_text(run, render)}")
        folder = args.run if args.run.is_dir() else args.run.parent
        _write_page(folder / REPORT, [run], render, locale)
        return 0
    except BenchError as error:
        print(render(Message.of("bench-failed", reason=render(error.message))), file=sys.stderr)
        return 2


def _run(args: argparse.Namespace, suites: Suites, render: Render, localizer: Localizer, locale: Locale) -> int:
    suite = suites.get(args.suite)
    registry = Registry.installed()
    for plugin in suite.plugins:
        registry.register(plugin)
    variants = [load_variant(path, suite, registry, localizer) for path in args.variant]
    dataset, info = read_dataset(suite, args.cases or suite.dataset())
    print(
        render(
            Message.of(
                "bench-running",
                suite=suite.name,
                cases=info.cases,
                variants=len(variants),
                repeat=args.repeat,
                replayed="yes" if args.replay else "no",
            )
        ),
        flush=True,
    )
    plan = Plan(repeat=args.repeat, seed=args.seed, replay=args.replay, concurrency=args.concurrency)
    runs = asyncio.run(run_suite(suite, dataset, info, variants, plan, Cache(args.cache), _progress()))
    print(table(runs, render))
    folder = args.results / suite.name
    for run in runs:
        print(render(Message.of("bench-wrote", path=str(write_run(run, folder / run.folder_name())))))
        _write_page(folder / run.folder_name() / REPORT, [run], render, locale)
    if len(runs) > 1:
        _write_page(folder / f"{runs[0].started_at:%Y%m%dT%H%M%S}-compare.html", runs, render, locale)
    return 0


def _progress() -> Callable[[int, int], None] | None:
    """A counter on the same line of a terminal; nothing when the output is a file or a pipe."""
    if not sys.stderr.isatty():
        return None

    def show(done: int, total: int) -> None:
        print(f"\r{done}/{total}", end="\n" if done == total else "", file=sys.stderr, flush=True)

    return show


def _write_page(path: Path, runs: list[Run], render: Render, locale: Locale) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page(runs, render, lang=str(locale)), encoding="utf-8")
    print(render(Message.of("bench-wrote", path=str(path))))


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{value} < 1")
    return value
