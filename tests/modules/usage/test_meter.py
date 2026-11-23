"""Every call to a model is recorded once, however it ends, on behalf of the work that made it."""

from collections.abc import AsyncGenerator
from contextlib import aclosing

import pytest

from nestor.core import ModelType, Money, ProviderError, Unit, Usage, report
from nestor.modules.channels import Medium
from nestor.modules.cognition.images import ImageModel
from nestor.modules.cognition.model import (
    Finished,
    FinishReason,
    LanguageModel,
    Message,
    ModelOutput,
    ModelRequest,
    TextDelta,
    text_answer,
)
from nestor.modules.journal import Journal
from nestor.modules.usage import (
    CallPurpose,
    Consumer,
    CostBasis,
    Meter,
    Outcome,
    PriceBook,
    Rates,
    UsageRecorded,
    attributed,
    metered,
)
from nestor.testing.cognition import ScriptedModel
from nestor.testing.cognition.images import ScriptedImages
from nestor.testing.journal import MemoryEventLog

REQUEST = ModelRequest(messages=(Message.user("Quel temps fait-il demain ?"),))
PRICES = {"drawer": Rates.written({Unit.IMAGES: 0.04}, "config")}


def consumer(key: str, provider: str, asked: str | None, kind: ModelType = ModelType.LANGUAGE) -> Consumer:
    return Consumer(key=key, kind=kind, provider=provider, model=asked)


async def recorded(journal: Journal) -> list[UsageRecorded]:
    return await journal.history(UsageRecorded)


async def test_a_call_is_recorded_on_behalf_of_whoever_made_it_priced_and_timed() -> None:
    journal = Journal(MemoryEventLog())
    async with Meter(journal, PriceBook(PRICES)) as meter:
        drawer = metered(
            ScriptedImages(), consumer("drawer", "openai-compatible", "gpt-image-1", ModelType.IMAGE), meter
        )
        assert isinstance(drawer, ImageModel)
        with attributed(purpose=CallPurpose.TURN, person="lea", channel="telegram", medium=Medium.WRITTEN, turn="t1"):
            await drawer.generate("Un galet noir")
    (call,) = await recorded(journal)
    assert (call.consumer, call.kind, call.served, call.units) == (
        "drawer",
        "image",
        "gpt-image-1",
        {Unit.IMAGES: 1, Unit.REQUESTS: 1},
    )
    assert (call.cost_nusd, call.basis, call.price, call.outcome) == (
        Money.usd("0.04").nusd,
        CostBasis.PRICED,
        "config",
        Outcome.OK,
    )
    assert (call.purpose, call.person, call.channel, call.medium, call.turn) == (
        CallPurpose.TURN,
        "lea",
        "telegram",
        Medium.WRITTEN,
        "t1",
    )


async def test_an_answer_cut_short_is_recorded_as_cut_with_what_it_had_consumed() -> None:
    journal = Journal(MemoryEventLog())
    async with Meter(journal, PriceBook({})) as meter:
        model = metered(ScriptedModel("Il fera beau toute la journée."), consumer("haiku", "anthropic", None), meter)
        assert isinstance(model, LanguageModel)
        with attributed(purpose=CallPurpose.TURN, person="mathis"):
            stream = model.stream(REQUEST)
        await anext(stream)  # read outside the work that asked: the call keeps whom it was for
        await stream.aclose()  # barge-in
    (call,) = await recorded(journal)
    assert (call.outcome, call.purpose, call.person) == (Outcome.CANCELLED, CallPurpose.TURN, "mathis")
    assert call.units[Unit.INPUT_TOKENS] > 0


class Billing(LanguageModel):
    """A provider that says what it billed when its answer ends, cut or not, as the real adapters do."""

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        try:
            yield TextDelta("Il fera")
            yield TextDelta(" beau.")
            yield Finished(FinishReason.STOP)
        finally:
            report(Usage({Unit.OUTPUT_TOKENS: 7}))


async def test_an_answer_cut_by_its_reader_keeps_what_its_provider_billed_while_closing() -> None:
    journal = Journal(MemoryEventLog())
    async with Meter(journal, PriceBook({})) as meter:
        model = metered(Billing(), consumer("haiku", "anthropic", None), meter)
        assert isinstance(model, LanguageModel)
        async with aclosing(model.stream(REQUEST)) as stream:
            await anext(stream)
    (call,) = await recorded(journal)
    assert (call.outcome, call.units[Unit.OUTPUT_TOKENS]) == (Outcome.CANCELLED, 7)


async def test_a_failed_call_is_recorded_as_failed_and_the_failure_still_reaches_the_caller() -> None:
    journal = Journal(MemoryEventLog())
    down = ProviderError("anthropic", "overloaded", transient=True)
    async with Meter(journal, PriceBook({})) as meter:
        model = metered(ScriptedModel(fail=down), consumer("haiku", "anthropic", None), meter)
        assert isinstance(model, LanguageModel)
        with pytest.raises(ProviderError):
            await text_answer(model, REQUEST)
    (call,) = await recorded(journal)
    assert (call.outcome, call.basis, call.cost_nusd, call.units) == (Outcome.FAILED, CostBasis.FREE, 0, {}), (
        "nothing was billed: not a cost unknown"
    )


async def test_a_call_nobody_said_the_reason_of_is_recorded_as_unattributed_not_dropped() -> None:
    journal = Journal(MemoryEventLog())
    async with Meter(journal, PriceBook({})) as meter:
        model = metered(ScriptedModel("Oui."), consumer("haiku", "anthropic", None), meter)
        assert isinstance(model, LanguageModel)
        await text_answer(model, REQUEST)
    (call,) = await recorded(journal)
    assert (call.purpose, call.person) == (CallPurpose.UNATTRIBUTED, None)
