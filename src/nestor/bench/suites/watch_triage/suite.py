"""The watch-triage suite: does an incoming mail match what someone asked to be told about, and is it urgent?

Its dataset (`cases.jsonl`) starts with a header, then the watches, then the mails with their labels:

    {"dataset": "watch-triage", "version": 1}
    {"watch": "w-stroller", "what": "le colis de la poussette", "keywords": ["poussette", "colis"]}
    {"case": "m001", "from": "...", "title": "...", "body": "...", "expected": {"w-stroller": "match"}}

`expected` names the watches a mail matches, `"match"` or `"urgent"`; a watch it does not name is not
matched. Every (mail, watch) pair is scored.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.metrics import Confusion
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.suites.watch_triage.algorithms import Algorithm, decide
from nestor.bench.suites.watch_triage.fake import plugin as fake
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core.i18n import Message
from nestor.modules.initiative.watches import Incoming, Watch

NAME = "watch-triage"
LABELS = frozenset({"match", "urgent"})


class TriageKnobs(Knobs):
    algorithm: Algorithm = Algorithm.GATE


class WatchTriage(Suite[tuple[Watch, ...], TriageKnobs]):
    name = NAME
    description = "bench-watch-triage-description"
    knobs = TriageKnobs
    models = ("triage_model",)
    plugins = (fake,)

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "cases.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]]) -> Dataset[tuple[Watch, ...]]:
        if not records or records[0].get("dataset") != NAME or not isinstance(records[0].get("version"), int):
            raise BenchError(Message.of("bench-watch-triage-no-header"))
        watches: list[Watch] = []
        cases: list[Case] = []
        for number, record in enumerate(records[1:], start=2):
            if "watch" in record and isinstance(record.get("what"), str):
                keywords = tuple(str(k) for k in record.get("keywords", ()))
                kinds = tuple(str(k) for k in record.get("kinds", ("mail",)))
                watches.append(Watch(id=str(record["watch"]), what=record["what"], keywords=keywords, kinds=kinds))
            elif "case" in record and isinstance(record.get("title"), str):
                cases.append(Case(id=str(record["case"]), data=record))
            else:
                raise BenchError(Message.of("bench-watch-triage-bad-record", line=number))
        known = {w.id for w in watches}
        for case in cases:
            expected = case.data.get("expected", {})
            if not isinstance(expected, dict):
                raise BenchError(Message.of("bench-watch-triage-bad-label", case=case.id, watch="-"))
            for watch, label in expected.items():
                if watch not in known or label not in LABELS:
                    raise BenchError(Message.of("bench-watch-triage-bad-label", case=case.id, watch=watch))
        return Dataset(version=records[0]["version"], cases=tuple(cases), shared=tuple(watches))

    async def run(self, case: Case, shared: tuple[Watch, ...], trial: Trial[TriageKnobs]) -> Mapping[str, Any]:
        item = _incoming(case)
        language = trial.config.persona.language
        decisions = await decide(trial.knobs.algorithm, trial.model("triage_model"), shared, item, language=language)
        return {
            "decisions": [
                {
                    "watch": d.watch,
                    "gate": d.gate,
                    "asked": d.asked,
                    "matches": d.matches,
                    "urgent": d.urgent,
                    "unsorted": d.unsorted,
                }
                for d in decisions
            ]
        }

    def summarise(self, dataset: Dataset[tuple[Watch, ...]], results: Sequence[CaseResult]) -> Summary:
        cases = {c.id: c for c in dataset.cases}
        repetitions = len({r.repetition for r in results}) or 1
        matches, urgency = Confusion(), Confusion()
        missed: Counter[tuple[str, str, str]] = Counter()
        alarms: Counter[tuple[str, str]] = Counter()
        late: Counter[tuple[str, str]] = Counter()
        dropped = unread = 0
        for result in results:
            expected: Mapping[str, str] = cases[result.case].data.get("expected", {})
            decided = {d["watch"]: d for d in result.output["decisions"]}
            for watch in dataset.shared:
                decision = decided.get(watch.id, {})
                said, urgent, label = (
                    bool(decision.get("matches")),
                    bool(decision.get("urgent")),
                    expected.get(watch.id),
                )
                matches.add(predicted=said, expected=label is not None)
                urgency.add(predicted=said and urgent, expected=label == "urgent")
                unread += bool(decision.get("unsorted"))
                if label is not None and not said:
                    stage = "keywords" if decision.get("gate") is False else "model"
                    dropped += stage == "keywords"
                    missed[result.case, watch.id, stage] += 1
                elif label is None and said:
                    alarms[result.case, watch.id] += 1
                if label == "urgent" and said and not urgent:
                    late[result.case, watch.id] += 1

        def title(case: str) -> str:
            return str(cases[case].data["title"])

        findings = [
            Finding(
                group="bench-watch-triage-missed-list",
                case=case,
                detail=Message.of(
                    "bench-watch-triage-missed-item",
                    case=case,
                    watch=watch,
                    title=title(case),
                    stage=stage,
                    times=times,
                    of=repetitions,
                ),
            )
            for (case, watch, stage), times in sorted(missed.items())
        ]
        findings += [
            Finding(
                group=group,
                case=case,
                detail=Message.of(
                    "bench-watch-triage-item", case=case, watch=watch, title=title(case), times=times, of=repetitions
                ),
            )
            for group, counts in (
                ("bench-watch-triage-false-alarms-list", alarms),
                ("bench-watch-triage-not-urgent-list", late),
            )
            for (case, watch), times in sorted(counts.items())
        ]

        def metric(id: str, value: float | None, unit: Unit, better: Better) -> Metric:
            return Metric(id=id, label=f"bench-watch-triage-{id}", value=value, unit=unit, better=better)

        per = float(repetitions)
        return Summary(
            metrics=(
                metric("matches-f1", matches.f1, Unit.RATIO, Better.HIGHER),
                metric("matches-precision", matches.precision, Unit.RATIO, Better.HIGHER),
                metric("matches-recall", matches.recall, Unit.RATIO, Better.HIGHER),
                metric("urgent-precision", urgency.precision, Unit.RATIO, Better.HIGHER),
                metric("urgent-recall", urgency.recall, Unit.RATIO, Better.HIGHER),
                metric("missed", matches.false_negatives / per, Unit.COUNT, Better.LOWER),
                metric("dropped-by-keywords", dropped / per, Unit.COUNT, Better.LOWER),
                metric("false-alarms", matches.false_positives / per, Unit.COUNT, Better.LOWER),
                metric("unread-answers", unread / per, Unit.COUNT, Better.LOWER),
            ),
            findings=tuple(findings),
        )


def _incoming(case: Case) -> Incoming:
    data = case.data
    sender = data.get("from")
    return Incoming(
        source="bench",
        kind=str(data.get("kind", "mail")),
        title=str(data["title"]),
        body=str(data.get("body", "")),
        sender=str(sender) if sender else None,
        id=case.id,
    )
