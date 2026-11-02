"""The two triage algorithms on one item: how many calls, what each judges, and how failures count."""

import json
from collections.abc import Callable

import pytest

from nestor.bench.suites.watch_triage import Algorithm, Decision, decide
from nestor.core import ProviderError
from nestor.modules.cognition import ModelRequest
from nestor.modules.initiative.watches import Incoming, Watch
from nestor.testing.cognition import ScriptedModel

PARCEL = Watch(id="w-parcel", what="the stroller parcel")
SCHOOL = Watch(id="w-school", what="the class trip")
HOME = Watch(id="w-home", what="the doorbell", kinds=("home.event",))
WATCHES = (PARCEL, SCHOOL, HOME)
CARRIER = Incoming(
    source="mail", kind="mail", title="Votre colis 8R04417 sera livré demain", body="Expéditeur : Petit Pas"
)


def yes_to(*matching: str, urgent: bool = False) -> Callable[[ModelRequest], str]:
    """A reply that says yes for those of the asked watches it is told."""

    def reply(request: ModelRequest) -> str:
        question = request.messages[0].content
        return json.dumps({"matches": [{"watch": w, "urgent": urgent} for w in matching if f"[{w}]" in question]})

    return reply


def answering(*matching: str, urgent: bool = False) -> ScriptedModel:
    return ScriptedModel(*[yes_to(*matching, urgent=urgent)] * 10)


async def test_one_call_judges_every_watch_of_the_items_kind_in_a_batch() -> None:
    model = answering("w-school", urgent=True)
    decisions = await decide(Algorithm.BATCH, model, WATCHES, CARRIER, language="French")
    assert len(model.requests) == 1
    assert decisions == [Decision(watch="w-parcel"), Decision(watch="w-school", matches=True, urgent=True)]


async def test_per_watch_each_call_lists_a_single_watch() -> None:
    model = answering("w-parcel")
    decisions = await decide(Algorithm.PER_WATCH, model, WATCHES, CARRIER, language="French")
    assert len(model.requests) == 2, "the doorbell watch does not watch mail"
    asked = [r.messages[0].content for r in model.requests]
    assert ["[w-parcel]" in q and "[w-school]" not in q for q in asked] == [True, False]
    assert decisions == [Decision(watch="w-parcel", matches=True), Decision(watch="w-school")]


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_no_watch_of_the_kind_asks_nothing(algorithm: Algorithm) -> None:
    model = answering()
    assert await decide(algorithm, model, (HOME,), CARRIER, language="French") == []
    assert model.requests == []


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_an_unreachable_model_leaves_the_item_unsorted_and_unmatched(algorithm: Algorithm) -> None:
    model = ScriptedModel(fail=ProviderError("triage", "down", transient=True))
    decisions = await decide(algorithm, model, WATCHES, CARRIER, language="French")
    assert decisions and all(d.unsorted and not d.matches for d in decisions)


@pytest.mark.parametrize("algorithm", list(Algorithm))
async def test_an_unreadable_answer_is_asked_again_once(algorithm: Algorithm) -> None:
    model = ScriptedModel("{I think so, yes.}", *[yes_to("w-parcel")] * 4)
    decisions = await decide(algorithm, model, WATCHES, CARRIER, language="French")
    parcel = next(d for d in decisions if d.watch == "w-parcel")
    assert (parcel.matches, parcel.unsorted) == (True, False)
