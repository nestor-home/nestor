"""Claude over Anthropic's Messages API: the language model contract over a mocked event stream, the wire format
(cache breakpoints, documents, tool rounds), usage, error mapping and interruption."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from nestor import __version__
from nestor.adapters.models.anthropic.language import AnthropicLanguage
from nestor.adapters.models.anthropic.wire import Effort
from nestor.core import ProviderError
from nestor.modules.cognition import (
    Document,
    Finished,
    FinishReason,
    Image,
    LanguageModel,
    Message,
    ModelOutput,
    ModelRequest,
    Role,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    ToolSpec,
    Usage,
)
from nestor.testing.cognition import LanguageModelContract

BASE_URL = "https://claude.test/v1"
MESSAGES = f"{BASE_URL}/messages"
KEY = "sk-ant-test-0123456789"
LIGHT = ToolSpec(
    "set_light",
    "Allume ou éteint une lampe.",
    {"type": "object", "properties": {"room": {"type": "string"}}, "required": ["room"]},
)
HELLO = ModelRequest(messages=(Message.user("Bonjour"),))


def sse(*events: dict[str, Any]) -> bytes:
    """A streamed message as Anthropic sends it: each event named, then its JSON, with pings between."""
    lines = ['event: ping\ndata: {"type": "ping"}\n\n']
    lines += [f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events]
    return "".join(lines).encode()


def streamed(*events: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, content=sse(*events), headers={"content-type": "text/event-stream"})


def start(**usage: int) -> dict[str, Any]:
    counts = {"input_tokens": 12, "output_tokens": 1} | usage
    return {"type": "message_start", "message": {"model": "claude-haiku-5-5", "usage": counts}}


def text_block(index: int, *pieces: str) -> list[dict[str, Any]]:
    return [
        {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}},
        *({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": p}} for p in pieces),
        {"type": "content_block_stop", "index": index},
    ]


def tool_block(index: int, id: str, name: str, *fragments: str) -> list[dict[str, Any]]:
    block = {"type": "tool_use", "id": id, "name": name, "input": {}}
    deltas = ({"type": "input_json_delta", "partial_json": f} for f in fragments)
    return [
        {"type": "content_block_start", "index": index, "content_block": block},
        *({"type": "content_block_delta", "index": index, "delta": d} for d in deltas),
        {"type": "content_block_stop", "index": index},
    ]


def end(reason: str = "end_turn", output_tokens: int = 7) -> list[dict[str, Any]]:
    return [
        {"type": "message_delta", "delta": {"stop_reason": reason}, "usage": {"output_tokens": output_tokens}},
        {"type": "message_stop"},
    ]


TEXT_REPLY = (start(), *text_block(0, "Ça va", " très bien."), *end())
TOOL_REPLY = (
    start(),
    *text_block(0, "Je regarde."),
    *tool_block(1, "toolu_1", "set_light", '{"room": "sa', 'lon"}'),
    *tool_block(2, "toolu_2", "set_light", ""),
    *end("tool_use"),
)


def sent(route: respx.Route) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


def model(*, base_url: str = BASE_URL, effort: Effort | None = None) -> AnthropicLanguage:
    return AnthropicLanguage(api_key=KEY, model="claude-haiku-5-5", base_url=base_url, effort=effort)


async def collect(request: ModelRequest = HELLO) -> list[ModelOutput]:
    async with model() as m:
        return [o async for o in m.stream(request)]


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


class TestAnthropicModel(LanguageModelContract):
    @pytest.fixture(autouse=True)
    def _endpoint(self, api: respx.MockRouter) -> None:
        def reply(request: httpx.Request) -> httpx.Response:
            return streamed(*(TOOL_REPLY if json.loads(request.content).get("tools") else TEXT_REPLY))

        api.post(MESSAGES).mock(side_effect=reply)
        api.post("https://down.test/v1/messages").respond(
            401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
        )

    def model(self) -> LanguageModel:
        return model()

    def tool_request(self) -> ModelRequest:
        return ModelRequest(messages=(Message.user("Allume le salon."),), tools=(LIGHT,))

    def unavailable_model(self) -> LanguageModel:
        return model(base_url="https://down.test/v1")


async def test_text_streams_and_tool_calls_are_reassembled_in_order(api: respx.MockRouter) -> None:
    api.post(MESSAGES).mock(return_value=streamed(*TOOL_REPLY))
    outputs = await collect()
    assert outputs[0] == TextDelta("Je regarde.")
    calls = [o.call for o in outputs if isinstance(o, ToolCallRequested)]
    assert [(c.id, c.name, dict(c.arguments)) for c in calls] == [
        ("toolu_1", "set_light", {"room": "salon"}),
        ("toolu_2", "set_light", {}),
    ]
    finished = outputs[-1]
    assert isinstance(finished, Finished) and finished.reason is FinishReason.TOOL_CALLS


async def test_the_request_is_authenticated_versioned_named_and_streamed(api: respx.MockRouter) -> None:
    route = api.post(MESSAGES).mock(return_value=streamed(*TEXT_REPLY))
    async with model(effort=Effort.LOW) as m:
        [o async for o in m.stream(HELLO)]
    request = route.calls.last.request
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert request.headers["user-agent"] == f"nestor/{__version__} (+https://nestorhome.dev)"
    body = sent(route)
    assert (body["model"], body["stream"], body["output_config"]) == ("claude-haiku-5-5", True, {"effort": "low"})
    assert "tools" not in body and "system" not in body


async def test_the_stable_layers_and_the_conversation_are_cache_breakpoints(api: respx.MockRouter) -> None:
    route = api.post(MESSAGES).mock(return_value=streamed(*TEXT_REPLY))
    system = Message(role=Role.SYSTEM, layers=("Tu es Nestor.", "", "Le foyer : Mathis."), content="Il est 9 h.")
    await collect(ModelRequest(messages=(system, Message.user("Bonjour"))))
    body = sent(route)
    ephemeral = {"type": "ephemeral"}
    assert body["system"] == [
        {"type": "text", "text": "Tu es Nestor.", "cache_control": ephemeral},
        {"type": "text", "text": "Le foyer : Mathis.", "cache_control": ephemeral},
        {"type": "text", "text": "Il est 9 h."},
    ], "each stable layer ends a cached prefix, what changes every turn comes after"
    assert body["cache_control"] == ephemeral, "the conversation is cached up to its last message"
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Bonjour"}]}]


async def test_a_tool_round_goes_back_as_tool_use_then_its_results_together(api: respx.MockRouter) -> None:
    route = api.post(MESSAGES).mock(return_value=streamed(*TEXT_REPLY))
    calls = (ToolCall("toolu_1", "set_light", {"room": "salon"}), ToolCall("toolu_2", "set_light", {"room": "cuisine"}))
    history = (
        Message.user("Allume tout."),
        Message(role=Role.ASSISTANT, content="Je m'en occupe.", tool_calls=calls),
        Message(role=Role.TOOL, content="ok", tool_call_id="toolu_1"),
        Message(role=Role.TOOL, content="", tool_call_id="toolu_2"),
        Message(role=Role.ASSISTANT, content="C'est fait."),
    )
    await collect(ModelRequest(messages=history, tools=(LIGHT,)))
    body = sent(route)
    assert body["messages"][1:] == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Je m'en occupe."},
                {"type": "tool_use", "id": "toolu_1", "name": "set_light", "input": {"room": "salon"}},
                {"type": "tool_use", "id": "toolu_2", "name": "set_light", "input": {"room": "cuisine"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                {"type": "tool_result", "tool_use_id": "toolu_2"},
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "C'est fait."}]},
    ]
    assert body["tools"] == [{"name": "set_light", "description": LIGHT.description, "input_schema": LIGHT.parameters}]


async def test_a_pdf_is_a_document_block_and_a_photo_an_image_before_the_words(api: respx.MockRouter) -> None:
    route = api.post(MESSAGES).mock(return_value=streamed(*TEXT_REPLY))
    pdf = Document(media_type="application/pdf", data=b"%PDF-1.7 devis", name="devis.pdf")
    photo = Image(media_type="image/jpeg", data=b"jpeg bytes")
    await collect(ModelRequest(messages=(Message.user("C'est combien ?", images=(photo,), documents=(pdf,)),)))
    [message] = sent(route)["messages"]
    assert message["content"] == [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(pdf.data).decode()},
            "title": "devis.pdf",
        },
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "anBlZyBieXRlcw=="}},
        {"type": "text", "text": "C'est combien ?"},
    ]


async def test_the_reply_says_what_it_read_from_the_cache_and_which_model_answered(api: respx.MockRouter) -> None:
    reply = (start(input_tokens=20, cache_read_input_tokens=1800, cache_creation_input_tokens=100), *end())
    api.post(MESSAGES).mock(return_value=streamed(*reply))
    finished = (await collect())[-1]
    assert finished == Finished(
        FinishReason.STOP, Usage(input_tokens=1920, output_tokens=7, cached_input_tokens=1800), "claude-haiku-5-5"
    )


async def test_an_answer_cut_by_its_length_says_so(api: respx.MockRouter) -> None:
    api.post(MESSAGES).mock(return_value=streamed(start(), *end("max_tokens")))
    finished = (await collect())[-1]
    assert isinstance(finished, Finished) and finished.reason is FinishReason.LENGTH


async def test_a_refusal_is_a_provider_error_a_retry_will_not_get_past(api: respx.MockRouter) -> None:
    api.post(MESSAGES).mock(return_value=streamed(start(), *text_block(0, "Je"), *end("refusal")))
    with pytest.raises(ProviderError, match="refusal") as raised:
        await collect()
    assert not raised.value.transient, "the turn apologizes, or its fallback answers"


def thinking_block(index: int, thought: str, signature: str) -> list[dict[str, Any]]:
    start = {"type": "thinking", "thinking": "", "signature": ""}
    deltas = [{"type": "thinking_delta", "thinking": thought}, {"type": "signature_delta", "signature": signature}]
    return [
        {"type": "content_block_start", "index": index, "content_block": start},
        *({"type": "content_block_delta", "index": index, "delta": d} for d in deltas),
        {"type": "content_block_stop", "index": index},
    ]


async def test_the_reasoning_behind_a_tool_call_goes_back_unchanged_with_it_in_the_turn(api: respx.MockRouter) -> None:
    reply = (
        start(),
        *thinking_block(0, "La lampe du salon.", "sig-1"),
        *text_block(1, "Je regarde."),
        *tool_block(2, "toolu_1", "set_light", '{"room": "salon"}'),
        *end("tool_use"),
    )
    route = api.post(MESSAGES).mock(return_value=streamed(*reply))
    async with model() as m:
        outputs = [o async for o in m.stream(HELLO)]
        [call] = [o.call for o in outputs if isinstance(o, ToolCallRequested)]
        round_two = ModelRequest(
            messages=(
                Message.user("Allume le salon."),
                Message(role=Role.ASSISTANT, content="Je regarde.", tool_calls=(call,)),
                Message(role=Role.TOOL, content="ok", tool_call_id="toolu_1"),
            )
        )
        [o async for o in m.stream(round_two)]
    assert sent(route)["messages"][1]["content"] == [
        {"type": "thinking", "thinking": "La lampe du salon.", "signature": "sig-1"},
        {"type": "text", "text": "Je regarde."},
        {"type": "tool_use", "id": "toolu_1", "name": "set_light", "input": {"room": "salon"}},
    ]


@pytest.mark.parametrize(
    ("status", "transient"), [(400, False), (401, False), (404, False), (429, True), (500, True), (529, True)]
)
async def test_http_errors_say_whether_a_retry_may_succeed(api: respx.MockRouter, status: int, transient: bool) -> None:
    error = {"type": "error", "error": {"type": "some_error", "message": f"status {status}"}}
    api.post(MESSAGES).respond(status, json=error)
    with pytest.raises(ProviderError, match=f"HTTP {status}: status {status}") as raised:
        await collect()
    assert raised.value.transient is transient


@pytest.mark.parametrize(("kind", "transient"), [("overloaded_error", True), ("invalid_request_error", False)])
async def test_an_error_inside_the_stream_is_a_provider_error(
    api: respx.MockRouter, kind: str, transient: bool
) -> None:
    error = {"type": "error", "error": {"type": kind, "message": "Overloaded"}}
    api.post(MESSAGES).mock(return_value=streamed(start(), *text_block(0, "Ça"), error))
    with pytest.raises(ProviderError, match="error in stream: Overloaded") as raised:
        await collect()
    assert raised.value.transient is transient


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ((start(), *text_block(0, "Ça va")), "stream ended before the message was finished"),
        ((start(), *tool_block(0, "toolu_1", "set_light", '{"room":'), *end("tool_use")), "invalid JSON arguments"),
        ((start(), *tool_block(0, "toolu_1", "", "{}"), *end("tool_use")), "has no name"),
    ],
)
async def test_a_broken_stream_is_a_transient_provider_error(
    api: respx.MockRouter, events: tuple[dict[str, Any], ...], expected: str
) -> None:
    api.post(MESSAGES).mock(return_value=streamed(*events))
    with pytest.raises(ProviderError, match=expected) as raised:
        await collect()
    assert raised.value.transient


async def test_the_api_key_never_appears_in_an_error(api: respx.MockRouter) -> None:
    api.post(MESSAGES).respond(401, json={"error": {"message": f"invalid x-api-key {KEY}"}})
    with pytest.raises(ProviderError) as raised:
        await collect()
    assert KEY not in str(raised.value)


class StalledBody(httpx.AsyncByteStream):
    """The first words of a reply, then nothing, as a slow model; records when it is closed."""

    def __init__(self) -> None:
        self.closed = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield sse(start(), *text_block(0, "Alors,")[:2])
        await asyncio.Event().wait()
        yield b""  # never reached

    async def aclose(self) -> None:
        self.closed.set()


async def test_closing_the_stream_early_closes_the_http_response(api: respx.MockRouter) -> None:
    body = StalledBody()
    api.post(MESSAGES).mock(return_value=httpx.Response(200, stream=body))
    async with model() as m:
        stream = m.stream(HELLO)
        assert await asyncio.wait_for(anext(stream), timeout=1) == TextDelta("Alors,")
        await stream.aclose()
        assert body.closed.is_set()


async def test_a_history_window_opening_on_an_answer_starts_at_the_next_words_of_a_person(
    api: respx.MockRouter,
) -> None:
    route = api.post(MESSAGES).mock(return_value=streamed(*TEXT_REPLY))
    call = ToolCall("toolu_0", "set_light", {"room": "salon"})
    window = (
        Message(role=Role.ASSISTANT, tool_calls=(call,)),
        Message(role=Role.TOOL, content="ok", tool_call_id="toolu_0"),
        Message(role=Role.ASSISTANT, content="C'est allumé."),
        Message.user("Merci."),
    )
    await collect(ModelRequest(messages=window))
    assert sent(route)["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Merci."}]}]
