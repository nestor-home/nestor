"""LiteLLM's public price list: looked up by who bills a model, kept on disk for the next start, and kept as it was
while the list cannot be read."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import respx

from nestor.adapters.prices import LiteLLMCatalogue
from nestor.core import Unit

URL = "https://prices.test/model_prices.json"
NOW = datetime(2026, 11, 23, 14, tzinfo=UTC)
LIST = {
    "sample_spec": {"input_cost_per_token": 0.0, "litellm_provider": "one of the providers"},
    "claude-haiku-4-5": {
        "litellm_provider": "anthropic",
        "input_cost_per_token": 1e-06,
        "output_cost_per_token": 5e-06,
        "cache_read_input_token_cost": 1e-07,
        "input_cost_per_token_batches": 5e-07,
    },
    "gemini/gemini-2.5-flash": {"litellm_provider": "gemini", "input_cost_per_token": 3e-07},
    "gemini-2.5-flash": {"litellm_provider": "vertex_ai-language-models", "input_cost_per_token": 9e-07},
    "elevenlabs/scribe_v1": {"litellm_provider": "elevenlabs", "input_cost_per_second": 6.11e-05},
    "elevenlabs/eleven_v4": {"litellm_provider": "elevenlabs", "input_cost_per_character": 8e-05},
}


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def catalogue(tmp_path: Path) -> LiteLLMCatalogue:
    return LiteLLMCatalogue(tmp_path / "prices" / "litellm.json", url=URL, first_s=3600, clock=lambda: NOW)


async def test_a_model_is_priced_by_who_bills_it_and_only_them(tmp_path: Path, api: respx.MockRouter) -> None:
    api.get(URL).respond(200, json=LIST)
    async with catalogue(tmp_path) as prices:
        assert prices.rates("anthropic", "claude-haiku-4-5") is None, "nothing known before the list is read"
        await prices.refresh()
        haiku = prices.rates("anthropic", "claude-haiku-4-5")
        assert haiku is not None and haiku.source == "catalogue:2026-11-23"
        assert haiku.per_unit == {
            Unit.INPUT_TOKENS: Decimal("0.000001"),
            Unit.OUTPUT_TOKENS: Decimal("0.000005"),
            Unit.CACHED_INPUT_TOKENS: Decimal("1E-7"),
        }, "batch prices are not what a live call pays"
        flash = prices.rates("gemini", "gemini-2.5-flash")
        assert flash is not None and flash.per_unit == {Unit.INPUT_TOKENS: Decimal("3E-7")}, "Gemini's, not Vertex's"
        scribe, voice = prices.rates("elevenlabs", "scribe_v1"), prices.rates("elevenlabs", "eleven_v4")
        assert scribe is not None and scribe.per_unit == {Unit.AUDIO_SECONDS: Decimal("0.0000611")}
        assert voice is not None and voice.per_unit == {Unit.CHARACTERS: Decimal("0.00008")}
        assert prices.rates("openai-compatible", "claude-haiku-4-5") is None, "an unknown host may resell at any price"


async def test_the_last_list_is_known_at_once_after_a_restart_and_kept_when_the_list_cannot_be_read(
    tmp_path: Path, api: respx.MockRouter
) -> None:
    api.get(URL).respond(200, json=LIST)
    async with catalogue(tmp_path) as prices:
        await prices.refresh()
    api.get(URL).respond(200, content=b"<html>rate limited</html>")
    async with catalogue(tmp_path) as restarted:
        assert restarted.rates("anthropic", "claude-haiku-4-5") is not None, "read from its copy, offline"
        with pytest.raises(ValueError):
            await restarted.refresh()
        assert restarted.rates("anthropic", "claude-haiku-4-5") is not None
    copy = json.loads((tmp_path / "prices" / "litellm.json").read_text())
    assert copy == LIST, "a broken download never replaces the copy"
