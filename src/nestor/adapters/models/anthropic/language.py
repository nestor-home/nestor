"""Claude as a language model, streamed from Anthropic's Messages API."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing

import httpx

from nestor.adapters.common.http import provider_error, sse_payloads, streamed_lines
from nestor.adapters.models.anthropic.stream import Decoder
from nestor.adapters.models.anthropic.wire import EPHEMERAL, Effort, wire_messages, wire_system, wire_tool
from nestor.core import ContractError, ProviderError
from nestor.modules.cognition import (
    LanguageModel,
    ModelOutput,
    ModelRequest,
)

API_VERSION = "2023-06-01"  # the Messages API's version: features come by headers or fields, not by a newer one
MAX_TOKENS = 64_000  # thinking included: room for current models' adaptive thinking, within every one's output limit


class AnthropicLanguage(LanguageModel):
    """Streams replies from `{base_url}/messages`. Errors are `ProviderError`s labelled with its name: HTTP
    408/409/425/429 and 5xx (529: overloaded), timeouts, transport failures, malformed streams and errors the stream
    reports as overloaded or rate limited are transient, others are not; so is a refusal, which a fallback may
    answer.
    """

    brand = "anthropic"
    vision = True
    reads = frozenset({"application/pdf"})

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = MAX_TOKENS,
        effort: Effort | None = None,
        extra_body: Mapping[str, object] | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 60.0,
        name: str = "anthropic",
    ) -> None:
        self.name = name
        self._api_key, self._model, self._max_tokens, self._effort = api_key, model, max_tokens, effort
        self._extra_body = dict(extra_body or {})
        self._base_url = base_url
        self._timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
        self._client: httpx.AsyncClient | None = None

    def details(self) -> Mapping[str, str]:
        return {"model": self._model}

    async def start(self) -> None:
        headers = {"x-api-key": self._api_key, "anthropic-version": API_VERSION, "Accept": "text/event-stream"}
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=self._timeout)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        if self._client is None:
            raise ContractError(f"{self.name}: stream() called before start()")
        lines = streamed_lines(self._client, "messages", self._body(request), self._error)
        async with aclosing(lines), aclosing(Decoder(self._error).outputs(sse_payloads(lines, self._error))) as out:
            async for output in out:
                yield output

    def _body(self, request: ModelRequest) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": wire_messages(request.messages, self.name),
            "stream": True,
            "cache_control": EPHEMERAL,  # the conversation, up to its last message
        }
        if system := wire_system(request.messages):
            body["system"] = system
        if request.tools:
            body["tools"] = [wire_tool(t) for t in request.tools]
        if self._effort is not None:
            body["output_config"] = {"effort": self._effort.value}
        return body | self._extra_body

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(self.name, self._api_key, message, transient=transient)
