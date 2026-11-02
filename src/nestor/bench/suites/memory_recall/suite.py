"""The memory-recall suite: do the memories a turn needs reach its instructions, and how many others with them?

Its dataset (`cases.jsonl`) starts with a header, then the household's memories, then what people say with
the memories that matter to it:

    {"dataset": "memory-recall", "version": 1}
    {"memory": "m01", "about": "lea", "text": "Léa est végétarienne depuis 2024."}
    {"case": "c13", "speaker": "hugo", "said": "Je mets du jambon pour tout le monde ?", "expected": ["m01"],
     "kind": "paraphrase"}

`kind` groups the cases:
- `direct`: it shares words with the memory; `paraphrase`: it does not;
- `contradiction`: a later memory overrides an earlier one (`stale`), which should not come instead of it;
  a memory's `at` dates it;
- `premise`: what is said contradicts a memory, which must come to correct it ("Jules loves chicory, right?");
- `other-person`: the same subject about someone else (`avoid`), which can mislead;
- `none`: no memory matters, whatever comes is noise.

The memories are kept in Nestor's own store, so what is measured is what runs.
"""

import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.memory import Memories, Memory
from nestor.modules.memory.recall import RecallSettings, Strategy, for_turn
from nestor.runtime.app import open_memories

NAME = "memory-recall"
KINDS = ("direct", "paraphrase", "contradiction", "premise", "other-person", "none")


class RecallKnobs(Knobs):
    strategy: Strategy = Strategy.BOTH
    recent: int = 150
    found: int = 12


class MemoryRecall(Suite[tuple[Memory, ...], RecallKnobs]):
    name = NAME
    description = "bench-memory-recall-description"
    knobs = RecallKnobs
    models = ()  # retrieval calls no language model

    def __init__(self) -> None:
        self._memories: Memories | None = None
        self._loaded: tuple[Memory, ...] = ()
        self._stack = AsyncExitStack()  # open for the process: a bench run is a command of its own

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "cases.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]]) -> Dataset[tuple[Memory, ...]]:
        if not records or records[0].get("dataset") != NAME or not isinstance(records[0].get("version"), int):
            raise BenchError(Message.of("bench-memory-recall-no-header"))
        memories: list[Memory] = []
        cases: list[Case] = []
        for number, record in enumerate(records[1:], start=2):
            if "memory" in record and isinstance(record.get("text"), str):
                about = record.get("about")
                at = datetime.fromisoformat(str(record.get("at", "2026-01-01"))).replace(tzinfo=UTC)
                memories.append(
                    Memory(
                        id=str(record["memory"]),
                        text=record["text"],
                        about=PersonId(about) if about else None,
                        created_at=at,
                        updated_at=at,
                    )
                )
            elif "case" in record and isinstance(record.get("said"), str) and record.get("kind") in KINDS:
                cases.append(Case(id=str(record["case"]), data=record))
            else:
                raise BenchError(Message.of("bench-memory-recall-bad-record", line=number))
        known = {m.id for m in memories}
        for case in cases:
            named = {*case.data.get("expected", ()), *case.data.get("stale", ()), *case.data.get("avoid", ())}
            if unknown := named - known:
                raise BenchError(Message.of("bench-memory-recall-unknown", case=case.id, memory=", ".join(unknown)))
        return Dataset(version=records[0]["version"], cases=tuple(cases), shared=tuple(memories))

    async def run(self, case: Case, shared: tuple[Memory, ...], trial: Trial[RecallKnobs]) -> Mapping[str, Any]:
        memories = await self._store(shared)
        knobs = trial.knobs
        settings = RecallSettings(strategy=knobs.strategy, found=knobs.found, recent=knobs.recent)
        injected = await for_turn(memories, str(case.data["said"]), settings)
        return {"injected": [m.id for m in injected]}

    async def _store(self, shared: tuple[Memory, ...]) -> Memories:
        """The household's memories in a store of their own, filled once for the whole run."""
        if self._memories is None or self._loaded is not shared:
            opened = open_memories(Path(tempfile.mkdtemp(prefix="nestor-bench-recall-")))
            memories = await self._stack.enter_async_context(opened)
            for memory in shared:
                await memories.store.put(memory)
            self._memories, self._loaded = memories, shared
        return self._memories

    def summarise(self, dataset: Dataset[tuple[Memory, ...]], results: Sequence[CaseResult]) -> Summary:
        cases = {c.id: c for c in dataset.cases}
        repetitions = len({r.repetition for r in results}) or 1
        wanted: Counter[str] = Counter()
        reached: Counter[str] = Counter()
        complete = answered = injected = noise = stale = misleading = 0
        counted: Counter[str] = Counter()
        missed: Counter[tuple[str, str]] = Counter()
        for result in results:
            data = cases[result.case].data
            kind, expected = str(data["kind"]), set(data.get("expected", ()))
            got = set(result.output["injected"])
            counted[kind] += 1
            injected += len(got)
            stale += len(got & set(data.get("stale", ())))
            misleading += len(got & set(data.get("avoid", ())))
            if kind == "none":
                noise += len(got)
                continue
            wanted[kind] += len(expected)
            reached[kind] += len(expected & got)
            answered += 1
            complete += expected <= got
            for memory in sorted(expected - got):
                missed[result.case, memory] += 1

        def ratio(part: float, whole: float) -> float | None:
            return part / whole if whole else None

        def metric(id: str, value: float | None, unit: Unit, better: Better) -> Metric:
            return Metric(id=id, label=f"bench-memory-recall-{id}", value=value, unit=unit, better=better)

        texts = {m.id: m.text for m in dataset.shared}
        findings = tuple(
            Finding(
                group="bench-memory-recall-missed-list",
                case=case,
                detail=Message.of(
                    "bench-memory-recall-item",
                    case=case,
                    said=str(cases[case].data["said"]),
                    memory=texts[memory],
                    times=times,
                    of=repetitions,
                ),
            )
            for (case, memory), times in sorted(missed.items())
        )
        by_kind = tuple(
            metric(f"recall-{kind}", ratio(reached[kind], wanted[kind]), Unit.RATIO, Better.HIGHER)
            for kind in KINDS
            if kind != "none"
        )
        return Summary(
            metrics=(
                metric("recall", ratio(sum(reached.values()), sum(wanted.values())), Unit.RATIO, Better.HIGHER),
                *by_kind,
                metric("complete", ratio(complete, answered), Unit.RATIO, Better.HIGHER),
                metric("injected-per-case", ratio(injected, len(results)), Unit.COUNT, Better.LOWER),
                metric("noise-when-nothing-matters", ratio(noise, counted["none"]), Unit.COUNT, Better.LOWER),
                metric("stale-injected", ratio(stale, counted["contradiction"]), Unit.COUNT, Better.LOWER),
                metric("misleading-injected", ratio(misleading, counted["other-person"]), Unit.COUNT, Better.LOWER),
            ),
            findings=findings,
        )
