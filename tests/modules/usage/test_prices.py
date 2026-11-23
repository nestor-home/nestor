"""What a call costs: the provider's word first, then the configuration's price, then the public list; nothing for
the household's own models; never a made-up zero."""

from decimal import Decimal

import pytest

from nestor.core import ModelType, Money, Unit, Usage
from nestor.modules.usage import ZERO, Consumer, CostBasis, PriceBook, PriceCatalogue, Priced, Rates

HAIKU = Consumer(key="haiku", kind=ModelType.LANGUAGE, provider="anthropic", model="claude-haiku-4-5")
TOKENS = {Unit.INPUT_TOKENS: 10_000, Unit.CACHED_INPUT_TOKENS: 8_000, Unit.OUTPUT_TOKENS: 1_000}


class Listed(PriceCatalogue):
    """The public list: Haiku at $1 in, $5 out, $0.10 read from the cache, per million tokens."""

    def rates(self, provider: str, model: str) -> Rates | None:
        if (provider, model) != ("anthropic", "claude-haiku-4-5"):
            return None
        per_token = {Unit.INPUT_TOKENS: "1", Unit.OUTPUT_TOKENS: "5", Unit.CACHED_INPUT_TOKENS: "0.1"}
        return Rates({u: Decimal(p) / 1_000_000 for u, p in per_token.items()}, "catalogue:2026-11-23")


CONFIGURED = {"haiku": Rates.written({Unit.INPUT_TOKENS: 2, Unit.OUTPUT_TOKENS: 10}, "config")}

LIST = "catalogue:2026-11-23"
LISTED = Priced(
    Money.usd("0.0078"), CostBasis.PRICED, LIST
)  # 2000 fresh tokens at $1, 8000 cached at $0.10, 1000 out at $5
PI = Consumer(key="pi", kind=ModelType.LANGUAGE, provider="openai-compatible", local=True)
GROQ = Consumer(key="x", kind=ModelType.LANGUAGE, provider="groq", model="llama")
FREE = {"haiku": Rates.written({Unit.INPUT_TOKENS: 0}, "config")}
UNKNOWN = Priced(None, CostBasis.UNKNOWN)

CASES = [
    # what the provider billed is taken as it is, whatever is priced
    (
        "billed",
        HAIKU,
        Usage(TOKENS, cost=Money(4_200_000)),
        CONFIGURED,
        Priced(Money(4_200_000), CostBasis.REPORTED),
    ),
    # the configuration's price comes before the list; without its own cache price, the cache is billed as input
    ("configured", HAIKU, Usage(TOKENS), CONFIGURED, Priced(Money.usd("0.03"), CostBasis.PRICED, "config")),
    ("listed", HAIKU, Usage(TOKENS), {}, LISTED),
    # the model that answered is looked up first, then the one asked
    ("served", HAIKU, Usage(TOKENS, served="claude-unlisted"), {}, LISTED),
    # a model of the household's own costs nothing, and says so
    ("local", PI, Usage(TOKENS), {}, Priced(ZERO, CostBasis.FREE)),
    # neither said nor listed: unknown, not zero
    ("unlisted", GROQ, Usage(TOKENS), {}, UNKNOWN),
    # a price for none of what the call consumed does not price it
    ("other units", HAIKU, Usage({Unit.AUDIO_SECONDS: 30}), {}, UNKNOWN),
    # a price of zero is free, not unknown
    ("zero", HAIKU, Usage(TOKENS), FREE, Priced(Money(0), CostBasis.FREE, "config")),
]


@pytest.mark.parametrize(
    ("consumer", "usage", "configured", "priced"), [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
def test_a_call_is_valued_by_the_best_source_known(
    consumer: Consumer, usage: Usage, configured: dict[str, Rates], priced: Priced
) -> None:
    assert PriceBook(configured, Listed()).price(consumer, usage) == priced


def test_prices_are_written_as_providers_publish_them() -> None:
    written = {Unit.CHARACTERS: 30, Unit.AUDIO_SECONDS: 0.006, Unit.IMAGES: 0.04}  # per million, per minute, apiece
    rates = Rates.written(written, "config")
    spoken = {Unit.CHARACTERS: 1_000, Unit.AUDIO_SECONDS: 90, Unit.IMAGES: 2}
    assert rates.cost(spoken) == Money.usd("0.03") + Money.usd("0.009") + Money.usd("0.08")
