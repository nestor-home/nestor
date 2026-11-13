"""OpenAI-compatible embeddings: the embedder contract over a mocked endpoint, prefixes, batches, dimensions and
errors, plus an opt-in run against OpenRouter."""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from nestor.adapters.models.openai_compatible import embedding
from nestor.adapters.models.openai_compatible.embedding import OpenAICompatibleEmbedding
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale
from nestor.runtime.plugins import Services
from nestor.testing.cognition import EmbeddingModelContract
from nestor.testing.i18n import EchoLocalizer

BASE_URL = "https://embed.test/v1"
KEY = "sk-embed-0123456789"


def embedder(**kwargs: Any) -> OpenAICompatibleEmbedding:
    settings: dict[str, Any] = {"base_url": BASE_URL, "api_key": KEY, "model": "vendor/embed", "dimensions": 3}
    return OpenAICompatibleEmbedding(**(settings | kwargs))


def answer(request: httpx.Request) -> httpx.Response:
    """Vectors in reverse order of `index`, as some servers send them: the adapter must sort them."""
    inputs = json.loads(request.content)["input"]
    data = [{"index": i, "embedding": [float(len(t)), 1.0, 0.0]} for i, t in enumerate(inputs)]
    return httpx.Response(200, json={"data": list(reversed(data))})


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


class TestOpenAICompatibleEmbedder(EmbeddingModelContract):
    @pytest.fixture(autouse=True)
    def _endpoint(self, api: respx.MockRouter) -> None:
        api.post(f"{BASE_URL}/embeddings").mock(side_effect=answer)
        api.post("https://down.test/v1/embeddings").respond(401, json={"error": {"message": "No auth"}})

    def embedder(self) -> OpenAICompatibleEmbedding:
        return embedder()

    def unavailable_embedder(self) -> OpenAICompatibleEmbedding:
        return embedder(base_url="https://down.test/v1")


async def test_questions_and_documents_get_their_prefixes_and_documents_go_in_batches(api: respx.MockRouter) -> None:
    route = api.post(f"{BASE_URL}/embeddings").mock(side_effect=answer)
    async with embedder(query_prefix="query: ", document_prefix="passage: ", batch_size=2) as e:
        vectors = await e.embed_documents(["a", "bb", "ccc"])
        await e.embed_query("dd")
    bodies = [json.loads(c.request.content) for c in route.calls]
    assert [b["input"] for b in bodies] == [["passage: a", "passage: bb"], ["passage: ccc"], ["query: dd"]]
    assert [v[0] for v in vectors] == [10.0, 11.0, 12.0], "in the order of the texts, whatever the answer's"
    assert all(b["model"] == "vendor/embed" and "dimensions" not in b for b in bodies)


async def test_shorter_vectors_are_asked_for_only_when_the_profile_says_so(api: respx.MockRouter) -> None:
    route = api.post(f"{BASE_URL}/embeddings").mock(side_effect=answer)
    async with embedder(send_dimensions=True) as e:
        await e.embed_query("x")
    assert json.loads(route.calls.last.request.content)["dimensions"] == 3


async def test_vectors_of_another_dimension_say_how_to_fix_the_profile(api: respx.MockRouter) -> None:
    api.post(f"{BASE_URL}/embeddings").mock(side_effect=answer)
    async with embedder(dimensions=768) as e:
        with pytest.raises(ProviderError, match="vectors of 3 dimensions, the profile says 768") as raised:
            await e.embed_query("x")
    assert not raised.value.transient


@pytest.mark.parametrize(
    ("answer", "transient"),
    [
        (httpx.Response(429, text=f"bad key {KEY}"), True),
        (httpx.Response(503, text=f"bad key {KEY}"), True),
        (httpx.Response(400, text=f"bad key {KEY}"), False),
        (httpx.ReadTimeout(f"no answer for {KEY}"), True),
        (httpx.ConnectError(f"refused for {KEY}"), True),
        (httpx.Response(200, text=f"<html>{KEY}</html>"), True),
        (httpx.Response(200, json={"data": [{"index": 0, "vector": [1.0, 0.0, 0.0]}]}), True),
        (httpx.Response(200, json={"data": []}), True),  # no vector for the text: never one shifted onto another
    ],
    ids=["429", "503", "400", "timeout", "unreachable", "not json", "no embedding", "too few vectors"],
)
async def test_a_failed_call_is_a_provider_error_that_says_whether_a_retry_may_succeed_and_never_shows_the_key(
    api: respx.MockRouter, answer: httpx.Response | Exception, transient: bool
) -> None:
    api.post(f"{BASE_URL}/embeddings").mock(side_effect=[answer])
    async with embedder() as e:
        with pytest.raises(ProviderError) as raised:
            await e.embed_query("x")
    assert raised.value.transient is transient and KEY not in str(raised.value)


async def test_an_embedder_used_before_it_starts_says_so() -> None:
    with pytest.raises(ContractError, match="before start"):
        await embedder().embed_query("x")


async def test_the_space_is_the_model_served_its_dimension_and_prefixes_not_the_profile_name() -> None:
    one, renamed = embedder(provider="gemma"), embedder(provider="other-name")
    assert one.space == renamed.space
    assert embedder(query_prefix="query: ").space.id != one.space.id
    assert embedder(dimensions=4).space.id != one.space.id


def test_the_plugin_builds_an_embedder_from_its_profile(tmp_path: Path) -> None:
    raw = {"base_url": BASE_URL, "model": "vendor/embed", "dimensions": 768, "query_prefix": "query: "}
    built = embedding.create(raw, "te3", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("en")))
    assert isinstance(built, OpenAICompatibleEmbedding)
    assert (built.space.dimensions, built.space.query_prefix) == (768, "query: ")


@pytest.mark.live
async def test_openrouter_embeds_for_real() -> None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY is not set")
    async with OpenAICompatibleEmbedding(
        base_url="https://openrouter.ai/api/v1", api_key=key, model="openai/text-embedding-3-small", dimensions=1536
    ) as e:
        (vector,) = await e.embed_documents(["Léa est végétarienne."])
    assert len(vector) == 1536
