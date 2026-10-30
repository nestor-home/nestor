"""Conversation model over any OpenAI-compatible Chat Completions endpoint (OpenRouter, vLLM, Ollama…).

Speaks the wire protocol directly with httpx and Server-Sent Events: no vendor SDK. Every streamed
payload is a single-line `data:` JSON chunk, as all OpenAI-compatible servers send them, and the
stream ends with `data: [DONE]`.

Tested against OpenRouter only; other servers are expected to work but remain untested.
"""

import json
import urllib.parse
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator, Mapping
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import Field, PositiveFloat, SecretStr

from nestor.core import ContractError, ProviderError, new_id
from nestor.modules.cognition import (
    ConversationModel,
    Finished,
    FinishReason,
    Message,
    ModelOutput,
    ModelRequest,
    Role,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    ToolSpec,
)
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services

_FINISH_REASONS = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
}
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429})
_BRANDS = {"openrouter.ai": "openrouter", "openai.com": "openai", "mistral.ai": "mistral", "anthropic.com": "anthropic"}
_MAX_DETAIL = 300


def _retryable(status: int) -> bool:
    return status in _RETRYABLE_STATUSES or status >= 500


class OpenAICompatibleModel(ConversationModel):
    """Streams replies from `{base_url}/chat/completions`.

    `extra_body` is merged last into every request body: OpenRouter's `provider` pinning, `reasoning`
    effort, sampling settings… Errors are `ProviderError`s labelled with `provider`; HTTP 408/409/425/429,
    5xx, timeouts, transport failures and malformed output are transient, other HTTP errors are not.
    """

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        extra_body: Mapping[str, object] | None = None,
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 30.0,
        provider: str = "openai-compatible",
    ) -> None:
        if not api_key:
            raise ContractError(f"{provider}: empty api_key (local servers accept any placeholder)")
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._extra_body = dict(extra_body or {})
        self._timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
        self._provider = provider
        self._client: httpx.AsyncClient | None = None
        host = urllib.parse.urlsplit(base_url).hostname or ""
        self.brand = next((b for suffix, b in _BRANDS.items() if host == suffix or host.endswith(f".{suffix}")), None)

    def details(self) -> Mapping[str, str]:
        return {"model": self._model}

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}", "Accept": "text/event-stream"},
            timeout=self._timeout,
        )

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        if self._client is None:
            raise ContractError(f"{self._provider}: stream() called before start()")
        try:
            async with self._client.stream("POST", "chat/completions", json=self._body(request)) as response:
                if response.is_error:
                    detail = _detail(await response.aread())
                    raise self._error(
                        f"HTTP {response.status_code}: {detail}", transient=_retryable(response.status_code)
                    )
                async with aclosing(_ChunkDecoder(self._error).outputs(response.aiter_lines())) as outputs:
                    async for output in outputs:
                        yield output
        except httpx.TimeoutException as error:
            raise self._error(f"timed out ({type(error).__name__})", transient=True) from error
        except httpx.HTTPError as error:
            raise self._error(f"transport failure ({type(error).__name__}: {error})", transient=True) from error

    def _body(self, request: ModelRequest) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [_wire_message(m, self._provider) for m in request.messages],
            "stream": True,
        }
        if request.tools:  # some servers reject an empty tool list
            body["tools"] = [_wire_tool(t) for t in request.tools]
        return body | self._extra_body

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return ProviderError(self._provider, message.replace(self._api_key, "[redacted]"), transient=transient)


@dataclass(slots=True)
class _PartialCall:
    """A tool call whose fields arrive in fragments across stream chunks."""

    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


class _ChunkDecoder:
    """Turns the chunks of one streamed reply into model outputs."""

    def __init__(self, error: Callable[..., ProviderError]) -> None:
        self._error = error
        self._calls: dict[int, _PartialCall] = {}
        self._finish: str | None = None

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
        yield Finished(_FINISH_REASONS.get(self._finish or "stop", FinishReason.STOP))

    def _parse(self, data: str) -> dict[str, Any]:
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            chunk = None
        if not isinstance(chunk, dict):
            raise self._error(f"malformed stream chunk: {data[:_MAX_DETAIL]}", transient=True)
        return chunk

    def _read(self, chunk: dict[str, Any]) -> Iterator[str]:
        if (error := chunk.get("error")) is not None:
            code = error.get("code") if isinstance(error, dict) else None
            transient = not isinstance(code, int) or _retryable(code)
            raise self._error(f"error in stream: {_message_of(error)}", transient=transient)
        for choice in chunk.get("choices") or ():
            delta = choice.get("delta") or {}
            if text := delta.get("content"):
                yield text
            for position, fragment in enumerate(delta.get("tool_calls") or ()):
                self._add_fragment(fragment, position)
            if reason := choice.get("finish_reason"):
                self._finish = reason

    def _add_fragment(self, fragment: dict[str, Any], position: int) -> None:
        partial = self._calls.setdefault(fragment.get("index", position), _PartialCall())
        function = fragment.get("function") or {}
        partial.id = partial.id or fragment.get("id") or ""
        partial.name = partial.name or function.get("name") or ""
        partial.arguments.append(function.get("arguments") or "")

    def _completed_calls(self) -> Iterator[ToolCall]:
        for index in sorted(self._calls):
            partial = self._calls[index]
            if not partial.name:
                raise self._error(f"tool call #{index} has no name", transient=True)
            raw = "".join(partial.arguments) or "{}"
            try:
                arguments = json.loads(raw)
            except json.JSONDecodeError:
                arguments = None
            if not isinstance(arguments, dict):
                message = f"tool call {partial.name!r} has invalid JSON arguments: {raw[:_MAX_DETAIL]}"
                raise self._error(message, transient=True)
            yield ToolCall(partial.id or new_id(), partial.name, arguments)


def _wire_message(message: Message, provider: str) -> dict[str, object]:
    match message.role:
        case Role.ASSISTANT if message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": [_wire_call(c) for c in message.tool_calls],
            }
        case Role.TOOL:
            if message.tool_call_id is None:
                raise ContractError(f"{provider}: a tool message must say which call it answers (tool_call_id)")
            return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
        case _:
            return {"role": message.role.value, "content": message.content}


def _wire_call(call: ToolCall) -> dict[str, object]:
    arguments = json.dumps(dict(call.arguments), ensure_ascii=False)
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": arguments}}


def _wire_tool(tool: ToolSpec) -> dict[str, object]:
    function = {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)}
    return {"type": "function", "function": function}


def _detail(body: bytes) -> str:
    text = body.decode(errors="replace")
    try:
        error = json.loads(text)["error"]
    except (ValueError, KeyError, TypeError):
        return text[:_MAX_DETAIL]
    return _message_of(error)


def _message_of(error: object) -> str:
    message = error.get("message", error) if isinstance(error, dict) else error
    return str(message)[:_MAX_DETAIL]


class OpenAICompatibleSettings(AdapterSettings):
    """Configuration of an OpenAI-compatible model; `api_key` should come from the environment."""

    base_url: str
    api_key: SecretStr = Field(min_length=1)
    model: str
    extra_body: dict[str, Any] = Field(default_factory=dict)
    connect_timeout_s: PositiveFloat = 5.0
    read_timeout_s: PositiveFloat = 30.0


def build(settings: OpenAICompatibleSettings, name: str, services: Services) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value(),
        model=settings.model,
        extra_body=settings.extra_body,
        connect_timeout_s=settings.connect_timeout_s,
        read_timeout_s=settings.read_timeout_s,
        provider=name,
    )


plugin = Plugin(Family.MODEL, "openai-compatible", OpenAICompatibleSettings, build)
