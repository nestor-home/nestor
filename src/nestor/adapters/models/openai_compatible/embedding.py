"""EmbeddingModel over any OpenAI-compatible `/embeddings` endpoint (OpenRouter, OpenAI, Mistral, Ollama, vLLM…).

Speaks the wire protocol with httpx, no vendor SDK. The profile says everything about the model: its name, the
dimension of its vectors, the prefixes it expects before a question or a document (`query_prefix: "query: "`
for e5, an instruction for Qwen3-Embedding), whether to ask for a shorter vector (`dimensions` sent for
Matryoshka models). Nothing about a model is known here.

Tested against OpenRouter only. With a hosted provider, the texts embedded (the household's memories) leave
the house: a local server keeps them in.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.common.http import MAX_DETAIL, detail, provider_error, retryable
from nestor.adapters.models.common import EndpointSettings, brand
from nestor.core import ContractError, ProviderError
from nestor.modules.cognition.embedding import EmbeddingModel, EmbeddingSpace, Vector
from nestor.runtime.plugins import Family, Plugin, Services


class OpenAICompatibleEmbedding(EmbeddingModel):
    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        dimensions: int,
        send_dimensions: bool = False,
        query_prefix: str = "",
        document_prefix: str = "",
        batch_size: int = 64,
        extra_body: Mapping[str, object] | None = None,
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 30.0,
        provider: str = "openai-compatible-embedding",
    ) -> None:
        self._base_url, self._api_key = base_url, api_key or None
        self._send_dimensions, self._batch_size = send_dimensions, batch_size
        self._extra_body = dict(extra_body or {})
        self._timeout = httpx.Timeout(read_timeout_s, connect=connect_timeout_s)
        self._provider = provider
        self._space = EmbeddingSpace(
            model=model, dimensions=dimensions, query_prefix=query_prefix, document_prefix=document_prefix
        )
        self._client: httpx.AsyncClient | None = None
        self.brand = brand(base_url)

    @property
    def space(self) -> EmbeddingSpace:
        return self._space

    def details(self) -> Mapping[str, str]:
        return {"model": self._space.model, "dimensions": str(self._space.dimensions)}

    async def start(self) -> None:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=self._timeout)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        prefix = self._space.document_prefix
        vectors: list[Vector] = []
        for start in range(0, len(texts), self._batch_size):
            vectors += await self._embed([prefix + t for t in texts[start : start + self._batch_size]])
        return vectors

    async def embed_query(self, text: str) -> Vector:
        (vector,) = await self._embed([self._space.query_prefix + text])
        return vector

    async def _embed(self, inputs: list[str]) -> list[Vector]:
        if self._client is None:
            raise ContractError(f"{self._provider}: used before start()")
        if not inputs:
            return []
        body: dict[str, object] = {"model": self._space.model, "input": inputs, "encoding_format": "float"}
        if self._send_dimensions:
            body["dimensions"] = self._space.dimensions
        try:
            response = await self._client.post("embeddings", json=body | self._extra_body)
        except httpx.TimeoutException as error:
            raise self._error(f"timed out ({type(error).__name__})", transient=True) from error
        except httpx.HTTPError as error:
            raise self._error(f"transport failure ({type(error).__name__}: {error})", transient=True) from error
        if response.is_error:
            status = response.status_code
            raise self._error(f"HTTP {status}: {detail(response.content)}", transient=retryable(status))
        return self._vectors(response, len(inputs))

    def _vectors(self, response: httpx.Response, count: int) -> list[Vector]:
        try:
            data: list[dict[str, Any]] = sorted(response.json()["data"], key=lambda d: d.get("index", 0))
            vectors = [[float(x) for x in d["embedding"]] for d in data]
        except (ValueError, KeyError, TypeError):
            raise self._error(f"malformed answer: {response.text[:MAX_DETAIL]}", transient=True) from None
        if len(vectors) != count:
            raise self._error(f"{len(vectors)} vectors for {count} texts", transient=True)
        if any(len(v) != self._space.dimensions for v in vectors):
            served = len(vectors[0])
            raise self._error(
                f"the model serves vectors of {served} dimensions, the profile says {self._space.dimensions}: "
                f"set `dimensions: {served}`, or `send_dimensions: true` if it can shorten them",
                transient=False,
            )
        return vectors

    def _error(self, message: str, *, transient: bool) -> ProviderError:
        return provider_error(self._provider, self._api_key, message, transient=transient)


class OpenAICompatibleEmbeddingSettings(EndpointSettings):
    """An embedding model's profile."""

    model: str
    dimensions: PositiveInt  # of the vectors it returns, or asks for with `send_dimensions`
    send_dimensions: bool = False  # ask the model for `dimensions` (Matryoshka models shorten their vectors)
    query_prefix: str = ""  # put before a question, when the model expects it ("query: ")
    document_prefix: str = ""  # put before a document ("passage: ")
    batch_size: PositiveInt = Field(default=64, json_schema_extra={"advanced": True})
    extra_body: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})
    connect_timeout_s: PositiveFloat = Field(default=5.0, json_schema_extra={"advanced": True})
    read_timeout_s: PositiveFloat = Field(default=30.0, json_schema_extra={"advanced": True})


def build(settings: OpenAICompatibleEmbeddingSettings, name: str, services: Services) -> OpenAICompatibleEmbedding:
    return OpenAICompatibleEmbedding(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        dimensions=settings.dimensions,
        send_dimensions=settings.send_dimensions,
        query_prefix=settings.query_prefix,
        document_prefix=settings.document_prefix,
        batch_size=settings.batch_size,
        extra_body=settings.extra_body,
        connect_timeout_s=settings.connect_timeout_s,
        read_timeout_s=settings.read_timeout_s,
        provider=name,
    )


plugin = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleEmbeddingSettings,
    build,
    serves=EmbeddingModel,
)
