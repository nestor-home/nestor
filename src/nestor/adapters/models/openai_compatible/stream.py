"""The OpenAI API's streamed Chat Completions decoded: Server-Sent Events of single-line JSON chunks, ending with
`data: [DONE]`."""

import json
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import Any

from nestor.adapters.common.http import MAX_DETAIL, Failure, message_of, retryable
from nestor.adapters.models.common import PartialCall
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    ModelOutput,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    Usage,
)

_FINISH_REASONS = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
}


class ChunkDecoder:
    """Turns the chunks of one streamed reply into model outputs."""

    def __init__(self, error: Failure) -> None:
        self._error = error
        self._calls: dict[int, PartialCall] = {}
        self._finish: str | None = None
        self._usage: Usage | None = None
        self._model: str | None = None

    async def outputs(self, lines: AsyncIterator[str]) -> AsyncGenerator[ModelOutput]:
        async for line in lines:
            if not line.startswith("data:"):
                continue  # blank separators, `: keep-alive` comments, other SSE fields
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            for text in self._read(self._parse(data)):
                yield TextDelta(text)
        else:
            if self._finish is None:
                raise self._error("stream ended before the reply was finished", transient=True)
        for call in self._completed_calls():
            yield ToolCallRequested(call)
        yield Finished(_FINISH_REASONS.get(self._finish or "stop", FinishReason.STOP), self._usage, self._model)

    def _parse(self, data: str) -> dict[str, Any]:
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            chunk = None
        if not isinstance(chunk, dict):
            raise self._error(f"malformed stream chunk: {data[:MAX_DETAIL]}", transient=True)
        return chunk

    def _read(self, chunk: dict[str, Any]) -> Iterator[str]:
        if (error := chunk.get("error")) is not None:
            code = error.get("code") if isinstance(error, dict) else None
            transient = not isinstance(code, int) or retryable(code)
            raise self._error(f"error in stream: {message_of(error)}", transient=transient)
        if isinstance(model := chunk.get("model"), str) and model:
            self._model = model
        if isinstance(usage := chunk.get("usage"), dict):
            self._usage = _usage(usage) or self._usage
        for choice in chunk.get("choices") or ():
            delta = choice.get("delta") or {}
            if text := delta.get("content"):
                yield text
            for position, fragment in enumerate(delta.get("tool_calls") or ()):
                self._add_fragment(fragment, position)
            if reason := choice.get("finish_reason"):
                self._finish = reason

    def _add_fragment(self, fragment: dict[str, Any], position: int) -> None:
        partial = self._calls.setdefault(fragment.get("index", position), PartialCall())
        function = fragment.get("function") or {}
        partial.id = partial.id or fragment.get("id") or ""
        partial.name = partial.name or function.get("name") or ""
        partial.arguments.append(function.get("arguments") or "")

    def _completed_calls(self) -> Iterator[ToolCall]:
        for index in sorted(self._calls):
            yield self._calls[index].call(self._error)


def _usage(usage: dict[str, Any]) -> Usage | None:
    """The usage of a chunk (OpenRouter sends it on the last one, others with `stream_options.include_usage`),
    with OpenRouter's `cost`."""
    tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not all(isinstance(t, int) for t in tokens):
        return None
    cost = usage.get("cost")
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    return Usage(
        input_tokens=int(tokens[0] or 0),
        output_tokens=int(tokens[1] or 0),
        cost=float(cost) if isinstance(cost, int | float) else None,
        cached_input_tokens=cached if isinstance(cached, int) else None,
    )
