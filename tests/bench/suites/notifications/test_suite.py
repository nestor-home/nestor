"""The notifications suite: its dataset, its scoring, and a run through the agent the runtime builds."""

from pathlib import Path

import pytest

from nestor.bench import BenchError, CaseResult, Knobs, Trial
from nestor.bench.runner import read_dataset
from nestor.bench.suites.notifications import suite
from nestor.bench.variants import load_variant
from nestor.core import ProviderError
from nestor.modules.conversation import SILENT
from nestor.runtime.plugins import Registry
from nestor.testing.cognition import ScriptedModel
from nestor.testing.i18n import EchoLocalizer

from ...kit import ORACLE


def test_the_shipped_dataset_asks_for_both_answers_and_never_silence_where_it_must_tell() -> None:
    dataset, _ = read_dataset(suite, suite.dataset())
    expected = [c.data["expected"] for c in dataset.cases]
    assert expected.count("silent") >= 8 and expected.count("tell") >= 8
    assert all(c.data["expected"] == "tell" for c in dataset.cases if c.data.get("must_tell"))


@pytest.mark.parametrize(
    "line",
    [
        {"case": "n1", "source": "message", "text": "t", "expected": "maybe"},
        {"case": "n1", "source": "rumour", "text": "t", "expected": "tell"},
        {"case": "n1", "source": "task", "result": "r", "expected": "tell"},
    ],
)
def test_a_case_the_suite_cannot_score_is_refused(line: dict[str, object]) -> None:
    with pytest.raises(BenchError) as raised:
        suite.load([{"dataset": "notifications", "version": 1}, line], suite.dataset())
    assert raised.value.message.id == "bench-notifications-bad-record"


def answered(case: str, told: bool, said: str = "", failed: bool = False) -> CaseResult:
    return CaseResult(case=case, repetition=0, output={"told": told, "said": said, "failed": failed})


def test_scores_tell_silence_from_noise_and_name_the_wrong_decisions() -> None:
    dataset = suite.load(
        [
            {"dataset": "notifications", "version": 1},
            {"case": "quiet", "source": "task", "objective": "o", "result": "nothing", "expected": "silent"},
            {"case": "found", "source": "task", "objective": "o", "result": "a deal", "expected": "tell"},
            {"case": "asked", "source": "message", "text": "call back", "expected": "tell", "must_tell": True},
            {"case": "noisy", "source": "task", "objective": "o", "result": "nothing either", "expected": "silent"},
        ],
        suite.dataset(),
    )
    summary = suite.summarise(
        dataset,
        [
            answered("quiet", False, "rien sous 1 600 €"),
            answered("found", True, "Bonne affaire."),
            answered("asked", False, "", failed=True),
            answered("noisy", True, "[SILENCE] Rien à signaler."),
        ],
    )
    metrics = {m.id: m.value for m in summary.metrics}
    assert metrics["accuracy"] == 0.5
    assert (metrics["unsaid"], metrics["noise"]) == (0.5, 0.5)
    assert (metrics["silences-with-reason"], metrics["marker-sent"], metrics["failed"]) == (1.0, 1, 1)
    assert sorted((f.group, f.case) for f in summary.findings) == [
        ("bench-notifications-noise-list", "noisy"),
        ("bench-notifications-unsaid-list", "asked"),
    ]


async def test_a_case_runs_through_the_variant_s_persona_and_model(tmp_path: Path) -> None:
    path = tmp_path / "richie.yaml"
    path.write_text("models: {m: {type: language, provider: oracle}}\npersona: {name: Richie, language: French}\n")
    config = load_variant(path, suite, Registry((ORACLE,)), EchoLocalizer(), environ={}).config
    dataset, _ = read_dataset(suite, suite.dataset())
    case = next(c for c in dataset.cases if c.data["expected"] == "silent")
    model = ScriptedModel(f"{SILENT} rien sous 1 600 €")

    def trial(variant: str, model: ScriptedModel) -> Trial[Knobs]:
        return Trial(
            variant=variant,
            knobs=Knobs(),
            config=config,
            models={"written": model},
            repetition=0,
            seed=0,
            localizer=EchoLocalizer(),
        )

    assert await suite.run(case, None, trial("richie", model)) == {
        "told": False,
        "failed": False,
        "said": "rien sous 1 600 €",
    }
    assert "write in French" in model.requests[0].messages[0].text, "the variant's persona writes it"
    down = ScriptedModel(fail=ProviderError("openrouter", "503", transient=True))
    failed = await suite.run(case, None, trial("down", down))
    assert failed["failed"] and not failed["told"]
