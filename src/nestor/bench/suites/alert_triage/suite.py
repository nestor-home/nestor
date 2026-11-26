"""The alert-triage suite: does an incoming mail match what someone asked to be told about?

Its dataset (`cases.jsonl`) starts with a header, then the alerts with their condition, then the mails with the alerts
they match:

    {"dataset": "alert-triage", "version": 2}
    {"alert": "a-stroller", "condition": "le colis de la poussette"}
    {"case": "m001", "from": "...", "title": "...", "body": "...", "expected": ["a-stroller"]}

An alert a mail does not name in `expected` is not matched. Every (mail, alert) pair is scored. How urgent an alert is
was set when it was created: the triage only says whether an item matches.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.metrics import Confusion
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.suites.alert_triage.algorithms import Algorithm, decide
from nestor.bench.suites.alert_triage.fake import plugin as fake
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core.i18n import Message
from nestor.modules.initiative import Alert, Frequency, Incoming

NAME = "alert-triage"


class TriageKnobs(Knobs):
    algorithm: Algorithm = Algorithm.BATCH


class AlertTriage(Suite[tuple[Alert, ...], TriageKnobs]):
    name = NAME
    description = "bench-alert-triage-description"
    knobs = TriageKnobs
    models = ("alerts",)
    plugins = (fake,)

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "cases.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[tuple[Alert, ...]]:
        if not records or records[0].get("dataset") != NAME or not isinstance(records[0].get("version"), int):
            raise BenchError(Message.of("bench-alert-triage-no-header"))
        alerts: list[Alert] = []
        cases: list[Case] = []
        for number, record in enumerate(records[1:], start=2):
            if "alert" in record and isinstance(record.get("condition"), str):
                condition = record["condition"]
                alerts.append(
                    Alert(
                        id=str(record["alert"]),
                        title=condition,
                        instruction="tell them",
                        condition=condition,
                        kinds=tuple(str(k) for k in record.get("kinds", ("mail",))),
                        frequency=Frequency.EVERY_TIME,
                    )
                )
            elif "case" in record and isinstance(record.get("title"), str):
                cases.append(Case(id=str(record["case"]), data=record))
            else:
                raise BenchError(Message.of("bench-alert-triage-bad-record", line=number))
        known = {a.id for a in alerts}
        for case in cases:
            expected = case.data.get("expected", [])
            if not isinstance(expected, list):
                raise BenchError(Message.of("bench-alert-triage-bad-label", case=case.id, alert="-"))
            for alert in expected:
                if alert not in known:
                    raise BenchError(Message.of("bench-alert-triage-bad-label", case=case.id, alert=str(alert)))
        return Dataset(version=records[0]["version"], cases=tuple(cases), shared=tuple(alerts))

    async def run(self, case: Case, shared: tuple[Alert, ...], trial: Trial[TriageKnobs]) -> Mapping[str, Any]:
        item = _incoming(case)
        language = trial.config.persona.language
        decisions = await decide(trial.knobs.algorithm, trial.model("alerts"), shared, item, language=language)
        return {"decisions": [{"alert": d.alert, "matches": d.matches, "unsorted": d.unsorted} for d in decisions]}

    def summarise(self, dataset: Dataset[tuple[Alert, ...]], results: Sequence[CaseResult]) -> Summary:
        cases = {c.id: c for c in dataset.cases}
        repetitions = len({r.repetition for r in results}) or 1
        matches = Confusion()
        missed: Counter[tuple[str, str]] = Counter()
        alarms: Counter[tuple[str, str]] = Counter()
        unsorted = 0
        for result in results:
            expected = set(cases[result.case].data.get("expected", []))
            decided = {d["alert"]: d for d in result.output["decisions"]}
            for alert in dataset.shared:
                decision = decided.get(alert.id, {})
                said, wanted = bool(decision.get("matches")), alert.id in expected
                matches.add(predicted=said, expected=wanted)
                unsorted += bool(decision.get("unsorted"))
                if wanted and not said:
                    missed[result.case, alert.id] += 1
                elif said and not wanted:
                    alarms[result.case, alert.id] += 1

        def title(case: str) -> str:
            return str(cases[case].data["title"])

        findings = [
            Finding(
                group=group,
                case=case,
                detail=Message.of(
                    "bench-alert-triage-item", case=case, alert=alert, title=title(case), times=times, of=repetitions
                ),
            )
            for group, counts in (
                ("bench-alert-triage-missed-list", missed),
                ("bench-alert-triage-false-alarms-list", alarms),
            )
            for (case, alert), times in sorted(counts.items())
        ]

        def metric(id: str, value: float | None, unit: Unit, better: Better) -> Metric:
            return Metric(id=id, label=f"bench-alert-triage-{id}", value=value, unit=unit, better=better)

        per = float(repetitions)
        return Summary(
            metrics=(
                metric("matches-f1", matches.f1, Unit.RATIO, Better.HIGHER),
                metric("matches-precision", matches.precision, Unit.RATIO, Better.HIGHER),
                metric("matches-recall", matches.recall, Unit.RATIO, Better.HIGHER),
                metric("missed", matches.false_negatives / per, Unit.COUNT, Better.LOWER),
                metric("false-alarms", matches.false_positives / per, Unit.COUNT, Better.LOWER),
                metric("unsorted", unsorted / per, Unit.COUNT, Better.LOWER),
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
