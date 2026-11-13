"""How every OpenAI-compatible model names itself to the server it calls: a versioned `User-Agent` everywhere, and
the attribution headers only on the hosts that rank apps by them (OpenRouter, Vercel AI Gateway)."""

import base64
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest
import respx

from nestor import __version__
from nestor.adapters.models.openai_compatible.embedding import OpenAICompatibleEmbedding
from nestor.adapters.models.openai_compatible.image import OpenAICompatibleImage
from nestor.adapters.models.openai_compatible.language import OpenAICompatibleLanguage
from nestor.modules.cognition import Message, ModelRequest
from nestor.testing.cognition.images import PNG

KEY = "sk-test-0123456789"


def answer(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/embeddings"):
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}]})
    if path.endswith("/images/generations"):
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})
    done = {"choices": [{"index": 0, "delta": {"content": "Oui."}, "finish_reason": "stop"}]}
    return httpx.Response(200, content=f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode())


async def chat(base_url: str) -> None:
    async with OpenAICompatibleLanguage(base_url=base_url, api_key=KEY, model="m") as model:
        [_ async for _ in model.stream(ModelRequest(messages=(Message.user("Bonjour"),)))]


async def embed(base_url: str) -> None:
    async with OpenAICompatibleEmbedding(base_url=base_url, api_key=KEY, model="m", dimensions=3) as embedder:
        await embedder.embed_query("Bonjour")


async def draw(base_url: str) -> None:
    async with OpenAICompatibleImage(base_url=base_url, api_key=KEY, model="m") as images:
        await images.generate("un chat")


CLIENTS = pytest.mark.parametrize("call", [chat, embed, draw], ids=["language", "embedding", "image"])
Call = Callable[[str], Awaitable[None]]


async def headers_sent(call: Call, base_url: str) -> httpx.Headers:
    with respx.mock as router:
        route = router.route().mock(side_effect=answer)
        await call(base_url)
    return route.calls.last.request.headers


@CLIENTS
@pytest.mark.parametrize("base_url", ["https://openrouter.ai/api/v1", "https://eu.openrouter.ai/api/v1"])
async def test_openrouter_is_told_which_app_calls_and_what_it_is(call: Call, base_url: str) -> None:
    headers = await headers_sent(call, base_url)
    assert headers["user-agent"] == f"nestor/{__version__} (+https://nestorhome.dev)"
    assert headers["http-referer"] == "https://nestorhome.dev"
    assert headers["x-openrouter-title"] == "Nestor"
    assert headers["x-openrouter-categories"] == "personal-agent"
    assert headers["authorization"] == f"Bearer {KEY}"


@CLIENTS
async def test_vercel_ai_gateway_is_told_which_app_calls(call: Call) -> None:
    headers = await headers_sent(call, "https://ai-gateway.vercel.sh/v1")
    assert (headers["http-referer"], headers["x-title"]) == ("https://nestorhome.dev", "Nestor")
    assert headers["user-agent"].startswith(f"nestor/{__version__} ")


@CLIENTS
@pytest.mark.parametrize(
    "base_url", ["https://api.openai.com/v1", "http://localhost:8080/v1", "https://openrouter.ai.evil.test/v1"]
)
async def test_other_servers_only_learn_the_version_from_the_user_agent(call: Call, base_url: str) -> None:
    headers = await headers_sent(call, base_url)
    assert headers["user-agent"] == f"nestor/{__version__} (+https://nestorhome.dev)"
    assert not {"http-referer", "x-title", "x-openrouter-title", "x-openrouter-categories"} & set(headers.keys())
