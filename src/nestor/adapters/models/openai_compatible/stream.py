"""The OpenAI API's streamed Chat Completions decoded: Server-Sent Events of single-line JSON chunks, ending with
`data: [DONE]`."""

import json
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import Any

from nestor.adapters.common.http import MAX_DETAIL, Failure, message_of, retryable
from nestor.adapters.models.common import PartialCall
from nestor.adapters.models.openai_compatible.wire import spent
from nestor.core import report
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    ModelOutput,
    TextDelta,
    ToolCall,
    ToolCallRequested,
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
        self._usage: dict[str, Any] | None = None
        self._model: str | None = None

    async def outputs(self, lines: AsyncIterator[str]) -> AsyncGenerator[ModelOutput]:
        try:
            async for output in self._outputs(lines):
                yield output
        finally:  # what was billed, even for a reply cut or failed midway
            if self._usage is not None or self._model is not None:
                report(spent(self._usage, self._model, requests=1))

    async def _outputs(self, lines: AsyncIterator[str]) -> AsyncGenerator[ModelOutput]:
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
        # some providers close a reply that asks for tools with "stop" (Claude on Vertex through OpenRouter)
        reason = FinishReason.TOOL_CALLS if self._calls else _FINISH_REASONS.get(self._finish or "stop")
        yield Finished(reason or FinishReason.STOP)

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
            self._usage = usage
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
