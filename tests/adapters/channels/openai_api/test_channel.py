"""The OpenAI-compatible API, through its ASGI app: a key belongs to an account, only the last message the person
wrote is a turn (pictures included), answers come whole or stream as OpenAI streams them, and Nestor cannot write
to an API client by itself."""

import base64
import json
from collections.abc import AsyncGenerator

import httpx
import pytest

from nestor.adapters.channels.openai_api.channel import OpenAIApiChannel
from nestor.core import ProviderError
from nestor.modules.channels import Address, AttachmentKind, InboundMessage, Medium
from nestor.testing.channels import ScriptedAssistant

KEY, OTHER = "sk-nestor-mathis", "sk-nestor-guest"


def answer(message: InboundMessage) -> str:
    return f"echo: {message.text}"


@pytest.fixture
def assistant() -> ScriptedAssistant:
    return ScriptedAssistant(answer, strangers=frozenset({"guest"}))


@pytest.fixture
async def api(assistant: ScriptedAssistant) -> AsyncGenerator[httpx.AsyncClient]:
    channel = OpenAIApiChannel("openai-api", keys={"mathis": KEY, "guest": OTHER})
    transport = httpx.ASGITransport(app=channel.app(assistant))
    async with httpx.AsyncClient(transport=transport, base_url="http://nestor.test") as client:
        yield client


def asked(*messages: dict, stream: bool = False) -> dict:
    return {"model": "nestor", "messages": list(messages), "stream": stream}


async def test_only_the_last_message_the_person_wrote_is_a_turn(
    api: httpx.AsyncClient, assistant: ScriptedAssistant
) -> None:
    history = (
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "bonjour"},
        {"role": "assistant", "content": "echo: bonjour"},
        {"role": "user", "content": "et la météo ?"},
    )
    answered = await api.post("/v1/chat/completions", json=asked(*history), headers={"Authorization": f"Bearer {KEY}"})
    assert answered.status_code == 200
    assert answered.json()["choices"][0]["message"] == {"role": "assistant", "content": "echo: et la météo ?"}
    [message] = assistant.messages
    assert message.address.conversation.startswith("mathis/")
    assert message.sender is not None and message.sender.id == "mathis"


async def test_a_picture_sent_inline_comes_with_the_turn(api: httpx.AsyncClient, assistant: ScriptedAssistant) -> None:
    picture = "data:image/png;base64," + base64.b64encode(b"png").decode()
    parts = [{"type": "text", "text": "c'est quoi ?"}, {"type": "image_url", "image_url": {"url": picture}}]
    await api.post(
        "/v1/chat/completions",
        json=asked({"role": "user", "content": parts}),
        headers={"Authorization": f"Bearer {KEY}"},
    )
    [message] = assistant.messages
    assert message.text == "c'est quoi ?"
    assert [(a.kind, a.data) for a in message.attachments] == [(AttachmentKind.IMAGE, b"png")]


async def test_the_answer_streams_as_openai_streams_it(api: httpx.AsyncClient) -> None:
    async with api.stream(
        "POST",
        "/v1/chat/completions",
        json=asked({"role": "user", "content": "raconte"}, stream=True),
        headers={"Authorization": f"Bearer {KEY}"},
    ) as response:
        events = [line.removeprefix("data: ") async for line in response.aiter_lines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == "echo: raconte"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert {c["object"] for c in chunks} == {"chat.completion.chunk"}


@pytest.mark.parametrize(
    ("key", "status"), [("sk-wrong", 401), ("", 401), (OTHER, 403)], ids=["unknown-key", "no-key", "not-in-household"]
)
async def test_a_key_that_belongs_to_nobody_of_the_household_is_refused(
    api: httpx.AsyncClient, assistant: ScriptedAssistant, key: str, status: int
) -> None:
    refused = await api.post(
        "/v1/chat/completions", json=asked({"role": "user", "content": "?"}), headers={"Authorization": f"Bearer {key}"}
    )
    assert refused.status_code == status and "error" in refused.json()
    assert assistant.messages == []


async def test_models_lists_nestor_to_a_known_key(api: httpx.AsyncClient) -> None:
    listed = await api.get("/v1/models", headers={"Authorization": f"Bearer {KEY}"})
    assert [m["id"] for m in listed.json()["data"]] == ["nestor"]


async def test_nestor_cannot_write_to_an_api_client_by_itself() -> None:
    channel = OpenAIApiChannel("openai-api", keys={"mathis": KEY})
    assert not channel.reachable(Address("openai-api", "mathis"), Medium.WRITTEN)
    with pytest.raises(ProviderError):
        await channel.send(Address("openai-api", "mathis"), "hello", Medium.WRITTEN, ())


async def test_each_thread_of_the_client_is_a_conversation_of_its_own(
    api: httpx.AsyncClient, assistant: ScriptedAssistant
) -> None:
    headers = {"Authorization": f"bearer {KEY}"}  # the scheme in any case
    first = {"role": "user", "content": "bonjour"}
    await api.post("/v1/chat/completions", json=asked(first), headers=headers)
    follow = (first, {"role": "assistant", "content": "echo: bonjour"}, {"role": "user", "content": "et toi ?"})
    await api.post("/v1/chat/completions", json=asked(*follow), headers=headers)
    await api.post(
        "/v1/chat/completions", json=asked({"role": "user", "content": "nouvelle discussion"}), headers=headers
    )
    started, continued, other = (m.address for m in assistant.messages)
    assert started == continued != other
