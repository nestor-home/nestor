"""The Telegram channel against a fake Bot API served through `httpx.MockTransport`."""

import asyncio
import json
import logging
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from nestor.adapters.channels.telegram import MESSAGE_LIMIT, TelegramChannel, plugin, split_text
from nestor.core import ContractError, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.channels import Address, InboundMessage, Sender
from nestor.runtime import Services
from nestor.testing.channels import ScriptedAssistant
from nestor.testing.i18n import EchoLocalizer

TOKEN = "123456:secret-token"
ADA, BOB, STRANGER = 7, 8, 9


class FakeBotApi:
    """Just enough of the Bot API: queued updates for `getUpdates`, recorded `sendMessage` and
    `sendChatAction` calls, and scripted failures (an exception or a response) per method."""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self.sent: list[tuple[int | str, str]] = []
        self.payloads: list[dict[str, Any]] = []
        self.actions: list[tuple[int, str]] = []
        self.polls = 0
        self.failures: dict[str, deque[httpx.Response | Exception]] = defaultdict(deque)
        self._next_update = 1
        self.transport = httpx.MockTransport(self.handle)

    def say(self, text: str | None, *, user: int = ADA, chat: int | None = None, name: str = "Ada") -> None:
        message: dict[str, Any] = {"message_id": self._next_update, "date": 1_760_000_000}
        message |= {"chat": {"id": chat or user, "type": "private"}, "from": {"id": user, "first_name": name}}
        if text is not None:
            message["text"] = text
        self.updates.append({"update_id": self._next_update, "message": message})
        self._next_update += 1

    def other_update(self) -> None:
        self.updates.append({"update_id": self._next_update})
        self._next_update += 1

    def fail(self, method: str, *failures: httpx.Response | Exception) -> None:
        self.failures[method].extend(failures)

    def texts(self, chat: int) -> list[str]:
        return [text for to, text in self.sent if to == chat]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        token, method = request.url.path.removeprefix("/bot").split("/")
        if token != TOKEN:
            return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})
        if self.failures[method]:
            failure = self.failures[method].popleft()
            if isinstance(failure, Exception):
                raise failure
            return failure
        payload = json.loads(request.content)
        if method == "getUpdates":
            return ok(await self.get_updates(payload))
        if method == "sendChatAction":
            self.actions.append((payload["chat_id"], payload["action"]))
            return ok(True)
        self.payloads.append(payload)
        self.sent.append((payload["chat_id"], payload["text"]))
        return ok({"message_id": len(self.sent)})

    async def get_updates(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.polls += 1
        assert payload["allowed_updates"] == ["message"]
        self.updates = [u for u in self.updates if u["update_id"] >= payload.get("offset", 0)]
        deadline = asyncio.get_running_loop().time() + payload["timeout"]
        while not self.updates and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.005)
        return self.updates


def ok(result: object) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": result})


def error(status: int, description: str, **extra: object) -> httpx.Response:
    return httpx.Response(status, json={"ok": False, "error_code": status, "description": description, **extra})


async def eventually(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


def echo(message: InboundMessage) -> str:
    if message.text == "boom":
        raise RuntimeError("the model is down")
    return f"echo: {message.text}"


@pytest.fixture
def api() -> FakeBotApi:
    return FakeBotApi()


def channel_for(api: FakeBotApi, *, token: str = TOKEN, **options: Any) -> TelegramChannel:
    options = {"poll_timeout_s": 1, "retry_delay_s": 0.01, "typing_interval_s": 0.02} | options
    return TelegramChannel("telegram", token=token, transport=api.transport, **options)


@asynccontextmanager
async def serving(
    api: FakeBotApi, assistant: ScriptedAssistant, **options: Any
) -> AsyncGenerator[tuple[TelegramChannel, asyncio.Task[None]]]:
    channel = channel_for(api, **options)
    task = asyncio.create_task(channel.serve(assistant))
    try:
        yield channel, task
    finally:
        await channel.close()
        await asyncio.wait_for(task, 1)


async def test_a_household_member_is_answered_in_the_same_chat(api: FakeBotApi) -> None:
    assistant = ScriptedAssistant(echo)
    async with serving(api, assistant):
        api.say("hello there", user=ADA, chat=-100)
        await eventually(lambda: bool(api.sent))
    assert api.sent == [(-100, "echo: hello there")]
    assert "parse_mode" not in api.payloads[0]
    [message] = assistant.messages
    assert (message.address, message.sender) == (Address("telegram", "-100"), Sender(str(ADA), "Ada"))


async def test_each_update_is_answered_once(api: FakeBotApi) -> None:
    async with serving(api, ScriptedAssistant(echo)):
        api.say("one")
        await eventually(lambda: bool(api.sent))
        api.say("two")
        await eventually(lambda: len(api.sent) == 2)
    assert api.texts(ADA) == ["echo: one", "echo: two"]


async def test_a_stranger_is_ignored_without_logging_what_they_wrote(
    api: FakeBotApi, caplog: pytest.LogCaptureFixture
) -> None:
    assistant = ScriptedAssistant(echo, strangers=frozenset({str(STRANGER)}))
    with caplog.at_level(logging.INFO):
        async with serving(api, assistant):
            api.say("my secret plan", user=STRANGER)
            api.say("hi", user=ADA)
            await eventually(lambda: bool(api.sent))
    assert api.sent == [(ADA, "echo: hi")]
    assert [m.sender.id for m in assistant.messages] == [str(ADA)]
    assert str(STRANGER) in caplog.text
    assert "my secret plan" not in caplog.text


async def test_updates_without_a_text_message_are_skipped(api: FakeBotApi) -> None:
    assistant = ScriptedAssistant(echo)
    async with serving(api, assistant):
        api.say(None)  # a sticker
        api.other_update()  # an update of another kind
        api.say("after the sticker")
        await eventually(lambda: bool(api.sent))
    assert [m.text for m in assistant.messages] == ["after the sticker"]


async def test_a_long_answer_is_sent_in_several_messages_cut_between_sentences(api: FakeBotApi) -> None:
    answer = " ".join(f"This is sentence number {i}." for i in range(600))
    async with serving(api, ScriptedAssistant(lambda _: answer)):
        api.say("tell me everything")
        await eventually(lambda: " ".join(api.texts(ADA)) == answer)
    texts = api.texts(ADA)
    assert len(texts) > 1
    assert all(len(text) <= MESSAGE_LIMIT and text.endswith(".") for text in texts)


async def test_a_failing_answer_gets_an_apology_and_the_next_message_is_answered(api: FakeBotApi) -> None:
    async with serving(api, ScriptedAssistant(echo), apology="Oops."):
        api.say("boom")
        api.say("still there?")
        await eventually(lambda: len(api.sent) == 2)
    assert api.texts(ADA) == ["Oops.", "echo: still there?"]


async def test_an_empty_apology_keeps_the_bot_silent_after_a_failure(api: FakeBotApi) -> None:
    async with serving(api, ScriptedAssistant(echo), apology=""):
        api.say("boom")
        api.say("still there?")
        await eventually(lambda: bool(api.sent))
    assert api.texts(ADA) == ["echo: still there?"]


async def test_a_reply_that_cannot_be_delivered_does_not_stop_the_chat(api: FakeBotApi) -> None:
    api.fail("sendMessage", error(400, "Bad Request: message is too long"))
    async with serving(api, ScriptedAssistant(echo)):
        api.say("first")
        await eventually(lambda: not api.failures["sendMessage"])
        api.say("second")
        await eventually(lambda: bool(api.sent))
    assert api.texts(ADA) == ["echo: second"]


async def test_typing_is_shown_and_renewed_while_the_answer_is_produced(api: FakeBotApi) -> None:
    api.fail("sendChatAction", error(500, "Internal Server Error"))  # a lost indicator is not an error
    slow = ScriptedAssistant(lambda _: "a slow and thoughtful answer", word_delay_s=0.03)
    async with serving(api, slow):
        api.say("think hard")
        await eventually(lambda: bool(api.sent))
        typed = len(api.actions)
        await asyncio.sleep(0.1)
    assert typed >= 2
    assert set(api.actions) == {(ADA, "typing")}
    assert len(api.actions) == typed  # stops once the answer is sent


async def test_chats_are_answered_concurrently_and_each_chat_in_order(api: FakeBotApi) -> None:
    long_answers = ScriptedAssistant(
        lambda m: f"{m.text} " + "and " * (20 if m.text == "slow" else 0), word_delay_s=0.01
    )
    async with serving(api, long_answers):
        api.say("slow", user=ADA)
        api.say("next", user=ADA)
        api.say("quick", user=BOB, name="Bob")
        await eventually(lambda: len(api.sent) == 3)
    assert [chat for chat, _ in api.sent] == [BOB, ADA, ADA]
    assert [text.split()[0] for text in api.texts(ADA)] == ["slow", "next"]


async def test_transient_polling_failures_are_retried(api: FakeBotApi, caplog: pytest.LogCaptureFixture) -> None:
    api.fail(
        "getUpdates",
        httpx.ConnectError("connection refused"),
        httpx.Response(502, text="<html>Bad Gateway</html>"),
        error(429, "Too Many Requests: retry after 1", parameters={"retry_after": 0.01}),
    )
    with caplog.at_level(logging.WARNING):
        async with serving(api, ScriptedAssistant(echo)):
            api.say("are you up?")
            await eventually(lambda: bool(api.sent))
    assert api.sent == [(ADA, "echo: are you up?")]
    assert caplog.text.count("retrying") == 3


async def test_a_bad_token_stops_serving_with_a_permanent_error(api: FakeBotApi) -> None:
    channel = channel_for(api, token="123456:wrong")
    with pytest.raises(ProviderError) as raised:
        await asyncio.wait_for(channel.serve(ScriptedAssistant(echo)), 1)
    assert raised.value.transient is False
    await channel.close()


async def test_an_unexpected_updates_payload_stops_serving(api: FakeBotApi) -> None:
    api.fail("getUpdates", ok([{"message": {"text": "no update id"}}]))
    channel = channel_for(api)
    with pytest.raises(ProviderError) as raised:
        await asyncio.wait_for(channel.serve(ScriptedAssistant(echo)), 1)
    assert raised.value.transient is False
    await channel.close()


async def test_close_stops_a_waiting_long_poll_promptly(api: FakeBotApi) -> None:
    channel = channel_for(api, poll_timeout_s=30)
    serving = asyncio.create_task(channel.serve(ScriptedAssistant(echo)))
    await eventually(lambda: api.polls == 1)
    await channel.close()
    await asyncio.wait_for(serving, 0.5)
    await channel.close()  # closing twice is harmless


async def test_close_interrupts_a_retry_backoff(api: FakeBotApi) -> None:
    api.fail("getUpdates", httpx.ReadTimeout("timed out"))
    channel = channel_for(api, retry_delay_s=30)
    serving = asyncio.create_task(channel.serve(ScriptedAssistant(echo)))
    await eventually(lambda: not api.failures["getUpdates"])
    await channel.close()
    await asyncio.wait_for(serving, 0.5)


async def test_close_abandons_an_answer_in_progress(api: FakeBotApi) -> None:
    slow = ScriptedAssistant(lambda _: "never finished " * 50, word_delay_s=0.05)
    channel = channel_for(api)
    serving = asyncio.create_task(channel.serve(slow))
    api.say("long one")
    await eventually(lambda: bool(slow.messages))
    await channel.close()
    await asyncio.wait_for(serving, 0.5)
    assert api.sent == []


async def test_serving_can_be_cancelled(api: FakeBotApi) -> None:
    channel = channel_for(api, poll_timeout_s=30)
    serving = asyncio.create_task(channel.serve(ScriptedAssistant(echo)))
    await eventually(lambda: api.polls == 1)
    serving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(serving, 0.5)
    await channel.close()


async def test_a_closed_channel_serves_nothing(api: FakeBotApi) -> None:
    channel = channel_for(api)
    await channel.close()
    await asyncio.wait_for(channel.serve(ScriptedAssistant(echo)), 0.5)
    assert api.polls == 0


async def test_the_token_never_appears_in_logs(api: FakeBotApi, caplog: pytest.LogCaptureFixture) -> None:
    api.fail("getUpdates", httpx.ConnectError(f"cannot reach https://api.telegram.org/bot{TOKEN}/getUpdates"))
    with caplog.at_level(logging.DEBUG):
        async with serving(api, ScriptedAssistant(echo)):
            api.say("hi")
            await eventually(lambda: bool(api.sent))
    assert "getUpdates" in caplog.text  # httpx and the channel did log the requests
    assert TOKEN not in caplog.text


async def test_send_delivers_an_unprompted_message(api: FakeBotApi) -> None:
    async with channel_for(api) as channel:
        await channel.send(Address("telegram", str(ADA)), "Your task is done.")
    assert api.sent == [(str(ADA), "Your task is done.")]


@pytest.mark.parametrize(
    ("response", "transient"),
    [(error(403, "Forbidden: bot was blocked"), False), (error(503, "Service Unavailable"), True)],
)
async def test_send_reports_failures_and_whether_retrying_may_help(
    api: FakeBotApi, response: httpx.Response, transient: bool
) -> None:
    api.fail("sendMessage", response)
    async with channel_for(api) as channel:
        with pytest.raises(ProviderError) as raised:
            await channel.send(Address("telegram", str(ADA)), "Your task is done.")
    assert raised.value.transient is transient


async def test_send_to_another_channel_is_a_contract_error(api: FakeBotApi) -> None:
    async with channel_for(api) as channel:
        with pytest.raises(ContractError):
            await channel.send(Address("voice", "kitchen"), "hello")
    assert api.sent == []


async def test_send_after_close_fails_permanently(api: FakeBotApi) -> None:
    channel = channel_for(api)
    await channel.close()
    with pytest.raises(ProviderError) as raised:
        await channel.send(Address("telegram", str(ADA)), "hello")
    assert raised.value.transient is False


async def test_only_addresses_of_this_channel_are_reachable(api: FakeBotApi) -> None:
    async with channel_for(api) as channel:
        assert channel.reachable(Address("telegram", str(ADA)))
        assert not channel.reachable(Address("family-bot", str(ADA)))


async def test_the_plugin_names_the_channel_after_its_configured_instance(tmp_path: Path) -> None:
    channel = plugin.create(
        {"token": TOKEN}, "family-bot", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    )
    assert isinstance(channel, TelegramChannel)
    assert channel.channel_id == "family-bot"
    assert TOKEN not in repr(plugin.settings.model_validate({"token": TOKEN}))
    await channel.close()


def test_split_text_keeps_short_texts_whole() -> None:
    assert split_text("  Hello.  ") == ["Hello."]
    assert split_text("") == []


def test_split_text_prefers_a_paragraph_break_to_a_sentence_end() -> None:
    text = "One. Two.\n\nThree. Four."
    assert split_text(text, limit=20) == ["One. Two.", "Three. Four."]


def test_split_text_cuts_after_a_sentence_when_a_paragraph_is_too_long() -> None:
    text = "First sentence here. Second sentence there. Third one."
    assert split_text(text, limit=30) == ["First sentence here.", "Second sentence there.", "Third one."]


def test_split_text_cuts_a_word_longer_than_the_limit() -> None:
    assert split_text("abcdefghij", limit=4) == ["abcd", "efgh", "ij"]


def test_split_text_counts_characters_as_telegram_does() -> None:
    parts = split_text("🙂" * 5, limit=4)  # an emoji is two UTF-16 units
    assert parts == ["🙂🙂", "🙂🙂", "🙂"]


@pytest.mark.parametrize(
    ("configured", "said"), [({}, "telegram-apology"), ({"apology": ""}, ""), ({"apology": "Oups."}, "Oups.")]
)
async def test_the_apology_is_the_households_language_unless_configured(
    tmp_path: Path, configured: dict[str, str], said: str
) -> None:
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    channel = plugin.create({"token": TOKEN, **configured}, "bot", services)
    assert isinstance(channel, TelegramChannel) and channel._apology == said
    await channel.close()


@pytest.mark.parametrize(("configured", "seconds"), [({}, 4 * 3600.0), ({"conversation_ends_after_s": 86400}, 86400.0)])
async def test_a_written_conversation_lasts_hours_unless_configured(
    tmp_path: Path, configured: dict[str, int], seconds: float
) -> None:
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    channel = plugin.create({"token": TOKEN, **configured}, "bot", services)
    assert channel.conversation_ends_after_s == seconds
    await channel.close()
    with pytest.raises(ContractError):
        plugin.create({"token": TOKEN, "conversation_ends_after_s": 0}, "bot", services)
