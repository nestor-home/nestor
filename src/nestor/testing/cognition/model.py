"""Test double and contract suite for the conversation model port."""

import asyncio
from collections.abc import AsyncGenerator, Callable

from nestor.core import ProviderError
from nestor.modules.cognition import (
    ConversationModel,
    Finished,
    FinishReason,
    Message,
    ModelOutput,
    ModelRequest,
    TextDelta,
    ToolCall,
    ToolCallRequested,
)

type Reply = str | ToolCall | Callable[[ModelRequest], str | ToolCall]


class ScriptedModel(ConversationModel):
    """Answers each request with the next scripted reply: text (streamed word by word), a tool call,
    or a policy that picks one of those from the request (what a real model would decide)."""

    name = "scripted-model"

    def __init__(self, *replies: Reply, word_delay_s: float = 0.0, fail: ProviderError | None = None):
        self._replies = list(replies)
        self._word_delay_s = word_delay_s
        self._fail = fail
        self.requests: list[ModelRequest] = []
        self.interrupted = 0

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        self.requests.append(request)
        if self._fail:
            raise self._fail
        reply = self._replies.pop(0) if self._replies else ""
        if not isinstance(reply, str | ToolCall):
            reply = reply(request)
        try:
            if isinstance(reply, ToolCall):
                yield ToolCallRequested(reply)
                yield Finished(FinishReason.TOOL_CALLS)
                return
            for i, word in enumerate(reply.split()):
                await asyncio.sleep(self._word_delay_s)
                yield TextDelta(word if i == 0 else f" {word}")
            yield Finished(FinishReason.STOP)
        except GeneratorExit:
            self.interrupted += 1
            raise


class ConversationModelContract:
    """Behaviour every `ConversationModel` adapter must show. Mix into a `Test…` class and implement
    `model()`, `tool_request()` and `unavailable_model()`."""

    def model(self) -> ConversationModel:
        raise NotImplementedError

    def tool_request(self) -> ModelRequest:
        """A request this model answers with a call to one of the offered tools."""
        raise NotImplementedError

    def unavailable_model(self) -> ConversationModel:
        """The same adapter when its provider fails (bad key, unreachable endpoint…)."""
        raise NotImplementedError

    def text_request(self) -> ModelRequest:
        return ModelRequest(messages=(Message.user("Bonjour, ça va ?"),))

    async def test_stream_ends_with_exactly_one_finished(self) -> None:
        async with self.model() as model:
            outputs = [o async for o in model.stream(self.text_request())]
        assert outputs, "empty stream"
        assert isinstance(outputs[-1], Finished), f"stream did not end with Finished: {outputs[-1]!r}"
        assert sum(isinstance(o, Finished) for o in outputs) == 1, "more than one Finished"
        assert "".join(o.text for o in outputs if isinstance(o, TextDelta)).strip(), "no text in the reply"

    async def test_closing_the_stream_early_is_clean(self) -> None:
        async with self.model() as model:
            stream = model.stream(self.text_request())
            await anext(stream)
            await stream.aclose()

    async def test_tool_call_comes_before_finished(self) -> None:
        request = self.tool_request()
        async with self.model() as model:
            outputs = [o async for o in model.stream(request)]
        calls = [o for o in outputs if isinstance(o, ToolCallRequested)]
        tool_names = {t.name for t in request.tools}
        assert calls, "no tool call"
        assert all(c.call.name in tool_names for c in calls), "call to a tool that was not offered"
        assert isinstance(outputs[-1], Finished)

    async def test_provider_failure_is_a_provider_error(self) -> None:
        async with self.unavailable_model() as model:
            try:
                [o async for o in model.stream(self.text_request())]
            except ProviderError:
                return
        raise AssertionError("no ProviderError raised by an unavailable provider")
