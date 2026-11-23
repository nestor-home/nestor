"""What Gemini's API streams: its chunks, turned into model outputs."""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import Any

from nestor.adapters.common.http import Failure, message_of, retryable
from nestor.core import Unit, Usage, new_id, report
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    ModelOutput,
    TextDelta,
    ToolCall,
    ToolCallRequested,
)

_FINISHED = {"STOP": FinishReason.STOP, "MAX_TOKENS": FinishReason.LENGTH}
# a reply stopped otherwise: the model's own slip may pass on a retry, a refusal (SAFETY, RECITATION…) will not
_GLITCHES = frozenset({"MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "OTHER"})


class Decoder:
    """Turns the chunks of one streamed reply into model outputs. Gemini sends each tool call whole, in one part."""

    def __init__(self, error: Failure) -> None:
        self._error = error
        self._calls: list[ToolCall] = []
        self._finish: str | None = None
        self._usage: dict[Unit, float] = {}  # Gemini repeats the whole count: the last one holds
        self._model: str | None = None

    async def outputs(self, chunks: AsyncIterator[dict[str, Any]]) -> AsyncGenerator[ModelOutput]:
        try:
            async for output in self._outputs(chunks):
                yield output
        finally:  # what was billed, even for a reply cut or failed midway
            if self._usage or self._model is not None:
                report(Usage(self._usage | {Unit.REQUESTS: 1}, served=self._model))

    async def _outputs(self, chunks: AsyncIterator[dict[str, Any]]) -> AsyncGenerator[ModelOutput]:
        async for chunk in chunks:
            for text in self._read(chunk):
                yield TextDelta(text)
        if self._finish is None:
            raise self._error("stream ended before the reply was finished", transient=True)
        if self._finish not in _FINISHED:
            transient = self._finish in _GLITCHES
            raise self._error(f"the reply was stopped ({self._finish})", transient=transient)
        for call in self._calls:
            yield ToolCallRequested(call)
        reason = FinishReason.TOOL_CALLS if self._calls else _FINISHED[self._finish]
        yield Finished(reason)

    def _read(self, chunk: dict[str, Any]) -> Iterator[str]:
        if (error := chunk.get("error")) is not None:
            code = error.get("code") if isinstance(error, dict) else None
            transient = not isinstance(code, int) or retryable(code)
            raise self._error(f"error in stream: {message_of(error)}", transient=transient)
        if blocked := (chunk.get("promptFeedback") or {}).get("blockReason"):
            raise self._error(f"prompt blocked: {blocked}", transient=False)
        if isinstance(model := chunk.get("modelVersion"), str) and model:
            self._model = model
        if isinstance(usage := chunk.get("usageMetadata"), dict):
            self._usage = _units(usage) or self._usage
        for candidate in (chunk.get("candidates") or ())[:1]:
            for part in (candidate.get("content") or {}).get("parts") or ():
                if part.get("thought"):
                    continue  # its reasoning, when asked for a summary of it
                if text := part.get("text"):
                    yield text
                if isinstance(call := part.get("functionCall"), dict):
                    self._calls.append(self._call(call, part.get("thoughtSignature")))
            if reason := candidate.get("finishReason"):
                self._finish = reason

    def _call(self, call: dict[str, Any], signature: object) -> ToolCall:
        name, arguments = call.get("name"), call.get("args") or {}
        if not isinstance(name, str) or not name:
            raise self._error("a tool call has no name", transient=True)
        if not isinstance(arguments, dict):
            raise self._error(f"tool call {name!r} has arguments that are not an object", transient=True)
        replay = signature if isinstance(signature, str) else None
        return ToolCall(call.get("id") or new_id(), name, arguments, replay=replay)


def _units(usage: dict[str, Any]) -> dict[Unit, float]:
    """Gemini counts its thinking apart from the answer: both are output."""
    prompt = usage.get("promptTokenCount")
    if not isinstance(prompt, int):
        return {}
    output = sum(n for k in ("candidatesTokenCount", "thoughtsTokenCount") if isinstance(n := usage.get(k), int))
    units: dict[Unit, float] = {Unit.INPUT_TOKENS: prompt, Unit.OUTPUT_TOKENS: output}
    if isinstance(cached := usage.get("cachedContentTokenCount"), int):
        units[Unit.CACHED_INPUT_TOKENS] = cached
    return units
