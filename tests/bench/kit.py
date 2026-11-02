"""A small suite for testing the engine: each case asks a question, a scripted model answers, the suite scores
exact answers. Its model kind takes a reply table and a key, like a real hosted model would."""

import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr

from nestor.bench import Better, Case, CaseResult, Dataset, Finding, Knobs, Metric, Suite, Summary, Trial, Unit
from nestor.bench.recording import Cache
from nestor.bench.results import Run
from nestor.bench.runner import Plan, read_dataset, run_suite
from nestor.bench.variants import Variant, load_variant
from nestor.core import ProviderError
from nestor.core.i18n import Message
from nestor.modules.cognition import (
    ConversationModel,
    Finished,
    FinishReason,
    ModelOutput,
    ModelRequest,
    TextDelta,
    Usage,
)
from nestor.modules.cognition import (
    Message as Said,
)
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Registry, Services
from nestor.testing.i18n import EchoLocalizer

CASES = [
    {"case": "c1", "question": "capital of France", "answer": "Paris"},
    {"case": "c2", "question": "two plus two", "answer": "4"},
    {"case": "c3", "question": "colour of the sky", "answer": "blue"},
]


class Oracle(ConversationModel):
    """Answers from a table, reports usage and the model it says it is; counts the requests it got."""

    name = "oracle"

    def __init__(self, replies: Mapping[str, str], served: str, fail_on: str | None = None) -> None:
        self.replies, self.served, self.fail_on = replies, served, fail_on
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        self.requests.append(request)
        question = request.messages[-1].content
        if question == self.fail_on:
            raise ProviderError("oracle", "overloaded", transient=True)
        reply = self.replies.get(question, "?")
        yield TextDelta(reply)
        yield Finished(
            FinishReason.STOP, Usage(input_tokens=len(question), output_tokens=len(reply), cost=0.001), self.served
        )


class OracleSettings(AdapterSettings):
    replies: dict[str, str] = Field(default_factory=dict)
    served: str = "oracle/v1"
    api_key: SecretStr | None = None
    fail_on: str | None = None


BUILT: list[Oracle] = []


def _build(settings: OracleSettings, name: str, services: Services) -> Oracle:
    BUILT.append(oracle := Oracle(settings.replies, settings.served, settings.fail_on))
    return oracle


ORACLE = Plugin(Family.MODEL, "oracle", OracleSettings, _build)


class QuizKnobs(Knobs):
    shout: bool = False


class Quiz(Suite[str, QuizKnobs]):
    name = "quiz"
    description = "bench-help"
    knobs = QuizKnobs
    models = ("triage_model",)
    plugins = (ORACLE,)

    def __init__(self, dataset: Path | None = None) -> None:
        self._dataset = dataset

    def dataset(self) -> Traversable:
        assert self._dataset is not None
        return self._dataset

    def load(self, records: Sequence[Mapping[str, Any]]) -> Dataset[str]:
        return Dataset(version=1, cases=tuple(Case(id=r["case"], data=r) for r in records), shared="answer:")

    async def run(self, case: Case, shared: str, trial: Trial[QuizKnobs]) -> Mapping[str, Any]:
        request = ModelRequest(messages=(Said.user(case.data["question"]),))
        try:
            reply = "".join(
                [o.text async for o in trial.model("triage_model").stream(request) if isinstance(o, TextDelta)]
            )
        except ProviderError:
            reply = ""
        return {"reply": reply.upper() if trial.knobs.shout else reply}

    def summarise(self, dataset: Dataset[str], results: Sequence[CaseResult]) -> Summary:
        expected = {c.id: c.data["answer"] for c in dataset.cases}
        wrong = [r for r in results if r.output["reply"] != expected[r.case]]
        accuracy = 1 - len(wrong) / len(results) if results else None
        return Summary(
            metrics=(
                Metric(
                    id="accuracy",
                    label="bench-watch-triage-matches-f1",
                    value=accuracy,
                    unit=Unit.RATIO,
                    better=Better.HIGHER,
                ),
            ),
            findings=tuple(
                Finding(
                    group="bench-watch-triage-missed-list", case=r.case, detail=Message.of("bench-wrote", path=r.case)
                )
                for r in wrong
            ),
        )


def write_cases(folder: Path, cases: Sequence[Mapping[str, Any]] = CASES) -> Path:
    path = folder / "cases.jsonl"
    path.write_text("".join(json.dumps(c) + "\n" for c in cases))
    return path


def write_variant(folder: Path, name: str, text: str) -> Path:
    path = folder / f"{name}.yaml"
    path.write_text(text)
    return path


ALL_RIGHT = (
    "triage_model: {kind: oracle, replies: {capital of France: Paris, two plus two: '4', colour of the sky: blue}}\n"
)


def registry(suite: Suite[Any, Any]) -> Registry:
    return Registry(suite.plugins)


def variant(folder: Path, suite: Quiz, name: str = "right", text: str = ALL_RIGHT) -> Variant[Any]:
    return load_variant(write_variant(folder, name, text), suite, registry(suite), EchoLocalizer(), environ={})


async def quiz_runs(folder: Path, *variants: Variant[Any], plan: Plan | None = None) -> list[Run]:
    suite = Quiz(write_cases(folder))
    dataset, info = read_dataset(suite, suite.dataset())
    return await run_suite(suite, dataset, info, variants, plan or Plan(), Cache(folder / "cache"))
