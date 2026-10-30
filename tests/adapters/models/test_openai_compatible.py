"""OpenAI-compatible model: the conversation model contract over a mocked SSE endpoint, the wire
format, error mapping and interruption, plus an opt-in run against OpenRouter."""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator, Mapping
from pathlib import Path

import httpx
import pytest
import respx

from nestor.adapters.models import OpenAICompatibleModel
from nestor.adapters.models.openai_compatible import plugin
from nestor.core import ContractError, ProviderError
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
from nestor.runtime.plugins import Services
from nestor.testing.cognition import ConversationModelContract

BASE_URL = "https://llm.test/api/v1"
COMPLETIONS = f"{BASE_URL}/chat/completions"
KEY = "sk-test-0123456789"
LIGHT = ToolSpec(
    "set_light",
    "Allume ou éteint une lampe.",
    {"type": "object", "properties": {"room": {"type": "string"}, "on": {"type": "boolean"}}, "required": ["room"]},
)
HELLO = ModelRequest(messages=(Message.user("Bonjour"),))


def chunk(delta: dict[str, object] | None = None, finish: str | None = None) -> dict[str, object]:
    return {
        "id": "gen-1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}],
    }


def call_fragment(
    index: int, *, id: str | None = None, name: str | None = None, arguments: str = ""
) -> dict[str, object]:
    fragment: dict[str, object] = {"index": index, "type": "function", "function": {"arguments": arguments}}
    if id:
        fragment["id"] = id
    if name:
        fragment["function"] = {"name": name, "arguments": arguments}
    return fragment


def sse(*chunks: object, done: bool = True) -> bytes:
    """A streamed body as OpenRouter sends it: a keep-alive comment, `data:` events, then `[DONE]`."""
    events = [": OPENROUTER PROCESSING\n\n", *(f"data: {json.dumps(c)}\n\n" for c in chunks)]
    if done:
        events.append("data: [DONE]\n\n")
    return "".join(events).encode()


def streamed(*chunks: object, done: bool = True) -> httpx.Response:
    return httpx.Response(200, content=sse(*chunks, done=done), headers={"content-type": "text/event-stream"})


TEXT_REPLY = (chunk({"role": "assistant", "content": "Ça va"}), chunk({"content": " très bien."}), chunk(finish="stop"))
TOOL_REPLY = (
    chunk({"role": "assistant", "tool_calls": [call_fragment(0, id="call_1", name="set_light")]}),
    chunk({"tool_calls": [call_fragment(0, arguments='{"room": "sa')]}),
    chunk({"tool_calls": [call_fragment(0, arguments='lon", "on": true}')]}),
    chunk(finish="tool_calls"),
)


def sent(route: respx.Route) -> dict[str, object]:
    return json.loads(route.calls.last.request.content)


def model(
    *,
    base_url: str = BASE_URL,
    api_key: str = KEY,
    extra_body: Mapping[str, object] | None = None,
    provider: str = "openai-compatible",
) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        base_url=base_url, api_key=api_key, model="vendor/model", extra_body=extra_body, provider=provider
    )


async def collect(
    request: ModelRequest = HELLO,
    *,
    extra_body: Mapping[str, object] | None = None,
    provider: str = "openai-compatible",
) -> list[ModelOutput]:
    async with model(extra_body=extra_body, provider=provider) as m:
        return [o async for o in m.stream(request)]


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


class TestOpenAICompatibleModel(ConversationModelContract):
    @pytest.fixture(autouse=True)
    def _endpoint(self, api: respx.MockRouter) -> None:
        def reply(request: httpx.Request) -> httpx.Response:
            return streamed(*(TOOL_REPLY if json.loads(request.content).get("tools") else TEXT_REPLY))

        api.post(COMPLETIONS).mock(side_effect=reply)
        api.post("https://down.test/v1/chat/completions").respond(401, json={"error": {"message": "No auth"}})

    def model(self) -> ConversationModel:
        return model()

    def tool_request(self) -> ModelRequest:
        return ModelRequest(messages=(Message.user("Allume le salon."),), tools=(LIGHT,))

    def unavailable_model(self) -> ConversationModel:
        return model(base_url="https://down.test/v1")


async def test_a_history_with_tool_calls_is_sent_in_the_openai_wire_format(api: respx.MockRouter) -> None:
    route = api.post(COMPLETIONS).mock(return_value=streamed(*TEXT_REPLY))
    call = ToolCall("call_1", "set_light", {"room": "salon", "on": True})
    history = (
        Message(role=Role.SYSTEM, content="Tu es Nestor."),
        Message.user("Allume le salon."),
        Message(role=Role.ASSISTANT, tool_calls=(call,)),
        Message(role=Role.TOOL, content="ok", tool_call_id="call_1"),
        Message(role=Role.ASSISTANT, content="C'est allumé."),
    )

    await collect(ModelRequest(messages=history, tools=(LIGHT,)))

    body = sent(route)
    assert body["model"] == "vendor/model"
    assert body["stream"] is True
    assert body["messages"] == [
        {"role": "system", "content": "Tu es Nestor."},
        {"role": "user", "content": "Allume le salon."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "set_light", "arguments": '{"room": "salon", "on": true}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "assistant", "content": "C'est allumé."},
    ]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {"name": "set_light", "description": LIGHT.description, "parameters": LIGHT.parameters},
        }
    ]
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY}"


async def test_a_request_without_tools_sends_no_tool_list(api: respx.MockRouter) -> None:
    route = api.post(COMPLETIONS).mock(return_value=streamed(*TEXT_REPLY))
    await collect()
    assert "tools" not in sent(route)


async def test_extra_body_pins_the_provider_and_the_reasoning_effort(api: respx.MockRouter) -> None:
    route = api.post(COMPLETIONS).mock(return_value=streamed(*TEXT_REPLY))
    extra = {"provider": {"order": ["google-vertex/europe"], "allow_fallbacks": False}, "reasoning": {"effort": "none"}}

    await collect(extra_body=extra)

    body = sent(route)
    assert body["provider"] == extra["provider"]
    assert body["reasoning"] == extra["reasoning"]


async def test_a_tool_message_without_its_call_id_is_refused(api: respx.MockRouter) -> None:
    orphan = ModelRequest(messages=(Message(role=Role.TOOL, content="ok"),))
    with pytest.raises(ContractError, match="tool_call_id"):
        await collect(orphan)


async def test_parallel_tool_calls_split_across_deltas_are_reassembled_in_order(api: respx.MockRouter) -> None:
    api.post(COMPLETIONS).mock(
        return_value=streamed(
            chunk({"tool_calls": [call_fragment(1, id="call_b", name="set_light", arguments='{"room":')]}),
            chunk({"tool_calls": [call_fragment(0, id="call_a", name="set_light")]}),
            chunk(
                {
                    "tool_calls": [
                        call_fragment(1, arguments=' "cuisine"}'),
                        call_fragment(0, arguments='{"room": "salon"}'),
                    ]
                }
            ),
            chunk(finish="tool_calls"),
        )
    )

    outputs = await collect()

    assert outputs == [
        ToolCallRequested(ToolCall("call_a", "set_light", {"room": "salon"})),
        ToolCallRequested(ToolCall("call_b", "set_light", {"room": "cuisine"})),
        Finished(FinishReason.TOOL_CALLS),
    ]


async def test_a_tool_call_without_arguments_or_id_still_reaches_the_agent(api: respx.MockRouter) -> None:
    fragment = {"type": "function", "function": {"name": "set_light"}}  # no index, id nor arguments
    api.post(COMPLETIONS).mock(return_value=streamed(chunk({"tool_calls": [fragment]}), chunk(finish="tool_calls")))

    first = (await collect())[0]

    assert isinstance(first, ToolCallRequested)
    assert first.call.name == "set_light"
    assert first.call.arguments == {}
    assert first.call.id


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        (call_fragment(0, id="c1", name="set_light", arguments='{"room": "sal'), "invalid JSON arguments"),
        (call_fragment(0, id="c1", name="set_light", arguments='["salon"]'), "invalid JSON arguments"),
        (call_fragment(0, id="c1", arguments="{}"), "has no name"),
    ],
)
async def test_a_malformed_tool_call_is_a_provider_error(
    api: respx.MockRouter, fragment: dict[str, object], expected: str
) -> None:
    api.post(COMPLETIONS).mock(return_value=streamed(chunk({"tool_calls": [fragment]}), chunk(finish="tool_calls")))
    with pytest.raises(ProviderError, match=expected) as raised:
        await collect()
    assert raised.value.transient  # the request was valid: asking again may give a well-formed call


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("tool_calls", FinishReason.TOOL_CALLS),
        ("content_filter", FinishReason.STOP),
    ],
)
async def test_the_finish_reason_is_mapped(api: respx.MockRouter, reason: str, expected: FinishReason) -> None:
    api.post(COMPLETIONS).mock(return_value=streamed(chunk({"content": "Oui."}), chunk(finish=reason)))
    assert (await collect())[-1] == Finished(expected)


async def test_a_stream_ending_on_done_without_a_reason_is_a_normal_stop(api: respx.MockRouter) -> None:
    api.post(COMPLETIONS).mock(return_value=streamed(chunk({"content": "Oui."})))
    assert await collect() == [TextDelta("Oui."), Finished(FinishReason.STOP)]


async def test_a_stream_cut_before_the_end_is_a_transient_provider_error(api: respx.MockRouter) -> None:
    api.post(COMPLETIONS).mock(return_value=streamed(chunk({"content": "Ça"}), done=False))
    with pytest.raises(ProviderError, match="before the reply was finished") as raised:
        await collect()
    assert raised.value.transient


async def test_a_stream_that_finished_may_omit_done(api: respx.MockRouter) -> None:
    api.post(COMPLETIONS).mock(return_value=streamed(chunk({"content": "Oui."}), chunk(finish="stop"), done=False))
    assert await collect() == [TextDelta("Oui."), Finished(FinishReason.STOP)]


async def test_a_malformed_chunk_is_a_provider_error(api: respx.MockRouter) -> None:
    api.post(COMPLETIONS).respond(200, content=b"data: <html>oops</html>\n\n")
    with pytest.raises(ProviderError, match="malformed stream chunk"):
        await collect()


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        ({"code": 502, "message": "Upstream overloaded"}, True),
        ({"code": 400, "message": "Context too long"}, False),
        ({"code": "server_error", "message": "Upstream overloaded"}, True),
        ("Upstream overloaded", True),
    ],
)
async def test_an_error_inside_the_stream_is_a_provider_error(
    api: respx.MockRouter, error: object, transient: bool
) -> None:
    api.post(COMPLETIONS).mock(
        return_value=streamed(chunk({"content": "Ça"}), {"error": error, "choices": [{"finish_reason": "error"}]})
    )
    with pytest.raises(ProviderError, match="error in stream") as raised:
        await collect()
    assert raised.value.transient is transient


@pytest.mark.parametrize(
    ("status", "body", "transient"),
    [
        (429, b'{"error": {"message": "Rate limit exceeded", "code": 429}}', True),
        (503, b"<html>Service Unavailable</html>", True),
        (400, b'{"error": {"message": "Invalid model", "code": 400}}', False),
        (401, b'{"error": {"message": "No auth credentials found", "code": 401}}', False),
        (403, b'{"error": "forbidden"}', False),
        (404, b"Not Found", False),
    ],
)
async def test_http_errors_say_whether_a_retry_may_succeed(
    api: respx.MockRouter, status: int, body: bytes, transient: bool
) -> None:
    api.post(COMPLETIONS).respond(status, content=body)
    with pytest.raises(ProviderError, match=f"HTTP {status}") as raised:
        await collect(provider="openrouter")
    assert raised.value.transient is transient
    assert raised.value.provider == "openrouter"


async def test_the_api_key_never_appears_in_an_error(api: respx.MockRouter) -> None:
    api.post(COMPLETIONS).respond(401, json={"error": {"message": f"Invalid key {KEY}"}})
    with pytest.raises(ProviderError) as raised:
        await collect()
    assert KEY not in str(raised.value)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.ReadTimeout("read timed out"), "timed out"),
        (httpx.ConnectError("connection refused"), "transport failure"),
    ],
)
async def test_a_network_failure_is_a_transient_provider_error(
    api: respx.MockRouter, failure: Exception, expected: str
) -> None:
    api.post(COMPLETIONS).mock(side_effect=failure)
    with pytest.raises(ProviderError, match=expected) as raised:
        await collect()
    assert raised.value.transient


class StalledBody(httpx.AsyncByteStream):
    """Sends the first words of a reply, then stalls as a slow model would; records when it is closed."""

    def __init__(self) -> None:
        self.closed = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield sse(chunk({"content": "Alors,"}), done=False)
        await asyncio.Event().wait()
        yield b""  # never reached

    async def aclose(self) -> None:
        self.closed.set()


async def test_closing_the_stream_early_closes_the_http_response(api: respx.MockRouter) -> None:
    body = StalledBody()
    api.post(COMPLETIONS).mock(return_value=httpx.Response(200, stream=body))

    async with model() as m:
        stream = m.stream(HELLO)
        first = await asyncio.wait_for(anext(stream), timeout=1)
        await stream.aclose()

        assert first == TextDelta("Alors,")
        assert body.closed.is_set()


async def test_cancelling_the_consumer_closes_the_http_response(api: respx.MockRouter) -> None:
    body = StalledBody()
    api.post(COMPLETIONS).mock(return_value=httpx.Response(200, stream=body))
    started = asyncio.Event()

    async def consume(m: OpenAICompatibleModel) -> None:
        async for _ in m.stream(HELLO):
            started.set()

    async with model() as m:
        task = asyncio.create_task(consume(m))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert body.closed.is_set()


async def test_a_model_that_was_never_started_closes_cleanly_but_cannot_stream() -> None:
    m = model()
    await m.close()
    with pytest.raises(ContractError, match="before start"):
        await anext(m.stream(HELLO))


def test_an_empty_api_key_is_refused() -> None:
    with pytest.raises(ContractError, match="empty api_key"):
        model(api_key="")


async def test_the_plugin_builds_a_model_from_its_configuration(api: respx.MockRouter, tmp_path: Path) -> None:
    route = api.post(COMPLETIONS).mock(return_value=streamed(*TEXT_REPLY))
    raw = {"base_url": BASE_URL, "api_key": KEY, "model": "vendor/model", "extra_body": {"temperature": 0.2}}

    async with plugin.create(raw, "main", Services(data_dir=tmp_path)) as m:
        assert isinstance(m, ConversationModel)
        outputs = [o async for o in m.stream(HELLO)]

    assert outputs[-1] == Finished(FinishReason.STOP)
    assert sent(route)["temperature"] == 0.2


@pytest.mark.parametrize(
    "raw", [{"base_url": BASE_URL, "model": "m"}, {"base_url": BASE_URL, "model": "m", "api_key": ""}]
)
def test_the_plugin_refuses_a_configuration_without_a_key(raw: dict[str, object], tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="api_key"):
        plugin.create(raw, "main", Services(data_dir=tmp_path))


OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
WEATHER = ToolSpec(
    "get_weather",
    "Donne la météo actuelle d'une ville.",
    {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)


@pytest.mark.live
@pytest.mark.skipif(not OPENROUTER_KEY, reason="OPENROUTER_API_KEY is not set")
class TestOpenRouterLive(ConversationModelContract):
    """The contract against OpenRouter, pinned to Claude Haiku on Vertex in Europe without reasoning."""

    def model(self, api_key: str = OPENROUTER_KEY) -> ConversationModel:
        return OpenAICompatibleModel(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model="anthropic/claude-haiku-5.5",
            extra_body={
                "provider": {"order": ["google-vertex/europe"], "allow_fallbacks": False},
                "reasoning": {"effort": "none"},
            },
            provider="openrouter",
        )

    def tool_request(self) -> ModelRequest:
        system = Message(role=Role.SYSTEM, content="Utilise toujours tes outils pour répondre.")
        return ModelRequest(messages=(system, Message.user("Quel temps fait-il à Lyon ?")), tools=(WEATHER,))

    def unavailable_model(self) -> ConversationModel:
        return self.model(api_key="sk-or-v1-invalid")


@pytest.mark.parametrize(
    ("base_url", "brand"),
    [
        ("https://openrouter.ai/api/v1", "openrouter"),
        ("https://api.openai.com/v1", "openai"),
        ("http://localhost:8000", None),
    ],
)
def test_the_model_names_its_provider_and_its_model(base_url: str, brand: str | None) -> None:
    built = model(base_url=base_url)
    assert built.brand == brand and built.details() == {"model": "vendor/model"}
