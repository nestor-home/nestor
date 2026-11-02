"""A run as written to disk: `<results>/<suite>/<started>-<variant>/results.json`, next to its `report.html`.

Everything needed to trust and compare it later: the dataset's hash, the variant (secrets masked), the
models the provider says answered, Nestor's version and commit, timestamps, every case's output and calls.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.types import Better, Call, CaseResult, Finding, Metric, Summary, Unit
from nestor.core.i18n import Message

FORMAT = 1
RESULTS = "results.json"
REPORT = "report.html"


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetInfo:
    source: str
    sha256: str
    version: int
    cases: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Run:
    suite: str
    variant: str
    config: Mapping[str, Any]
    dataset: DatasetInfo
    repeat: int
    seed: int
    replay: bool
    nestor: str
    commit: str | None
    started_at: datetime
    finished_at: datetime
    results: tuple[CaseResult, ...]
    summary: Summary

    @property
    def served_models(self) -> tuple[str, ...]:
        return tuple(sorted({c.served_model for r in self.results for c in r.calls if c.served_model}))

    def folder_name(self) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", self.variant).strip("-") or "variant"
        return f"{self.started_at:%Y%m%dT%H%M%S}-{slug}"


def write_run(run: Run, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / RESULTS
    path.write_text(json.dumps(_wire(run), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def read_run(path: Path) -> Run:
    """A run from its folder or its `results.json`."""
    file = path / RESULTS if path.is_dir() else path
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        if raw.get("format") != FORMAT:
            raise ValueError(raw.get("format"))
        return _run(raw)
    except (OSError, ValueError, KeyError, TypeError):
        raise BenchError(Message.of("bench-results-unreadable", path=str(path))) from None


def _wire(run: Run) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "suite": run.suite,
        "variant": run.variant,
        "config": run.config,
        "dataset": asdict(run.dataset),
        "repeat": run.repeat,
        "seed": run.seed,
        "replay": run.replay,
        "nestor": run.nestor,
        "commit": run.commit,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat(),
        "served_models": list(run.served_models),
        "summary": {
            "metrics": [asdict(m) for m in run.summary.metrics],
            "findings": [
                {"group": f.group, "case": f.case, "detail": {"id": f.detail.id, "args": dict(f.detail.args)}}
                for f in run.summary.findings
            ],
        },
        "results": [
            {
                "case": r.case,
                "repetition": r.repetition,
                "latency_s": r.latency_s,
                "output": r.output,
                "calls": [asdict(c) for c in r.calls],
            }
            for r in run.results
        ],
    }


def _run(raw: dict[str, Any]) -> Run:
    summary = raw["summary"]
    return Run(
        suite=raw["suite"],
        variant=raw["variant"],
        config=raw["config"],
        dataset=DatasetInfo(**raw["dataset"]),
        repeat=raw["repeat"],
        seed=raw["seed"],
        replay=raw["replay"],
        nestor=raw["nestor"],
        commit=raw["commit"],
        started_at=datetime.fromisoformat(raw["started_at"]),
        finished_at=datetime.fromisoformat(raw["finished_at"]),
        results=tuple(
            CaseResult(
                case=r["case"],
                repetition=r["repetition"],
                latency_s=r["latency_s"],
                output=r["output"],
                calls=tuple(Call(**c) for c in r["calls"]),
            )
            for r in raw["results"]
        ),
        summary=Summary(
            metrics=tuple(
                Metric(id=m["id"], label=m["label"], value=m["value"], unit=Unit(m["unit"]), better=Better(m["better"]))
                for m in summary["metrics"]
            ),
            findings=tuple(
                Finding(group=f["group"], case=f["case"], detail=Message(f["detail"]["id"], f["detail"]["args"]))
                for f in summary["findings"]
            ),
        ),
    )
