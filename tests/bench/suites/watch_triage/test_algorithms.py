"""The four triage algorithms on one item: where each stops, what the model is asked, how failures count."""

import json

import pytest

from nestor.bench.suites.watch_triage import Algorithm, Decision, decide
from nestor.core import ProviderError
from nestor.modules.cognition import ModelRequest
from nestor.modules.initiative.watches import Incoming, Watch
from nestor.testing.cognition import ScriptedModel

PARCEL = Watch(id="w-parcel", what="the stroller parcel", keywords=("poussette", "PP-48213"))
SCHOOL = Watch(id="w-school", what="the class trip", keywords=("sortie",))
HOME = Watch(id="w-home", what="the doorbell", kinds=("home.event",))
WATCHES = (PARCEL, SCHOOL, HOME)
CARRIER = Incoming(
    source="mail", kind="mail", title="Votre colis 8R04417 sera livré demain", body="Expéditeur : Petit Pas"
)
SHOP = Incoming(source="mail", kind="mail", title="Commande PP-48213 expédiée", body="Votre poussette est en route.")


def answering(*matching: str, urgent: bool = False) -> ScriptedModel:
    """A model that says yes for the watches whose words are in its question, in the asked format."""

    def reply(request: ModelRequest) -> str:
        question = request.messages[0].content
        if "[w-" in question:
            found = [{"watch": w, "urgent": urgent} for w in matching if f"[{w}]" in question]
            return json.dumps({"matches": found})
        hit = any(w.what in question for w in WATCHES if w.id in matching)
        return json.dumps({"matches": hit, "urgent": urgent and hit, "summary": "ok"})

    return ScriptedModel(*[reply] * 10)


async def test_the_keyword_gate_drops_an_item_without_asking_the_model() -> None:
    model = answering("w-parcel")
    decisions = await decide(Algorithm.GATE, model, WATCHES, CARRIER, language="French")
    assert model.requests == []
    assert decisions == [
        Decision(watch="w-parcel", gate=False, asked=False),
        Decision(watch="w-school", gate=False, asked=False),
    ]


async def test_through_the_gate_the_model_decides_once_per_watch_it_passed() -> None:
    model = answering("w-parcel", urgent=True)
    decisions = await decide(Algorithm.GATE, model, WATCHES, SHOP, language="French")
    assert len(model.requests) == 1
    assert decisions[0] == Decision(watch="w-parcel", gate=True, asked=True, matches=True, urgent=True)


async def test_without_the_gate_the_model_sees_every_watch_of_the_items_kind() -> None:
    model = answering("w-parcel")
    decisions = await decide(Algorithm.NO_GATE, model, WATCHES, CARRIER, language="French")
    assert len(model.requests) == 2, "the doorbell watch does not watch mail"
    assert [(d.watch, d.matches, d.gate) for d in decisions] == [("w-parcel", True, None), ("w-school", False, None)]


async def test_hints_reach_the_model_with_the_question_of_production() -> None:
    model = answering()
    await decide(Algorithm.HINTS, model, WATCHES, CARRIER, language="French")
    question = model.requests[0].messages[0].content
    assert 'told about: "the stroller parcel"' in question
    assert question.endswith("(hints, not requirements): poussette, PP-48213.")


async def test_one_call_judges_every_watch_at_once_in_a_batch() -> None:
    model = answering("w-school", urgent=True)
    decisions = await decide(Algorithm.BATCH, model, WATCHES, CARRIER, language="French")
    assert len(model.requests) == 1
    assert [(d.watch, d.matches, d.urgent) for d in decisions] == [("w-parcel", False, False), ("w-school", True, True)]


async def test_a_batch_over_no_watch_of_the_kind_asks_nothing() -> None:
    model = answering()
    assert await decide(Algorithm.BATCH, model, (HOME,), CARRIER, language="French") == []
    assert model.requests == []


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_an_unreachable_model_counts_as_a_match_as_in_production(algorithm: Algorithm) -> None:
    model = ScriptedModel(fail=ProviderError("triage", "down", transient=True))
    decisions = await decide(algorithm, model, WATCHES, SHOP, language="French")
    parcel = next(d for d in decisions if d.watch == "w-parcel")
    assert (parcel.matches, parcel.unsorted) == (True, True)


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_an_unreadable_answer_counts_as_a_match_as_in_production(algorithm: Algorithm) -> None:
    model = ScriptedModel(*["{I think so, yes.}"] * 4)
    decisions = await decide(algorithm, model, WATCHES, SHOP, language="French")
    assert all(d.matches and d.unsorted for d in decisions if d.asked)
