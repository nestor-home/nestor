"""Scoring helpers for suites, and the metrics the engine adds to every run: calls, latencies, tokens, cost."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from nestor.bench.types import Better, CaseResult, Metric, Unit


@dataclass(slots=True)
class Confusion:
    """Counts of a yes/no decision against the expected answer."""

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0

    def add(self, *, predicted: bool, expected: bool) -> None:
        if predicted and expected:
            self.true_positives += 1
        elif predicted:
            self.false_positives += 1
        elif expected:
            self.false_negatives += 1
        else:
            self.true_negatives += 1

    @property
    def precision(self) -> float | None:
        """Of what was said yes, how much was right; None when nothing was said yes."""
        said = self.true_positives + self.false_positives
        return self.true_positives / said if said else None

    @property
    def recall(self) -> float | None:
        """Of what should have been said yes, how much was; None when nothing should have."""
        expected = self.true_positives + self.false_negatives
        return self.true_positives / expected if expected else None

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None:
            return None
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Linear interpolation between the closest ranks (what spreadsheets compute); None without values."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _total(values: Iterable[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def engine_metrics(results: Sequence[CaseResult]) -> tuple[Metric, ...]:
    """What every run measures, whatever the suite: model calls per case, latencies of the warm cases and
    calls (the first call of a model opens its connection), tokens and cost when the provider reports them,
    provider errors."""
    calls = [c for r in results for c in r.calls]
    warm_cases = [r.latency_s for r in results if not any(c.cold for c in r.calls)]
    warm_calls = [c.latency_s for c in calls if not c.cold and c.error is None]
    count = len(results) or 1
    input_tokens, output_tokens = _total(c.input_tokens for c in calls), _total(c.output_tokens for c in calls)
    cost = _total(c.cost for c in calls)

    def metric(id: str, value: float | None, unit: Unit, better: Better = Better.LOWER) -> Metric:
        return Metric(id=id, label=f"bench-metric-{id}", value=value, unit=unit, better=better)

    return (
        metric("calls-per-case", len(calls) / count, Unit.COUNT),
        metric("case-latency-p50", percentile(warm_cases, 0.5), Unit.DURATION),
        metric("case-latency-p95", percentile(warm_cases, 0.95), Unit.DURATION),
        metric("call-latency-p50", percentile(warm_calls, 0.5), Unit.DURATION),
        metric("call-latency-p95", percentile(warm_calls, 0.95), Unit.DURATION),
        metric("input-tokens-per-case", None if input_tokens is None else input_tokens / count, Unit.COUNT),
        metric("output-tokens-per-case", None if output_tokens is None else output_tokens / count, Unit.COUNT),
        metric("cost-per-1000-cases", None if cost is None else cost * 1000 / count, Unit.COST),
        metric("provider-errors", sum(c.error is not None for c in calls), Unit.COUNT),
    )
