"""Measured model calls, and the replay cache that lets a run be scored again without calling a provider.

A call is keyed by what decides its answer: the model as configured (secrets masked), the request, the
repetition and the seed. A live run measures every call and records its reply; a replayed run reads the
replies back, with the latencies, usage and model measured when they were recorded, and never calls out. What a
call consumed is gathered as the runtime gathers it (`nestor.core.report`), and said again when replayed.
"""

import contextvars
import hashlib
import json
import time
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.types import Call
from nestor.core import ContractError, Money, ProviderError, Tally, Unit, Usage, counted, report
from nestor.core.i18n import Message
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    LanguageModel,
    ModelOutput,
    ModelRequest,
    TextDelta,
    ToolCall,
    ToolCallRequested,
)


@dataclass(slots=True, kw_only=True)
class CaseLog:
    """The case being run in this task: the calls its models make are appended here."""

    case: str
    repetition: int
    seed: int
    calls: list[Call] = field(default_factory=list)


_TOKENS = (Unit.INPUT_TOKENS, Unit.CACHED_INPUT_TOKENS, Unit.OUTPUT_TOKENS)
CURRENT_CASE: contextvars.ContextVar[CaseLog] = contextvars.ContextVar("nestor_bench_case")


@dataclass(frozen=True, slots=True, kw_only=True)
class Recording:
    outputs: tuple[ModelOutput, ...]
    usage: Usage  # what the call reported it consumed
    latency_s: float
    first_output_s: float | None
    cold: bool


def request_key(model: Mapping[str, Any], request: ModelRequest, *, repetition: int, seed: int) -> str:
    wire = {
        "model": model,
        "messages": [
            {
                "role": m.role.value,
                "content": m.content,
                "tool_calls": [{"id": c.id, "name": c.name, "arguments": dict(c.arguments)} for c in m.tool_calls],
                "tool_call_id": m.tool_call_id,
            }
            for m in request.messages
        ],
        "tools": [
            {"name": t.name, "description": t.description, "parameters": dict(t.parameters)} for t in request.tools
        ],
        "repetition": repetition,
        "seed": seed,
    }
    canonical = json.dumps(wire, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class Cache:
    """Recordings on disk, one JSON file per call: `<folder>/<key[:2]>/<key>.json`."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def _path(self, key: str) -> Path:
        return self.folder / key[:2] / f"{key}.json"

    def read(self, key: str) -> Recording | None:
        path = self._path(key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return Recording(
                outputs=tuple(_output(o) for o in raw["outputs"]),
                usage=_usage(raw["usage"]),
                latency_s=raw["latency_s"],
                first_output_s=raw["first_output_s"],
                cold=raw["cold"],
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            raise BenchError(Message.of("bench-cache-unreadable", path=str(path))) from None

    def write(self, key: str, recording: Recording) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "outputs": [_wire_output(o) for o in recording.outputs],
            "usage": _wire_usage(recording.usage),
            "latency_s": recording.latency_s,
            "first_output_s": recording.first_output_s,
            "cold": recording.cold,
        }
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")


class MeasuredModel(LanguageModel):
    """A variant's model as the suite sees it: every call is timed, recorded, and logged on the running case.

    It never starts or closes the model it measures: the engine does, once per variant.
    """

    def __init__(
        self, inner: LanguageModel, *, role: str, described: Mapping[str, Any], cache: Cache, replay: bool
    ) -> None:
        self.name = inner.name
        self._inner, self._role, self._described = inner, role, described
        self._cache, self._replay = cache, replay
        self._cold = True

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        log = CURRENT_CASE.get(None)
        if log is None:
            raise ContractError("a measured model is called outside of a bench case")
        key = request_key(self._described, request, repetition=log.repetition, seed=log.seed)
        if self._replay:
            recording = self._cache.read(key)
            if recording is None:
                raise BenchError(Message.of("bench-no-recording", case=log.case, role=self._role))
            log.calls.append(self._call(key, recording, replayed=True))
            report(recording.usage)  # to whoever counts around the bench, as the call did when it was recorded
            for output in recording.outputs:
                yield output
            return
        outputs: list[ModelOutput] = []
        first: float | None = None
        started = time.perf_counter()
        tally = Tally()
        try:
            async for output in counted(self._inner.stream(request), tally):
                first = time.perf_counter() - started if first is None else first
                outputs.append(output)
                yield output
        except ProviderError as error:
            log.calls.append(Call(role=self._role, key=key, latency_s=time.perf_counter() - started, error=str(error)))
            raise
        cold, self._cold = self._cold, False
        recording = Recording(
            outputs=tuple(outputs),
            usage=tally.usage,
            latency_s=time.perf_counter() - started,
            first_output_s=first,
            cold=cold,
        )
        self._cache.write(key, recording)
        log.calls.append(self._call(key, recording, replayed=False))

    def _call(self, key: str, recording: Recording, *, replayed: bool) -> Call:
        units = recording.usage.units
        tokens = {u: int(n) if (n := units.get(u)) is not None else None for u in _TOKENS}
        cost = recording.usage.cost
        return Call(
            role=self._role,
            key=key,
            latency_s=recording.latency_s,
            first_output_s=recording.first_output_s,
            input_tokens=tokens[Unit.INPUT_TOKENS],
            cached_input_tokens=tokens[Unit.CACHED_INPUT_TOKENS],
            output_tokens=tokens[Unit.OUTPUT_TOKENS],
            cost=float(cost.dollars) if cost is not None else None,
            served_model=recording.usage.served,
            replayed=replayed,
            cold=recording.cold,
        )


def _wire_output(output: ModelOutput) -> dict[str, Any]:
    if isinstance(output, TextDelta):
        return {"text": output.text}
    if isinstance(output, ToolCallRequested):
        call = output.call
        return {"tool_call": {"id": call.id, "name": call.name, "arguments": dict(call.arguments)}}
    return {"finished": {"reason": output.reason.value}}


def _wire_usage(usage: Usage) -> dict[str, Any]:
    return {
        "units": {u.value: q for u, q in usage.units.items()},
        "cost_nusd": usage.cost.nusd if usage.cost is not None else None,
        "served": usage.served,
    }


def _usage(raw: Mapping[str, Any]) -> Usage:
    cost = raw["cost_nusd"]
    return Usage(
        {Unit(u): q for u, q in raw["units"].items()}, Money(cost) if cost is not None else None, raw["served"]
    )


def _output(raw: Mapping[str, Any]) -> ModelOutput:
    if "text" in raw:
        return TextDelta(raw["text"])
    if "tool_call" in raw:
        call = raw["tool_call"]
        return ToolCallRequested(ToolCall(call["id"], call["name"], call["arguments"]))
    return Finished(FinishReason(raw["finished"]["reason"]))
