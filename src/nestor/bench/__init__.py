"""Benchmarks: measure any part of Nestor on a dataset and compare configurations (`nestor bench`).

A suite (a `nestor.benches` plugin) says what a case is, how to run one and how to score them; the engine
runs every case against every variant (a fragment of `nestor.yaml`) and repetition, measures and records
each model call, and writes results and reports. Suites live in `nestor.bench.suites`, one folder each.
"""

from nestor.bench.catalogue import Suites
from nestor.bench.errors import BenchError
from nestor.bench.metrics import Confusion, percentile
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.types import Better, Call, Case, CaseResult, Dataset, Finding, Metric, Startup, Summary, Unit

__all__ = [
    "BenchError",
    "Better",
    "Call",
    "Case",
    "CaseResult",
    "Confusion",
    "Dataset",
    "Finding",
    "Knobs",
    "Metric",
    "Startup",
    "Suite",
    "Suites",
    "Summary",
    "Trial",
    "Unit",
    "percentile",
]
