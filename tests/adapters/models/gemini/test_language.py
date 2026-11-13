"""Gemini over Google's Gemini API: the language model contract over a mocked event stream, the wire format (roles,
tool rounds with their thought signatures, documents), usage, error mapping and interruption."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from nestor.adapters.models.gemini.language import GeminiLanguage
from nestor.adapters.models.gemini.wire import UNSIGNED
from nestor.core import ContractError, ProviderError
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

BASE_URL = "https://gemini.test/v1beta"
STREAM = f"{BASE_URL}/models/gemini-2.5-flash:streamGenerateContent"
KEY = "AIza-test-0123456789"
LIGHT = ToolSpec(
    "set_light",
    "Allume ou éteint une lampe.",
    {"type": "object", "properties": {"room": {"type": "string"}}, "additionalProperties": False},
)
HELLO = ModelRequest(messages=(Message.user("Bonjour"),))


def chunk(*parts: dict[str, Any], finish: str | None = None, **extra: object) -> dict[str, Any]:
    candidate: dict[str, Any] = {"content": {"role": "model", "parts": list(parts)}, "index": 0}
    if finish:
        candidate["finishReason"] = finish
    return {"candidates": [candidate], "modelVersion": "gemini-2.5-flash", **extra}


def streamed(*chunks: dict[str, Any]) -> httpx.Response:
    body = "".join(f"data: {json.dumps(c)}\r\n\r\n" for c in chunks).encode()
    return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


TEXT_REPLY = (chunk({"text": "Ça va"}), chunk({"text": " très bien."}, finish="STOP"))
CALL = {"functionCall": {"name": "set_light", "args": {"room": "salon"}}, "thoughtSignature": "c2lnbmF0dXJl"}
TOOL_REPLY = (
    chunk({"thought": True, "text": "Il faut la lampe."}, {"text": "Je regarde."}),
    chunk(CALL, finish="STOP"),
)


def sent(route: respx.Route) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


def model(*, base_url: str = BASE_URL) -> GeminiLanguage:
    return GeminiLanguage(api_key=KEY, model="gemini-2.5-flash", base_url=base_url)


async def collect(request: ModelRequest = HELLO) -> list[ModelOutput]:
    async with model() as m:
        return [o async for o in m.stream(request)]


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


class TestGeminiModel(LanguageModelContract):
    @pytest.fixture(autouse=True)
    def _endpoint(self, api: respx.MockRouter) -> None:
        def reply(request: httpx.Request) -> httpx.Response:
            return streamed(*(TOOL_REPLY if json.loads(request.content).get("tools") else TEXT_REPLY))

        api.post(STREAM).mock(side_effect=reply)
        api.post("https://down.test/v1beta/models/gemini-2.5-flash:streamGenerateContent").respond(
            400, json={"error": {"code": 400, "message": "API key not valid", "status": "INVALID_ARGUMENT"}}
        )

    def model(self) -> LanguageModel:
        return model()

    def tool_request(self) -> ModelRequest:
        return ModelRequest(messages=(Message.user("Allume le salon."),), tools=(LIGHT,))

    def unavailable_model(self) -> LanguageModel:
        return model(base_url="https://down.test/v1beta")


async def test_a_tool_call_comes_with_its_thought_signature_and_the_thoughts_stay_out(api: respx.MockRouter) -> None:
    api.post(STREAM).mock(return_value=streamed(*TOOL_REPLY))
    outputs = await collect()
    assert outputs[0] == TextDelta("Je regarde."), "a summary of its thinking is not part of the answer"
    [call] = [o.call for o in outputs if isinstance(o, ToolCallRequested)]
    assert (call.name, dict(call.arguments), call.replay) == ("set_light", {"room": "salon"}, "c2lnbmF0dXJl")
    assert isinstance(outputs[-1], Finished) and outputs[-1].reason is FinishReason.TOOL_CALLS


async def test_the_request_is_authenticated_and_streamed_as_server_sent_events(api: respx.MockRouter) -> None:
    route = api.post(STREAM).mock(return_value=streamed(*TEXT_REPLY))
    await collect()
    request = route.calls.last.request
    assert (request.headers["x-goog-api-key"], request.url.params["alt"]) == (KEY, "sse")
    assert sent(route) == {"contents": [{"role": "user", "parts": [{"text": "Bonjour"}]}]}


async def test_a_tool_round_goes_back_signed_with_its_results_together_and_matched_by_id(api: respx.MockRouter) -> None:
    route = api.post(STREAM).mock(return_value=streamed(*TEXT_REPLY))
    calls = (
        ToolCall("c1", "set_light", {"room": "salon"}, replay="c2ln"),
        ToolCall("c2", "get_weather", {}),
    )
    history = (
        Message(role=Role.SYSTEM, layers=("Tu es Nestor.", "Le foyer : Mathis."), content="Il est 9 h."),
        Message.user("Allume et dis-moi le temps."),
        Message(role=Role.ASSISTANT, content="Je m'en occupe.", tool_calls=calls),
        Message(role=Role.TOOL, content="ok", tool_call_id="c1"),
        Message(role=Role.TOOL, content="soleil", tool_call_id="c2"),
    )
    await collect(ModelRequest(messages=history, tools=(LIGHT,)))
    body = sent(route)
    assert body["systemInstruction"] == {
        "parts": [{"text": "Tu es Nestor."}, {"text": "Le foyer : Mathis."}, {"text": "Il est 9 h."}]
    }, "from the most stable to the least: Gemini caches the prefix by itself"
    assert body["contents"][1:] == [
        {
            "role": "model",
            "parts": [
                {"text": "Je m'en occupe."},
                {
                    "functionCall": {"id": "c1", "name": "set_light", "args": {"room": "salon"}},
                    "thoughtSignature": "c2ln",
                },
                {
                    "functionCall": {"id": "c2", "name": "get_weather", "args": {}},
                    "thoughtSignature": UNSIGNED,  # a call Gemini did not make (before a fallback)
                },
            ],
        },
        {
            "role": "user",
            "parts": [
                {"functionResponse": {"id": "c1", "name": "set_light", "response": {"result": "ok"}}},
                {"functionResponse": {"id": "c2", "name": "get_weather", "response": {"result": "soleil"}}},
            ],
        },
    ]
    assert body["tools"] == [
        {
            "functionDeclarations": [
                {"name": "set_light", "description": LIGHT.description, "parametersJsonSchema": LIGHT.parameters}
            ]
        }
    ], "the tool's JSON Schema as it is, not narrowed to the OpenAPI subset"


async def test_a_tool_result_for_a_call_it_never_made_is_refused(api: respx.MockRouter) -> None:
    with pytest.raises(ContractError, match="tool_call_id"):
        await collect(ModelRequest(messages=(Message(role=Role.TOOL, content="ok", tool_call_id="nope"),)))


async def test_a_pdf_and_a_photo_go_inline_before_the_words(api: respx.MockRouter) -> None:
    route = api.post(STREAM).mock(return_value=streamed(*TEXT_REPLY))
    pdf = Document(media_type="application/pdf", data=b"%PDF", name="devis.pdf")
    photo = Image(media_type="image/png", data=b"png")
    await collect(ModelRequest(messages=(Message.user("C'est combien ?", images=(photo,), documents=(pdf,)),)))
    [content] = sent(route)["contents"]
    assert content["parts"] == [
        {"inlineData": {"mimeType": "application/pdf", "data": "JVBERg=="}},
        {"inlineData": {"mimeType": "image/png", "data": "cG5n"}},
        {"text": "C'est combien ?"},
    ]


async def test_the_reply_says_what_it_cost_in_tokens_thinking_included(api: respx.MockRouter) -> None:
    usage = {
        "promptTokenCount": 2000,
        "cachedContentTokenCount": 1500,
        "candidatesTokenCount": 9,
        "thoughtsTokenCount": 30,
    }
    api.post(STREAM).mock(return_value=streamed(chunk({"text": "Oui."}, finish="STOP", usageMetadata=usage)))
    assert (await collect())[-1] == Finished(
        FinishReason.STOP, Usage(input_tokens=2000, output_tokens=39, cached_input_tokens=1500), "gemini-2.5-flash"
    )


async def test_an_answer_cut_by_its_length_says_so(api: respx.MockRouter) -> None:
    api.post(STREAM).mock(return_value=streamed(chunk({"text": "Il était"}, finish="MAX_TOKENS")))
    finished = (await collect())[-1]
    assert isinstance(finished, Finished) and finished.reason is FinishReason.LENGTH


@pytest.mark.parametrize(
    ("chunks", "expected", "transient"),
    [
        ((chunk({"text": "Ça va"}),), "stream ended before the reply was finished", True),
        (({"promptFeedback": {"blockReason": "SAFETY"}},), "prompt blocked: SAFETY", False),
        (({"error": {"code": 503, "message": "overloaded"}},), "error in stream: overloaded", True),
        ((chunk({"functionCall": {"args": {}}}, finish="STOP"),), "has no name", True),
        ((chunk({"text": "Voici"}, finish="SAFETY"),), "stopped \\(SAFETY\\)", False),
        ((chunk({"text": "Il était"}, finish="RECITATION"),), "stopped \\(RECITATION\\)", False),
        ((chunk(finish="MALFORMED_FUNCTION_CALL"),), "stopped \\(MALFORMED_FUNCTION_CALL\\)", True),
    ],
)
async def test_a_failed_stream_is_a_provider_error(
    api: respx.MockRouter, chunks: tuple[dict[str, Any], ...], expected: str, transient: bool
) -> None:
    api.post(STREAM).mock(return_value=streamed(*chunks))
    with pytest.raises(ProviderError, match=expected) as raised:
        await collect()
    assert raised.value.transient is transient


@pytest.mark.parametrize(("status", "transient"), [(400, False), (403, False), (429, True), (500, True)])
async def test_http_errors_say_whether_a_retry_may_succeed(api: respx.MockRouter, status: int, transient: bool) -> None:
    api.post(STREAM).respond(status, json={"error": {"code": status, "message": f"status {status} {KEY}"}})
    with pytest.raises(ProviderError, match=f"HTTP {status}: status {status}") as raised:
        await collect()
    assert raised.value.transient is transient
    assert KEY not in str(raised.value)


class StalledBody(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield f"data: {json.dumps(chunk({'text': 'Alors,'}))}\n\n".encode()
        await asyncio.Event().wait()
        yield b""  # never reached

    async def aclose(self) -> None:
        self.closed.set()


async def test_closing_the_stream_early_closes_the_http_response(api: respx.MockRouter) -> None:
    body = StalledBody()
    api.post(STREAM).mock(return_value=httpx.Response(200, stream=body))
    async with model() as m:
        stream = m.stream(HELLO)
        assert await asyncio.wait_for(anext(stream), timeout=1) == TextDelta("Alors,")
        await stream.aclose()
        assert body.closed.is_set()


async def test_a_history_window_opening_on_an_answer_starts_at_the_next_words_of_a_person(
    api: respx.MockRouter,
) -> None:
    route = api.post(STREAM).mock(return_value=streamed(*TEXT_REPLY))
    window = (
        Message(role=Role.ASSISTANT, tool_calls=(ToolCall("c0", "set_light", {}),)),
        Message(role=Role.TOOL, content="ok", tool_call_id="c0"),
        Message(role=Role.ASSISTANT, content="C'est allumé."),
        Message.user("Merci."),
    )
    await collect(ModelRequest(messages=window))
    assert sent(route)["contents"] == [{"role": "user", "parts": [{"text": "Merci."}]}]
