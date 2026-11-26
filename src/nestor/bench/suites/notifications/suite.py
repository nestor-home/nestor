"""The notifications suite: does the agent stay silent when a notification has nothing to tell, and only then?

Its dataset (`cases.jsonl`) starts with a header, then notifications with the answer expected:

    {"dataset": "notifications", "version": 1}
    {"case": "n01", "source": "task", "objective": "…", "result": "…", "expected": "silent"}
    {"case": "n19", "source": "alert", "title": "Mails de la banque", "instruction": "Préviens Mathis",
     "condition": "les mails de ma banque", "summary": "…", "from": "…", "subject": "…", "body": "…",
     "expected": "tell"}
    {"case": "n21", "source": "message", "text": "Léa asked you to pass this on…", "must_tell": true,
     "expected": "tell"}

A task's notification (`objective`, then `result`, or `error` with `status` "failed"; `written` unless false) and an
alert's (`title`, `instruction`, and `condition` with the mail that rang it, `from`, `subject`, `body`, matched as
`summary` says; due now without a mail) are written by the code that writes them in the house; other sources give
their `text`. `expected` is `tell` or `silent`.

Each is composed for the household's first person, in writing, by the agent the runtime builds (persona and prompt
layers), with the variant's written model, no tools and no history: what is measured is the decision on what the
notification says.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from nestor.bench.errors import BenchError
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import ContractError, PersonId, ProviderError
from nestor.core.i18n import Locale, Message
from nestor.modules.channels import Address, Medium
from nestor.modules.cognition.delegation import Task, TurnEnded, TurnStatus
from nestor.modules.cognition.tools import Toolbox
from nestor.modules.conversation import (
    SILENT,
    About,
    Agent,
    Attachments,
    ModelChoice,
    Notification,
    Persona,
    Silence,
    Source,
)
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import Alert, Frequency, Incoming, Ring, RingCause
from nestor.modules.initiative.alerts import ring_instruction
from nestor.modules.initiative.returns import turn_instruction
from nestor.modules.journal import Journal
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

NAME = "notifications"
EXPECTED = frozenset({"tell", "silent"})
CHAT = Address("bench", "chat")


class Notifications(Suite[None, Knobs]):
    """The variant's persona and written model say how it answers: no knobs of its own."""

    name = NAME
    description = "bench-notifications-description"
    knobs = Knobs
    models = ("written",)

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}  # by variant

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "cases.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[None]:
        if not records or records[0].get("dataset") != NAME or not isinstance(records[0].get("version"), int):
            raise BenchError(Message.of("bench-notifications-no-header"))
        cases = []
        for number, record in enumerate(records[1:], start=2):
            try:
                _text(record)
            except (KeyError, ValueError, TypeError):
                raise BenchError(Message.of("bench-notifications-bad-record", line=number)) from None
            if record.get("expected") not in EXPECTED or "case" not in record:
                raise BenchError(Message.of("bench-notifications-bad-record", line=number))
            cases.append(Case(id=str(record["case"]), data=record))
        return Dataset(version=records[0]["version"], cases=tuple(cases), shared=None)

    async def run(self, case: Case, shared: None, trial: Trial[Knobs]) -> Mapping[str, Any]:
        data = case.data
        notification = Notification(
            _text(data, trial.config.persona.timezone),
            About(Source(data["source"]), case.id),
            must_tell=bool(data.get("must_tell")),
        )
        try:
            agent = self._agents.get(trial.variant) or self._agents.setdefault(trial.variant, _agent(trial))
            composed = await agent.compose(CHAT, PERSON, notification, Medium.WRITTEN)
        except ProviderError as error:  # as the courier: the delivery fails
            return {"told": False, "failed": True, "said": str(error)}
        if isinstance(composed, Silence):
            return {"told": False, "failed": False, "said": composed.reason}
        return {"told": True, "failed": False, "said": composed.text}

    def summarise(self, dataset: Dataset[None], results: Sequence[CaseResult]) -> Summary:
        cases = {c.id: c for c in dataset.cases}
        repetitions = len({r.repetition for r in results}) or 1
        right = 0
        counted: Counter[str] = Counter()
        wrong: Counter[tuple[str, str]] = Counter()  # (group, case)
        failed = leaked = silent_with_reason = silences = 0
        for result in results:
            data, output = cases[result.case].data, result.output
            expected = str(data["expected"])
            counted[expected] += 1
            failed += bool(output["failed"])
            if output["told"]:  # the marker, even misspelt or translated ("[SILENCE]"), would be read as words
                leaked += str(output["said"]).lstrip().upper().startswith(SILENT[:6]) or SILENT in str(output["said"])
            elif not output["failed"]:
                silences += 1
                silent_with_reason += bool(str(output["said"]).strip())
            decided = "tell" if output["told"] else "silent"
            if decided == expected:
                right += 1
            elif expected == "tell":
                wrong["bench-notifications-unsaid-list", result.case] += 1
            else:
                wrong["bench-notifications-noise-list", result.case] += 1
        unsaid = sum(n for (group, _), n in wrong.items() if group == "bench-notifications-unsaid-list")
        noise = sum(n for (group, _), n in wrong.items() if group == "bench-notifications-noise-list")

        def ratio(part: float, whole: float) -> float | None:
            return part / whole if whole else None

        def metric(id: str, value: float | None, unit: Unit, better: Better) -> Metric:
            return Metric(id=id, label=f"bench-notifications-{id}", value=value, unit=unit, better=better)

        findings = tuple(
            Finding(
                group=group,
                case=case,
                detail=Message.of(
                    "bench-notifications-item",
                    case=case,
                    text=str(cases[case].data.get("label") or _text(cases[case].data))[:160],
                    times=times,
                    of=repetitions,
                ),
            )
            for (group, case), times in sorted(wrong.items())
        )
        return Summary(
            metrics=(
                metric("accuracy", ratio(right, len(results)), Unit.RATIO, Better.HIGHER),
                metric("unsaid", ratio(unsaid, counted["tell"]), Unit.RATIO, Better.LOWER),
                metric("noise", ratio(noise, counted["silent"]), Unit.RATIO, Better.LOWER),
                metric("silences-with-reason", ratio(silent_with_reason, silences), Unit.RATIO, Better.HIGHER),
                metric("marker-sent", leaked / repetitions, Unit.COUNT, Better.LOWER),
                metric("failed", failed / repetitions, Unit.COUNT, Better.LOWER),
            ),
            findings=findings,
        )


def _text(data: Mapping[str, Any], timezone: str = "UTC") -> str:
    """The notification's text, as the house writes it."""
    source = Source(data["source"])
    if source is Source.TASK:
        status = TurnStatus(data.get("status", "completed"))
        ended = TurnEnded(
            source="bench",
            task_id="bench",
            turn_id="bench",
            status=status,
            result=str(data["result"]) if status is TurnStatus.COMPLETED else None,
            error=None if status is TurnStatus.COMPLETED else str(data["error"]),
            duration_s=0.0,
        )
        now = datetime.now(ZoneInfo(timezone))
        task = Task(
            id="bench",
            title=str(data.get("title", "Tâche")),
            executor=str(data.get("executor", "hermes")),
            owner=PERSON.id,
            origin=CHAT,
            created_at=now,
            last_activity=now,
        )
        return turn_instruction(task, str(data["objective"]), ended, written=bool(data.get("written", True)))
    if source is Source.ALERT:
        return _rang(data, timezone)
    if not isinstance(data["text"], str):
        raise TypeError("text")
    return data["text"]


def _rang(data: Mapping[str, Any], timezone: str) -> str:
    """An alert ringing now: on a mail the triage matched when the case gives one, else at its time (due now: an
    alert dated otherwise reads as late)."""
    now = datetime.now(ZoneInfo(timezone))
    alert = Alert(
        title=str(data["title"]),
        instruction=str(data["instruction"]),
        condition=data.get("condition"),
        at=None if "subject" in data else now,
        kinds=("mail",) if "subject" in data else (),
        frequency=Frequency.ONCE,
        owner=PERSON.id,
    )
    if "subject" not in data:
        return ring_instruction(
            alert, Ring(id="bench", at=now, cause=RingCause.DUE, due_at=now), PERSON, timezone, None
        )
    mail = Incoming(
        source="gmail-mathis",
        kind="mail",
        title=str(data["subject"]),
        body=str(data.get("body", "")),
        sender=str(data["from"]),
        owner=PERSON.id,
    )
    ring = Ring(
        id="bench",
        at=now,
        cause=RingCause.MATCH,
        item_id=mail.id,
        item_title=mail.title,
        item_kind=mail.kind,
        item_source=mail.source,
        summary=str(data["summary"]),
    )
    return ring_instruction(alert, ring, PERSON, timezone, mail)


PERSON = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("bench:chat"),), reach=CHAT)


def _agent(trial: Trial[Knobs]) -> Agent:
    """The agent as the runtime builds it, with the variant's persona and written model, and nothing to call."""
    persona, localizer = trial.config.persona, trial.localizer
    if localizer is None:
        raise ContractError("the notifications suite runs the agent: it needs the engine's localizer")
    journal = Journal(MemoryEventLog())
    return Agent(
        models=ModelChoice.single(trial.model("written")),
        persona=Persona(**{**persona.model_dump(), "locale": Locale(persona.locale)}),
        localizer=localizer,
        journal=journal,
        household=Household([PERSON]),
        toolbox=Toolbox(journal),
        attachments=Attachments(MemoryBlobStore()),
    )
