"""Measured model calls, and the replay cache that lets a run be scored again without calling a provider.

A call is keyed by what decides its answer: the model as configured (secrets masked), the request, the
repetition and the seed. A live run measures every call and records its reply; a replayed run reads the
replies back, with the latencies, usage and model measured when they were recorded, and never calls out.
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
from nestor.core import ContractError, ProviderError
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
    Usage,
)


@dataclass(slots=True, kw_only=True)
class CaseLog:
    """The case being run in this task: the calls its models make are appended here."""

    case: str
    repetition: int
    seed: int
    calls: list[Call] = field(default_factory=list)


CURRENT_CASE: contextvars.ContextVar[CaseLog] = contextvars.ContextVar("nestor_bench_case")


@dataclass(frozen=True, slots=True, kw_only=True)
class Recording:
    outputs: tuple[ModelOutput, ...]
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
            for output in recording.outputs:
                yield output
            return
        outputs: list[ModelOutput] = []
        first: float | None = None
        started = time.perf_counter()
        try:
            async for output in self._inner.stream(request):
                first = time.perf_counter() - started if first is None else first
                outputs.append(output)
                yield output
        except ProviderError as error:
            log.calls.append(Call(role=self._role, key=key, latency_s=time.perf_counter() - started, error=str(error)))
            raise
        cold, self._cold = self._cold, False
        recording = Recording(
            outputs=tuple(outputs), latency_s=time.perf_counter() - started, first_output_s=first, cold=cold
        )
        self._cache.write(key, recording)
        log.calls.append(self._call(key, recording, replayed=False))

    def _call(self, key: str, recording: Recording, *, replayed: bool) -> Call:
        finished = next((o for o in recording.outputs if isinstance(o, Finished)), None)
        usage = finished.usage if finished else None
        return Call(
            role=self._role,
            key=key,
            latency_s=recording.latency_s,
            first_output_s=recording.first_output_s,
            input_tokens=usage.input_tokens if usage else None,
            cached_input_tokens=usage.cached_input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cost=usage.cost if usage else None,
            served_model=finished.model if finished else None,
            replayed=replayed,
            cold=recording.cold,
        )


def _wire_output(output: ModelOutput) -> dict[str, Any]:
    if isinstance(output, TextDelta):
        return {"text": output.text}
    if isinstance(output, ToolCallRequested):
        call = output.call
        return {"tool_call": {"id": call.id, "name": call.name, "arguments": dict(call.arguments)}}
    usage = output.usage
    spent = usage and {
        "input": usage.input_tokens,
        "cached": usage.cached_input_tokens,
        "output": usage.output_tokens,
        "cost": usage.cost,
    }
    return {"finished": {"reason": output.reason.value, "usage": spent, "model": output.model}}


def _output(raw: Mapping[str, Any]) -> ModelOutput:
    if "text" in raw:
        return TextDelta(raw["text"])
    if "tool_call" in raw:
        call = raw["tool_call"]
        return ToolCallRequested(ToolCall(call["id"], call["name"], call["arguments"]))
    finished = raw["finished"]
    spent = finished["usage"]
    usage = (
        None
        if spent is None
        else Usage(
            input_tokens=spent["input"],
            output_tokens=spent["output"],
            cost=spent.get("cost"),
            cached_input_tokens=spent.get("cached"),
        )
    )
    return Finished(FinishReason(finished["reason"]), usage, finished["model"])
