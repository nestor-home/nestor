"""Running a suite: every case against every variant, at every repetition.

Cases run in a seeded order, the variants of a case one after the other, so no variant gets the quiet
hours of a provider and another its rush. Each variant's models are started once for the whole run.
"""

import asyncio
import contextlib
import hashlib
import json
import random
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.metrics import engine_metrics
from nestor.bench.ports import Suite, Trial
from nestor.bench.recording import CURRENT_CASE, Cache, CaseLog, MeasuredModel
from nestor.bench.results import DatasetInfo, Run
from nestor.bench.types import Case, CaseResult, Dataset, Summary
from nestor.bench.variants import Variant
from nestor.core import utc_now
from nestor.core.i18n import Message


@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    repeat: int = 1
    seed: int = 0
    replay: bool = False  # read recorded replies only: no provider is called
    concurrency: int = 4  # cases in flight at once


def read_dataset[S](suite: Suite[S, Any], source: Traversable | Path) -> tuple[Dataset[S], DatasetInfo]:
    try:
        content = source.read_bytes()
    except OSError:
        raise BenchError(Message.of("bench-dataset-unreadable", path=str(source))) from None
    records: list[Mapping[str, Any]] = []
    for number, line in enumerate(content.decode("utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            record = None
        if not isinstance(record, dict):
            raise BenchError(Message.of("bench-dataset-invalid-line", path=str(source), line=number))
        records.append(record)
    dataset = suite.load(records)
    info = DatasetInfo(
        source=str(source),
        sha256=hashlib.sha256(content).hexdigest(),
        version=dataset.version,
        cases=len(dataset.cases),
    )
    return dataset, info


async def run_suite[S](
    suite: Suite[S, Any],
    dataset: Dataset[S],
    info: DatasetInfo,
    variants: Sequence[Variant[Any]],
    plan: Plan,
    cache: Cache,
    progress: Callable[[int, int], None] | None = None,
) -> list[Run]:
    """Every case against every variant and repetition; `progress` hears of each one done (done, total)."""
    names = [v.name for v in variants]
    if len(set(names)) != len(names):
        raise BenchError(Message.of("bench-same-variant-name", names=", ".join(names)))
    started = utc_now()
    results: dict[str, list[CaseResult]] = {v.name: [] for v in variants}
    gate = asyncio.Semaphore(plan.concurrency)
    total = len(dataset.cases) * len(variants) * plan.repeat
    async with contextlib.AsyncExitStack() as stack:
        for variant in variants:
            for model in variant.models.values():
                await stack.enter_async_context(model)
        measured = {v.name: _measured(v, cache, plan.replay) for v in variants}

        async def one(case: Case, variant: Variant[Any], repetition: int) -> None:
            trial = Trial(
                variant=variant.name,
                knobs=variant.knobs,
                config=variant.config,
                models=measured[variant.name],
                repetition=repetition,
                seed=plan.seed,
            )
            async with gate:
                log = CaseLog(case=case.id, repetition=repetition, seed=plan.seed)
                CURRENT_CASE.set(log)  # this task's own context: the calls of this case land here
                clock = time.perf_counter()
                output = await suite.run(case, dataset.shared, trial)
                elapsed = time.perf_counter() - clock
            # a replayed call took no time now: the case is charged what it took when it was recorded
            elapsed += sum(c.latency_s for c in log.calls if c.replayed)
            results[variant.name].append(
                CaseResult(
                    case=case.id, repetition=repetition, output=output, calls=tuple(log.calls), latency_s=elapsed
                )
            )
            if progress is not None:
                progress(sum(map(len, results.values())), total)

        try:
            async with asyncio.TaskGroup() as group:
                for repetition in range(plan.repeat):
                    order = list(dataset.cases)
                    random.Random(f"{plan.seed}:{repetition}").shuffle(order)
                    for case in order:
                        for variant in variants:
                            group.create_task(one(case, variant, repetition))
        except* BenchError as failed:
            raise failed.exceptions[0] from None
    finished = utc_now()
    position = {c.id: i for i, c in enumerate(dataset.cases)}
    nestor, commit = version("nestor-home"), _commit()
    runs = []
    for variant in variants:
        ordered = tuple(sorted(results[variant.name], key=lambda r: (r.repetition, position[r.case])))
        scored = suite.summarise(dataset, ordered)
        runs.append(
            Run(
                suite=suite.name,
                variant=variant.name,
                config=variant.record(),
                dataset=info,
                repeat=plan.repeat,
                seed=plan.seed,
                replay=plan.replay,
                nestor=nestor,
                commit=commit,
                started_at=started,
                finished_at=finished,
                results=ordered,
                summary=Summary(scored.metrics + engine_metrics(ordered), scored.findings),
            )
        )
    return runs


def _measured(variant: Variant[Any], cache: Cache, replay: bool) -> dict[str, MeasuredModel]:
    return {
        role: MeasuredModel(model, role=role, described=variant.described[role], cache=cache, replay=replay)
        for role, model in variant.models.items()
    }


def _commit() -> str | None:
    """The commit of the Nestor source the run used, `+dirty` with uncommitted changes; None when this file
    is not tracked by git (an installed wheel, even inside someone else's repository)."""
    here = Path(__file__)

    def git(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(here.parent), *args], capture_output=True, text=True, timeout=5)
        if done.returncode:
            raise subprocess.SubprocessError(done.stderr)
        return done.stdout.strip()

    try:
        git("ls-files", "--error-unmatch", here.name)
        head, dirty = git("rev-parse", "HEAD"), git("status", "--porcelain")
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{head}+dirty" if dirty else head
