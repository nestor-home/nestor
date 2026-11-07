"""The conversation model contract, its scripted double, and models the contract must reject."""

from collections.abc import AsyncGenerator

import pytest

from nestor.core import ProviderError
from nestor.modules.cognition import (
    LanguageModel,
    Message,
    ModelOutput,
    ModelRequest,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from nestor.testing.cognition import LanguageModelContract, ScriptedModel

LIGHT = ToolSpec("set_light", "Allume ou éteint une lampe.")


def answer(request: ModelRequest) -> str | ToolCall:
    """What a sensible model does: use the light tool when it is offered."""
    if request.tools:
        return ToolCall("c1", "set_light", {"room": "salon", "on": True})
    return "Ça va très bien, merci."


class TestScriptedModel(LanguageModelContract):
    def model(self) -> LanguageModel:
        return ScriptedModel(answer)

    def tool_request(self) -> ModelRequest:
        return ModelRequest(messages=(Message.user("Allume le salon."),), tools=(LIGHT,))

    def unavailable_model(self) -> LanguageModel:
        return ScriptedModel(fail=ProviderError("scripted", "HTTP 503", transient=True))


class EndlessModel(LanguageModel):
    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        yield TextDelta("bonjour")


async def test_the_model_contract_rejects_a_missing_finished_and_a_silent_outage() -> None:
    class Suite(LanguageModelContract):
        def model(self) -> LanguageModel:
            return EndlessModel()

        def unavailable_model(self) -> LanguageModel:
            return EndlessModel()  # "works" although its provider is down

    with pytest.raises(AssertionError, match="did not end with Finished"):
        await Suite().test_stream_ends_with_exactly_one_finished()
    with pytest.raises(AssertionError, match="no ProviderError"):
        await Suite().test_provider_failure_is_a_provider_error()
