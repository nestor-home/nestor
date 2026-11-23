"""What Anthropic's Messages API streams: its events, turned into model outputs."""

import json
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import Any

from nestor.adapters.common.http import Failure, message_of
from nestor.adapters.models.anthropic.wire import Block
from nestor.adapters.models.common import PartialCall
from nestor.core import Unit, Usage, new_id, report
from nestor.modules.cognition import (
    Finished,
    FinishReason,
    ModelOutput,
    TextDelta,
    ToolCallRequested,
)

REASONING = frozenset({"thinking", "redacted_thinking"})  # the blocks a tool call's reasoning is made of
_STOP_REASONS = {"tool_use": FinishReason.TOOL_CALLS, "max_tokens": FinishReason.LENGTH}
_INPUT_COUNTS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
_TRANSIENT = frozenset({"overloaded_error", "api_error", "rate_limit_error", "timeout_error"})  # error types


class Decoder:
    """Turns the events of one streamed message into model outputs. Content blocks come one after the other: the
    reasoning blocks before a tool call are that call's.
    """

    def __init__(self, error: Failure) -> None:
        self._error = error
        self._calls: dict[int, PartialCall] = {}
        self._reasoning: dict[int, Block] = {}  # the thinking blocks being streamed, by index
        self._unclaimed: list[Block] = []  # those no tool call has claimed yet
        self._claimed: dict[int, list[Block]] = {}  # by the index of the call they led to
        self._stop: str | None = None
        self._model: str | None = None
        self._input: dict[str, Any] = {}
        self._output_tokens: int | None = None

    async def outputs(self, events: AsyncIterator[dict[str, Any]]) -> AsyncGenerator[ModelOutput]:
        try:
            async for output in self._outputs(events):
                yield output
        finally:  # what was billed, even for a reply cut or failed midway
            if (units := self._units()) or self._model is not None:
                report(Usage(units, served=self._model))

    async def _outputs(self, events: AsyncIterator[dict[str, Any]]) -> AsyncGenerator[ModelOutput]:
        async for event in events:
            kind = event.get("type")
            if kind == "message_stop":
                break
            for text in self._read(kind, event):
                yield TextDelta(text)
        else:
            raise self._error("stream ended before the message was finished", transient=True)
        if self._stop == "refusal":
            raise self._error("Claude declined to answer (refusal)", transient=False)
        for index in sorted(self._calls):
            partial = self._calls[index]
            if reasoning := self._claimed.get(index):
                partial.replay = json.dumps(reasoning)
            yield ToolCallRequested(partial.call(self._error))
        yield Finished(_STOP_REASONS.get(self._stop or "", FinishReason.STOP))

    def _read(self, kind: object, event: dict[str, Any]) -> Iterator[str]:
        index = event.get("index", -1)
        match kind:
            case "message_start":
                message = event.get("message") or {}
                self._model = message.get("model") or None
                self._input = message.get("usage") or {}
                if isinstance(tokens := self._input.get("output_tokens"), int):
                    self._output_tokens = tokens
            case "content_block_start":
                block = dict(event.get("content_block") or {})
                if block.get("type") == "tool_use":
                    self._calls[index] = PartialCall(block.get("id") or new_id(), block.get("name") or "")
                    self._claimed[index], self._unclaimed = self._unclaimed, []
                elif block.get("type") in REASONING:
                    self._reasoning[index] = block
                    self._unclaimed.append(block)
                elif block.get("type") == "text" and block.get("text"):
                    yield block["text"]
            case "content_block_delta":
                delta = event.get("delta") or {}
                match delta.get("type"):
                    case "text_delta" if delta.get("text"):
                        yield delta["text"]
                    case "input_json_delta" if index in self._calls:
                        self._calls[index].arguments.append(delta.get("partial_json") or "")
                    case "thinking_delta" if index in self._reasoning:
                        block = self._reasoning[index]
                        block["thinking"] = block.get("thinking", "") + (delta.get("thinking") or "")
                    case "signature_delta" if index in self._reasoning:
                        block = self._reasoning[index]
                        block["signature"] = block.get("signature", "") + (delta.get("signature") or "")
            case "message_delta":
                self._stop = (event.get("delta") or {}).get("stop_reason") or self._stop
                if isinstance(tokens := (event.get("usage") or {}).get("output_tokens"), int):
                    self._output_tokens = tokens
            case "error":
                error = event.get("error") or {}
                transient = isinstance(error, dict) and error.get("type") in _TRANSIENT
                raise self._error(f"error in stream: {message_of(error)}", transient=transient)

    def _units(self) -> dict[Unit, float]:
        """Anthropic counts apart what it read from the cache and wrote to it: the input is all three."""
        fresh, read, written = (self._input.get(k) for k in _INPUT_COUNTS)
        if not isinstance(fresh, int):
            return {}
        read, written = (n if isinstance(n, int) else 0 for n in (read, written))
        units: dict[Unit, float] = {
            Unit.INPUT_TOKENS: fresh + read + written,
            Unit.CACHED_INPUT_TOKENS: read,
            Unit.CACHE_WRITE_TOKENS: written,
        }
        if self._output_tokens is not None:
            units[Unit.OUTPUT_TOKENS] = self._output_tokens
        return units
