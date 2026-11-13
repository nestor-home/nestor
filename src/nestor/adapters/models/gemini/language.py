"""Gemini as a language model, streamed from Google's Gemini API."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing

import httpx

from nestor.adapters.common.http import provider_error, sse_payloads, streamed_lines
from nestor.adapters.models.gemini.stream import Decoder
from nestor.adapters.models.gemini.wire import wire_contents, wire_tool
from nestor.core import ContractError, ProviderError
from nestor.modules.cognition import (
    LanguageModel,
    ModelOutput,
    ModelRequest,
    Role,
)


class GeminiLanguage(LanguageModel):
    """Streams replies from `{base_url}/models/{model}:streamGenerateContent`. Errors are `ProviderError`s labelled
    with its name: HTTP 408/409/425/429 and 5xx, timeouts, transport failures and malformed streams are transient;
    other HTTP errors, and a prompt Gemini blocks, are not.
    """

    brand = "gemini"
    vision = True
    reads = frozenset({"application/pdf"})

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        extra_body: Mapping[str, object] | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 60.0,
        name: str = "gemini",
    ) -> None:
        self.name = name
        self._api_key, self._model = api_key, model
        self._extra_body = dict(extra_body or {})
        self._base_url = base_url
        self._timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
        self._client: httpx.AsyncClient | None = None

    def details(self) -> Mapping[str, str]:
        return {"model": self._model}

    async def start(self) -> None:
        headers = {"x-goog-api-key": self._api_key, "Accept": "text/event-stream"}
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=self._timeout)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelOutput]:
        if self._client is None:
            raise ContractError(f"{self.name}: stream() called before start()")
        path = f"models/{self._model}:streamGenerateContent"
        lines = streamed_lines(self._client, path, self._body(request), self._error, params={"alt": "sse"})
        async with aclosing(lines), aclosing(Decoder(self._error).outputs(sse_payloads(lines, self._error))) as out:
            async for output in out:
                yield output

    def _body(self, request: ModelRequest) -> dict[str, object]:
        body: dict[str, object] = {"contents": wire_contents(request.messages, self.name)}
        system = [part for m in request.messages if m.role is Role.SYSTEM for part in (*m.layers, m.content) if part]
        if system:
            body["systemInstruction"] = {"parts": [{"text": text} for text in system]}
        if request.tools:
            body["tools"] = [{"functionDeclarations": [wire_tool(t) for t in request.tools]}]
        return body | self._extra_body

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(self.name, self._api_key, message, transient=transient)
