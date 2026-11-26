"""The routing suite: for a request, does the agent hand it to the right executor, use the right tool of its own, or
answer by itself (or say it cannot) without starting a task?

Its dataset (`cases.jsonl`) starts with a header, then requests with the routes expected, best first:

    {"dataset": "routing", "version": 1}
    {"case": "r01", "said": "Il va pleuvoir demain à Lyon ?", "expected": [["tool:weather"], ["delegate:hermes"]]}
    {"case": "r20", "said": "Salut, ça va ?", "expected": []}
    {"case": "r27", "said": "C'est un Hisense", "tasks": [{"id": "dish", "title": "Lave-vaisselle", "executor":
     "codex", "question": "Quelle marque ?"}], "expected": [["continue:dish"]]}

A route is `tool:<name>`, `delegate:<executor>`, `continue:<task>` or `none` (no tool: it answers, or says it cannot).
`tasks` are the person's tasks already there, ready or (with a `question`) waiting on them, each with its executor.
`expected` is a list of tiers; the right routes are those of the first tier the variant can take (its tool is offered,
its executor plugged), `none` when it can take none. So a weather question is right with the weather tool where there
is one, with an executor that searches the web otherwise, and answered without a task where neither exists. Executors
are named as the variant names them (by default, their plugin: `hermes`, `codex`, `claude-code`).

Each request is one written turn of the household's first person, answered by the agent the runtime builds (persona,
prompt layers, delegation, alerts over a mailbox and a dishwasher's webhook, messages, and the variant's `executors`
and `tools`) with the variant's written model, for one round: what is measured is the first decision. No tool runs
and no executor is reached.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from nestor.bench.errors import BenchError
from nestor.bench.ports import Knobs, Suite, Trial
from nestor.bench.types import Better, Case, CaseResult, Dataset, Finding, Metric, Summary, Unit
from nestor.core import ContractError, PersonId
from nestor.core.i18n import Locale, Message
from nestor.modules.channels import Address, InboundMessage, Sender
from nestor.modules.cognition import TurnStatus
from nestor.modules.cognition.delegation import TaskCreated, TurnEnded
from nestor.modules.cognition.delegation.assistant import Delegation
from nestor.modules.cognition.delegation.service import TaskManager
from nestor.modules.cognition.tools import Tool, Toolbox, ToolCalled, ToolContext, ToolOutput, ToolProvider
from nestor.modules.conversation import (
    Agent,
    AgentSettings,
    Attachments,
    FallbackSpoken,
    ModelChoice,
    Persona,
)
from nestor.modules.household import Household
from nestor.modules.initiative import AlertBook, AlertTools, MessageBook, MessageTools
from nestor.modules.journal import Journal
from nestor.runtime.app import offered_tools
from nestor.testing.initiative import QueuedSource
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

NAME = "routing"
NONE = "none"
ROUTES = ("tool:", "delegate:", "continue:")
DELEGATE = "start_task"
CONTINUE = "continue_task"
CHAT = Address("bench", "chat")
# what alerts can wait for in the household of the bench: a mailbox, and the dishwasher's webhook
SOURCES = (
    QueuedSource(kinds=("mail",)),
    QueuedSource(kinds=("dishwasher",), structured=True, follows={"dishwasher": ("lave-vaisselle",)}),
)


class Routing(Suite[None, Knobs]):
    """The variant's persona, written model, executors and tools say how it routes: no knobs of its own."""

    name = NAME
    description = "bench-routing-description"
    knobs = Knobs
    models = ("written",)
    components = True

    def dataset(self) -> Traversable:
        return files(__package__ or __name__) / "cases.jsonl"

    def load(self, records: Sequence[Mapping[str, Any]], source: Traversable | Path) -> Dataset[None]:
        if not records or records[0].get("dataset") != NAME or not isinstance(records[0].get("version"), int):
            raise BenchError(Message.of("bench-routing-no-header"))
        cases = []
        for number, record in enumerate(records[1:], start=2):
            if (
                "case" not in record
                or not isinstance(record.get("said"), str)
                or _tiers(record.get("expected")) is None
            ):
                raise BenchError(Message.of("bench-routing-bad-record", line=number))
            cases.append(Case(id=str(record["case"]), data=record))
        return Dataset(version=records[0]["version"], cases=tuple(cases), shared=None)

    async def run(self, case: Case, shared: None, trial: Trial[Knobs]) -> Mapping[str, Any]:
        agent, tasks = _agent(trial)
        person = agent.household.people[0]
        seeded = [await _seed(agent.journal, task, person.id) for task in case.data.get("tasks", [])]
        offered = {
            *(f"tool:{s.name}" for s in agent.toolbox.specs()),
            *(f"delegate:{e.name}" for e in trial.executors),
            *(f"continue:{task_id}" for task_id in seeded),
        }
        tiers = _tiers(case.data["expected"]) or ()
        right = next((routes for tier in tiers if (routes := [r for r in tier if r in offered])), [NONE])
        events = agent.journal.subscribe(ToolCalled, FallbackSpoken)
        async with tasks:  # the tasks seeded, as the journal tells them
            reply = agent.respond(
                InboundMessage(address=CHAT, sender=Sender("bench", person=person.id), text=str(case.data["said"]))
            )
            said = "".join([chunk async for chunk in reply if isinstance(chunk, str)]).strip()
        events.close()
        calls = [event async for event in events]
        failed = any(isinstance(e, FallbackSpoken) for e in calls)
        routes = [_route(e, trial) for e in calls if isinstance(e, ToolCalled)]
        return {"route": routes[0] if routes else NONE, "calls": routes, "right": right, "said": said, "failed": failed}

    def summarise(self, dataset: Dataset[None], results: Sequence[CaseResult]) -> Summary:
        cases = {c.id: c for c in dataset.cases}
        repetitions = len({r.repetition for r in results}) or 1
        right = failed = 0
        counted: Counter[str] = Counter()  # by the kind of route expected: tool, delegate, none
        wrong: Counter[tuple[str, str, str]] = Counter()  # (group, case, route taken)
        for result in results:
            output = result.output
            failed += bool(output["failed"])
            expected = _kind(output["right"][0])
            counted[expected] += 1
            if output["route"] in output["right"]:
                right += 1
                continue
            taken = _kind(output["route"])
            if expected == "delegate" and taken == "delegate":
                group = "bench-routing-wrong-executor-list"
            elif taken == "delegate":
                group = "bench-routing-needless-list"
            elif expected == "delegate":
                group = "bench-routing-missed-list"
            else:
                group = "bench-routing-other-list"
            wrong[group, result.case, output["route"]] += 1

        def share(group: str, whole: float) -> float | None:
            part = sum(n for (g, _, _), n in wrong.items() if g == group)
            return part / whole if whole else None

        def metric(id: str, value: float | None, unit: Unit, better: Better) -> Metric:
            return Metric(id=id, label=f"bench-routing-{id}", value=value, unit=unit, better=better)

        findings = tuple(
            Finding(
                group=group,
                case=case,
                detail=Message.of(
                    "bench-routing-item",
                    case=case,
                    said=str(cases[case].data["said"])[:160],
                    route=route,
                    times=times,
                    of=repetitions,
                ),
            )
            for (group, case, route), times in sorted(wrong.items())
        )
        return Summary(
            metrics=(
                metric("accuracy", right / len(results) if results else None, Unit.RATIO, Better.HIGHER),
                metric("missed", share("bench-routing-missed-list", counted["delegate"]), Unit.RATIO, Better.LOWER),
                metric(
                    "needless",
                    share("bench-routing-needless-list", counted["tool"] + counted[NONE]),
                    Unit.RATIO,
                    Better.LOWER,
                ),
                metric(
                    "wrong-executor",
                    share("bench-routing-wrong-executor-list", counted["delegate"]),
                    Unit.RATIO,
                    Better.LOWER,
                ),
                metric("failed", failed / repetitions, Unit.COUNT, Better.LOWER),
            ),
            findings=findings,
        )


def _tiers(value: object) -> tuple[tuple[str, ...], ...] | None:
    """The tiers of a case's `expected` (a tier of one route may be written alone), or `None` when they are not
    routes."""
    if not isinstance(value, list):
        return None
    tiers = tuple(tuple(tier) if isinstance(tier, list) else (tier,) for tier in value)
    routes = [route for tier in tiers for route in tier]
    if not all(tiers) or not all(isinstance(r, str) and (r == NONE or r.startswith(ROUTES)) for r in routes):
        return None
    return tiers


def _kind(route: str) -> str:
    """What a route does: a tool, a task handed over (a new one or one going on), or nothing."""
    kind = route.split(":", 1)[0]
    return "delegate" if kind == "continue" else kind


def _route(called: ToolCalled, trial: Trial[Knobs]) -> str:
    """`delegate:<executor>` for a task handed over (to the only executor when it names none), `continue:<task>` for
    one going on, else `tool:<name>`."""
    if called.name == CONTINUE:
        return f"continue:{called.arguments.get('task', '')}"
    if called.name != DELEGATE:
        return f"tool:{called.name}"
    executor = called.arguments.get("executor") or (trial.executors[0].name if trial.executors else "")
    return f"delegate:{executor}"


async def _dry(arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
    return {"ok": True}


async def _seed(journal: Journal, task: Mapping[str, Any], owner: PersonId) -> str:
    """One of the person's tasks already there, as the journal tells it: ready, or waiting on their answer to its
    `question`."""
    task_id, title = str(task["id"]), str(task["title"])
    question = task.get("question")
    status = TurnStatus.ASKED if question else TurnStatus.COMPLETED
    for event in (
        TaskCreated(
            source=NAME,
            task_id=task_id,
            title=title,
            executor=str(task["executor"]),
            owner=owner,
            origin=CHAT,
            turn_id=f"{task_id}-1",
            instruction=title,
            by=owner,
        ),
        TurnEnded(
            source=NAME,
            task_id=task_id,
            turn_id=f"{task_id}-1",
            status=status,
            result=str(task.get("result", "Fait.")),
            question=str(question) if question else None,
            duration_s=1.0,
        ),
    ):
        await journal.publish(event)
    return task_id


def _agent(trial: Trial[Knobs]) -> tuple[Agent, TaskManager]:
    """The agent as the runtime builds it, with the variant's persona, written model, executors and tools, for one
    round, its tools never run; and its task manager, to start once the case's tasks are seeded."""
    config, localizer = trial.config, trial.localizer
    if localizer is None:
        raise ContractError("the routing suite runs the agent: it needs the engine's localizer")
    journal = Journal(MemoryEventLog())
    household = Household(p.to_person() for p in config.household)
    tasks = TaskManager(journal, trial.executors)
    delegation = Delegation(tasks)
    messages = MessageTools(MessageBook(journal), household)
    alerts = AlertTools(AlertBook(journal, SOURCES, timezone=config.persona.timezone))
    providers: Sequence[ToolProvider] = (delegation, messages, alerts, *offered_tools(trial.tools))
    tools: list[Tool] = [replace(tool, run=_dry) for provider in providers for tool in provider.tools()]
    persona = config.persona
    agent = Agent(
        models=ModelChoice.single(trial.model("written")),
        persona=Persona(**{**persona.model_dump(), "locale": Locale(persona.locale)}),
        localizer=localizer,
        journal=journal,
        household=household,
        toolbox=Toolbox(journal, tools=tools),
        context=[delegation, messages, alerts],
        attachments=Attachments(MemoryBlobStore()),
        settings=AgentSettings(max_tool_rounds=1),
    )
    return agent, tasks
