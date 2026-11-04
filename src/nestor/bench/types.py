"""Values of a benchmark: cases, the calls a case made, what it produced, the metrics a run is summed up in."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nestor.core.i18n import Message


@dataclass(frozen=True, slots=True)
class Case:
    """One input with its expected answer: a line of the suite's JSONL dataset."""

    id: str
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Dataset[S]:
    """A suite's dataset once read: its cases, and what they share (the watches of the watch-triage suite)."""

    version: int
    cases: tuple[Case, ...]
    shared: S


@dataclass(frozen=True, slots=True, kw_only=True)
class Call:
    """One model call a case made, as measured (or recorded, when replayed)."""

    role: str  # the role of the model in the configuration: "watches"
    key: str  # its record in the replay cache
    latency_s: float
    first_output_s: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None  # of `input_tokens`, read from the provider's prompt cache
    output_tokens: int | None = None
    cost: float | None = None
    served_model: str | None = None  # the model the provider says answered
    error: str | None = None
    replayed: bool = False
    cold: bool = False  # the first call of a model: opens the connection, left out of latencies


@dataclass(frozen=True, slots=True, kw_only=True)
class Startup:
    """How a model the engine started for a variant came up: how long `start()` took, and how much the process's
    peak memory grew meanwhile (None where the platform does not tell)."""

    seconds: float
    memory_bytes: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CaseResult:
    case: str
    repetition: int
    output: Mapping[str, Any]  # what the suite made of the case, JSON
    calls: tuple[Call, ...] = ()
    latency_s: float = 0.0


class Unit(StrEnum):
    RATIO = "ratio"  # 0 to 1
    COUNT = "count"
    DURATION = "duration"  # seconds
    COST = "cost"  # the provider's billing currency
    BYTES = "bytes"


class Better(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"
    NEITHER = "neither"


@dataclass(frozen=True, slots=True, kw_only=True)
class Metric:
    id: str
    label: str  # a message id
    value: float | None  # None: nothing to measure it on (no token reported…)
    unit: Unit
    better: Better = Better.NEITHER


@dataclass(frozen=True, slots=True, kw_only=True)
class Finding:
    """A case worth reading: a missed match, a false alarm. `group` is the message id of its heading."""

    group: str
    case: str
    detail: Message


@dataclass(frozen=True, slots=True)
class Summary:
    metrics: tuple[Metric, ...]
    findings: tuple[Finding, ...] = field(default=())
