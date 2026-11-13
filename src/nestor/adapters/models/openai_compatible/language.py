"""Language model over any OpenAI-compatible Chat Completions endpoint (OpenRouter, vLLM, Ollama…).

Speaks the wire protocol directly with httpx and Server-Sent Events: no vendor SDK. Every streamed
payload is a single-line `data:` JSON chunk, as all OpenAI-compatible servers send them, and the
stream ends with `data: [DONE]`.

A message's stable layers (`Message.layers`) are sent as text parts marked with `cache_control`, the
breakpoints OpenRouter passes to the providers that cache on request (Anthropic, Gemini) and Anthropic
reads itself; other servers get one plain text, and those that cache by themselves (OpenAI) reuse the
same stable prefix. `cache_control` in the settings says otherwise.

Tested against OpenRouter only; other servers are expected to work but remain untested. Local servers
(Ollama, LM Studio, vLLM, llama.cpp) usually need no key: without one, no `Authorization` header is sent.
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing

import httpx

from nestor.adapters.common.http import identity, provider_error, streamed_lines
from nestor.adapters.models.common import brand
from nestor.adapters.models.openai_compatible.stream import ChunkDecoder
from nestor.adapters.models.openai_compatible.wire import wire_message, wire_tool
from nestor.core import ContractError, ProviderError
from nestor.modules.cognition import (
    LanguageModel,
    ModelOutput,
    ModelRequest,
)

_CACHE_CONTROL = frozenset({"openrouter", "anthropic"})  # the brands that read `cache_control` breakpoints


class OpenAICompatibleLanguage(LanguageModel):
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
        api_key: str | None,
        model: str,
        extra_body: Mapping[str, object] | None = None,
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 30.0,
        provider: str = "openai-compatible",
        cache_control: bool | None = None,
        vision: bool = False,
    ) -> None:
        self._base_url = base_url
        self.vision = vision
        self._api_key = api_key or None
        self._model = model
        self._extra_body = dict(extra_body or {})
        self._timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
        self._provider = provider
        self._client: httpx.AsyncClient | None = None
        self.brand = brand(base_url)
        self._cache_control = self.brand in _CACHE_CONTROL if cache_control is None else cache_control

    def details(self) -> Mapping[str, str]:
        return {"model": self._model}

    async def start(self) -> None:
        headers = {**identity(self._base_url), "Accept": "text/event-stream"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=self._timeout)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        if self._client is None:
            raise ContractError(f"{self._provider}: stream() called before start()")
        lines = streamed_lines(self._client, "chat/completions", self._body(request), self._error)
        async with aclosing(lines), aclosing(ChunkDecoder(self._error).outputs(lines)) as outputs:
            async for output in outputs:
                yield output

    def _body(self, request: ModelRequest) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [wire_message(m, self._provider, cache_control=self._cache_control) for m in request.messages],
            "stream": True,
        }
        if request.tools:  # some servers reject an empty tool list
            body["tools"] = [wire_tool(t) for t in request.tools]
        return body | self._extra_body

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(self._provider, self._api_key, message, transient=transient)
