"""The routing suite: its dataset, its scoring, and a turn of the agent the runtime builds with the variant's executors
and tools, none of which runs."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from nestor.bench import BenchError, CaseResult, Knobs, Trial
from nestor.bench.runner import read_dataset
from nestor.bench.suites.routing import suite
from nestor.bench.types import Case
from nestor.bench.variants import load_variant
from nestor.core import ProviderError
from nestor.modules.cognition.model import ToolCall, ToolSpec
from nestor.modules.cognition.tools import Tool, ToolContext, ToolOutput, ToolProvider
from nestor.runtime.config import NestorConfig
from nestor.runtime.plugins import Registry
from nestor.testing.cognition import ScriptedExecutor, ScriptedModel
from nestor.testing.i18n import EchoLocalizer

from ...kit import ORACLE

HEADER = {"dataset": "routing", "version": 1}


def test_the_shipped_dataset_asks_for_each_kind_of_route() -> None:
    dataset, _ = read_dataset(suite, suite.dataset())
    firsts = [c.data["expected"][0][0] if c.data["expected"] else "none" for c in dataset.cases]
    kinds = {route.split(":")[0] for route in firsts}
    assert kinds == {"tool", "delegate", "none"}
    assert firsts.count("none") >= 6 and sum(r.startswith("delegate:") for r in firsts) >= 3


@pytest.mark.parametrize(
    "line",
    [
        {"case": "r1", "said": "s", "expected": "none"},
        {"case": "r1", "said": "s", "expected": [["call:weather"]]},
        {"case": "r1", "said": "s", "expected": [[]]},
        {"case": "r1", "expected": []},
    ],
)
def test_a_case_the_suite_cannot_score_is_refused(line: dict[str, object]) -> None:
    with pytest.raises(BenchError) as raised:
        suite.load([HEADER, line], suite.dataset())
    assert raised.value.message.id == "bench-routing-bad-record"


def routed(case: str, route: str, right: Sequence[str], failed: bool = False) -> CaseResult:
    output = {"route": route, "calls": [route], "right": list(right), "said": "", "failed": failed}
    return CaseResult(case=case, repetition=0, output=output)


def test_scores_routes_and_names_each_wrong_one_by_what_went_wrong() -> None:
    lines = [{"case": c, "said": c, "expected": []} for c in ("ok", "slow", "lost", "astray", "hello", "other")]
    dataset = suite.load([HEADER, *lines], suite.dataset())
    summary = suite.summarise(
        dataset,
        [
            routed("ok", "tool:weather", ["tool:weather"]),
            routed("slow", "delegate:hermes", ["tool:weather"]),
            routed("lost", "none", ["delegate:hermes"]),
            routed("astray", "delegate:codex", ["delegate:hermes"]),
            routed("hello", "none", ["none"]),
            routed("other", "tool:route", ["tool:find_place"], failed=True),
        ],
    )
    metrics = {m.id: m.value for m in summary.metrics}
    assert metrics["accuracy"] == 2 / 6
    assert (metrics["missed"], metrics["wrong-executor"]) == (0.5, 0.5), "of the two cases to hand over"
    assert metrics["needless"] == 0.25, "of the four not to hand over"
    assert metrics["failed"] == 1
    assert sorted((f.group, f.case) for f in summary.findings) == [
        ("bench-routing-missed-list", "lost"),
        ("bench-routing-needless-list", "slow"),
        ("bench-routing-other-list", "other"),
        ("bench-routing-wrong-executor-list", "astray"),
    ]


class Weather(ToolProvider):
    name = "weather-tools"

    def __init__(self) -> None:
        self.asked = 0

    def tools(self) -> Sequence[Tool]:
        return (Tool(spec=ToolSpec("weather", "The weather at a place."), run=self._run),)

    async def _run(self, arguments: Mapping[str, object], context: ToolContext) -> ToolOutput:
        self.asked += 1
        return {"sky": "rain"}


@pytest.fixture
def config(tmp_path: Path) -> NestorConfig:
    path = tmp_path / "richie.yaml"
    path.write_text(
        "models: {m: {type: language, provider: oracle}}\n"
        "persona: {name: Richie, language: French}\n"
        "household: [{id: mathis, name: Mathis}, {id: mathilde, name: Mathilde}]\n"
    )
    return load_variant(path, suite, Registry((ORACLE,)), EchoLocalizer(), environ={}).config


def trial(
    config: NestorConfig, model: ScriptedModel, executors: Sequence[ScriptedExecutor], tools: Sequence[ToolProvider]
) -> Trial[Knobs]:
    return Trial(
        variant="richie",
        knobs=Knobs(),
        config=config,
        models={"written": model},
        repetition=0,
        seed=0,
        localizer=EchoLocalizer(),
        executors=tuple(executors),
        tools=tuple(tools),
    )


WEATHER = Case("r01", {"said": "Il va pleuvoir demain à Lyon ?", "expected": [["tool:weather"], ["delegate:hermes"]]})


async def test_the_right_route_is_the_first_the_variant_can_take_and_nothing_is_run(config: NestorConfig) -> None:
    hermes, weather = ScriptedExecutor(), Weather()
    hermes.name, hermes.description = "hermes", "chercher sur le web"
    model = ScriptedModel(ToolCall("c1", "weather", {"place": "Lyon"}), "Pluie.")
    took = await suite.run(WEATHER, None, trial(config, model, [hermes], [weather]))
    assert (took["route"], took["right"], took["failed"]) == ("tool:weather", ["tool:weather"], False)
    assert len(model.requests) == 1, "the first decision only"
    assert model.requests[0].messages[-1].content == WEATHER.data["said"], "it reads the request"
    assert weather.asked == 0
    prompt = model.requests[0].messages[0].text
    assert "hermes: chercher sur le web" in prompt and "write in French" in prompt, "the runtime's instructions"
    assert {"delegate_task", "schedule", "message_person", "weather"} <= {t.name for t in model.requests[0].tools}

    handed = ScriptedModel(ToolCall("c1", "delegate_task", {"objective": "météo de Lyon demain"}))
    took = await suite.run(WEATHER, None, trial(config, handed, [hermes], []))
    assert (took["route"], took["right"]) == ("delegate:hermes", ["delegate:hermes"]), "the only executor, unnamed"
    assert hermes.objectives == []

    alone = await suite.run(WEATHER, None, trial(config, ScriptedModel("Je ne peux pas le savoir."), [], []))
    assert (alone["route"], alone["right"], alone["said"]) == ("none", ["none"], "Je ne peux pas le savoir.")


async def test_a_model_down_is_a_failed_turn(config: NestorConfig) -> None:
    down = ScriptedModel(fail=ProviderError("openrouter", "503", transient=True))
    took = await suite.run(WEATHER, None, trial(config, down, [], [Weather()]))
    assert took["failed"] and took["route"] == "none"
