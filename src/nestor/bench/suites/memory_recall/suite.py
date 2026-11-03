"""The memory-recall suite: do the memories and past conversations a turn needs reach its instructions, and how
many others with them?

Its dataset (`cases.jsonl`) starts with a header, then the household's memories and episodes, then what people
say with what matters to it:

    {"dataset": "memory-recall", "version": 1}
    {"memory": "m01", "about": "lea", "text": "Léa est végétarienne depuis 2024."}
    {"episode": "e01", "people": ["lea"], "ended": "2026-10-18T20:10", "address": "telegram:7",
     "medium": "written", "summary": "Léa a parlé d'un restaurant italien…", "topics": ["restaurant"]}
    {"case": "c13", "speaker": "hugo", "said": "Je mets du jambon pour tout le monde ?", "expected": ["m01"],
     "kind": "paraphrase"}

`kind` groups the cases:
- `direct`: it shares words with the memory; `paraphrase`: it does not;
- `contradiction`: a later memory overrides an earlier one (`stale`), which should not come instead of it;
  a memory's `at` dates it;
- `premise`: what is said contradicts a memory, which must come to correct it ("Jules loves chicory, right?");
- `other-person`: the same subject about someone else (`avoid`), which can mislead;
- `episode`: a past conversation of whoever speaks matters ("do you remember the restaurant I told you about?");
- `private`: someone else's conversation (`avoid`) must never come, whatever is said;
- `none`: no memory matters, whatever comes is noise.

Memories and episodes are kept in Nestor's own stores, so what is measured is what runs.
"""

import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
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
from nestor.modules.channels import Address, Medium
from nestor.modules.memory import Memories, Memory
from nestor.modules.memory.episodes import Episode, Episodes
from nestor.modules.memory.recall import for_turn
from nestor.runtime.app import open_memories

NAME = "memory-recall"
KINDS = ("direct", "paraphrase", "contradiction", "premise", "other-person", "episode", "private", "none")


@dataclass(frozen=True, slots=True)
class Remembered:
    memories: tuple[Memory, ...]
    episodes: tuple[Episode, ...]


class MemoryRecall(Suite[Remembered, Knobs]):
    """A variant's `memory` section, embedder included, says how memories are found: no knobs of its own."""

    name = NAME
    description = "bench-memory-recall-description"
    knobs = Knobs
    models = ()  # retrieval calls no language model
    embedder = True  # but searches by meaning with the variant's embedder

    def __init__(self) -> None:
        self._stores: dict[str, tuple[Memories, Episodes]] = {}  # by variant: a run reads one dataset
        self._stack = AsyncExitStack()  # open for the process: a bench run is a command of its own

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "cases.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]]) -> Dataset[Remembered]:
        if not records or records[0].get("dataset") != NAME or not isinstance(records[0].get("version"), int):
            raise BenchError(Message.of("bench-memory-recall-no-header"))
        memories: list[Memory] = []
        episodes: list[Episode] = []
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
            elif "episode" in record and isinstance(record.get("summary"), str):
                ended = datetime.fromisoformat(str(record["ended"])).replace(tzinfo=UTC)
                episodes.append(
                    Episode(
                        id=str(record["episode"]),
                        address=Address.parse(str(record["address"])),
                        medium=Medium(record.get("medium", "written")),
                        participants=tuple(PersonId(p) for p in record.get("people", ())),
                        started_at=ended,
                        ended_at=ended,
                        summary=record["summary"],
                        topics=tuple(record.get("topics", ())),
                    )
                )
            elif "case" in record and isinstance(record.get("said"), str) and record.get("kind") in KINDS:
                cases.append(Case(id=str(record["case"]), data=record))
            else:
                raise BenchError(Message.of("bench-memory-recall-bad-record", line=number))
        known = {m.id for m in memories} | {e.id for e in episodes}
        for case in cases:
            named = {*case.data.get("expected", ()), *case.data.get("stale", ()), *case.data.get("avoid", ())}
            if unknown := named - known:
                raise BenchError(Message.of("bench-memory-recall-unknown", case=case.id, memory=", ".join(unknown)))
        return Dataset(
            version=records[0]["version"], cases=tuple(cases), shared=Remembered(tuple(memories), tuple(episodes))
        )

    async def run(self, case: Case, shared: Remembered, trial: Trial[Knobs]) -> Mapping[str, Any]:
        memories, episodes = await self._stores_for(shared, trial)
        speaker = PersonId(str(case.data["speaker"])) if case.data.get("speaker") else None
        found = await for_turn(memories, episodes, str(case.data["said"]), speaker, trial.config.memory.recall())
        carried = (*found.found, *found.shown, *found.latest_episodes, *found.found_episodes)
        return {"injected": [item.id for item in carried]}

    async def _stores_for(self, shared: Remembered, trial: Trial[Knobs]) -> tuple[Memories, Episodes]:
        """The household's memories and episodes in stores of the variant's own, filled and embedded once."""
        if (found := self._stores.get(trial.variant)) is not None:
            return found
        folder = Path(tempfile.mkdtemp(prefix="nestor-bench-recall-"))
        opened = open_memories(folder, trial.embedder, query_timeout_s=trial.config.memory.query_timeout_s)
        memories, episodes = await self._stack.enter_async_context(opened)
        for memory in shared.memories:
            await memories.store.put(memory)
        for episode in shared.episodes:
            await episodes.store.put(episode)
        for index in (memories.index, episodes.index):
            if index is not None:
                index.refresh()
                await index.settled()
        self._stores[trial.variant] = (memories, episodes)
        return memories, episodes

    def summarise(self, dataset: Dataset[Remembered], results: Sequence[CaseResult]) -> Summary:
        cases = {c.id: c for c in dataset.cases}
        repetitions = len({r.repetition for r in results}) or 1
        wanted: Counter[str] = Counter()
        reached: Counter[str] = Counter()
        complete = answered = injected = noise = stale = misleading = leaked = 0
        counted: Counter[str] = Counter()
        participants = {e.id: set(e.participants) for e in dataset.shared.episodes}
        missed: Counter[tuple[str, str]] = Counter()
        for result in results:
            data = cases[result.case].data
            kind, expected = str(data["kind"]), set(data.get("expected", ()))
            got = set(result.output["injected"])
            counted[kind] += 1
            injected += len(got)
            stale += len(got & set(data.get("stale", ())))
            misleading += len(got & set(data.get("avoid", ()))) if kind == "other-person" else 0
            leaked += sum(1 for i in got if i in participants and data.get("speaker") not in participants[i])
            if kind in ("none", "private"):
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

        texts = {m.id: m.text for m in dataset.shared.memories} | {e.id: e.summary for e in dataset.shared.episodes}
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
            if kind not in ("none", "private")
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
                metric("others-conversations-injected", leaked / repetitions, Unit.COUNT, Better.LOWER),
            ),
            findings=findings,
        )
