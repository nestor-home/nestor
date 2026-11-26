"""The two triage algorithms on one item: how many calls, what each judges, and how failures count."""

import json
from collections.abc import Callable

import pytest

from nestor.bench.suites.alert_triage import Algorithm, Decision, decide
from nestor.core import ProviderError
from nestor.modules.cognition import ModelRequest
from nestor.modules.initiative import Alert, Frequency, Incoming
from nestor.testing.cognition import ScriptedModel


def alert(id: str, condition: str, kinds: tuple[str, ...] = ("mail",)) -> Alert:
    return Alert(id=id, title=condition, instruction="x", condition=condition, kinds=kinds, frequency=Frequency.ONCE)


PARCEL = alert("a-parcel", "the stroller parcel")
SCHOOL = alert("a-school", "the class trip")
HOME = alert("a-home", "the doorbell", kinds=("home.event",))
ALERTS = (PARCEL, SCHOOL, HOME)
CARRIER = Incoming(
    source="mail", kind="mail", title="Votre colis 8R04417 sera livré demain", body="Expéditeur : Petit Pas"
)


def yes_to(*matching: str) -> Callable[[ModelRequest], str]:
    """A reply that says yes for those of the asked alerts it is told."""

    def reply(request: ModelRequest) -> str:
        question = request.messages[0].content
        return json.dumps({"matches": [{"alert": a} for a in matching if f"[{a}]" in question]})

    return reply


def answering(*matching: str) -> ScriptedModel:
    return ScriptedModel(*[yes_to(*matching)] * 10)


async def test_one_call_judges_every_alert_of_the_items_kind_in_a_batch() -> None:
    model = answering("a-school")
    decisions = await decide(Algorithm.BATCH, model, ALERTS, CARRIER, language="French")
    assert len(model.requests) == 1
    assert decisions == [Decision(alert="a-parcel"), Decision(alert="a-school", matches=True)]


async def test_per_alert_each_call_lists_a_single_alert() -> None:
    model = answering("a-parcel")
    decisions = await decide(Algorithm.PER_ALERT, model, ALERTS, CARRIER, language="French")
    assert len(model.requests) == 2, "the doorbell alert does not wait for mail"
    asked = [r.messages[0].content for r in model.requests]
    assert ["[a-parcel]" in q and "[a-school]" not in q for q in asked] == [True, False]
    assert decisions == [Decision(alert="a-parcel", matches=True), Decision(alert="a-school")]


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_no_alert_of_the_kind_asks_nothing(algorithm: Algorithm) -> None:
    model = answering()
    assert await decide(algorithm, model, (HOME,), CARRIER, language="French") == []
    assert model.requests == []


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_an_unreachable_model_leaves_the_item_unsorted_and_unmatched(algorithm: Algorithm) -> None:
    model = ScriptedModel(fail=ProviderError("triage", "down", transient=True))
    decisions = await decide(algorithm, model, ALERTS, CARRIER, language="French")
    assert decisions and all(d.unsorted and not d.matches for d in decisions)
