"""The Telegram channel against a fake Bot API served through `httpx.MockTransport`."""

import asyncio
import json
import logging
import re
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from nestor.adapters.channels.telegram import plugin
from nestor.adapters.channels.telegram.channel import FILE_LIMIT, MESSAGE_LIMIT, TelegramChannel
from nestor.core import ContractError, PersonId, ProviderError
from nestor.core.i18n import Locale
from nestor.modules.channels import (
    Address,
    Assistant,
    Attachment,
    AttachmentKind,
    InboundMessage,
    Medium,
    MessageEnd,
    Reply,
    Sender,
)
from nestor.runtime import Services
from nestor.testing.channels import OGG, MessagingChannelContract, Platform, ScriptedAssistant
from nestor.testing.i18n import EchoLocalizer

TOKEN = "123456:secret-token"
ADA, BOB, STRANGER = 7, 8, 9


class FakeBotApi:
    """Just enough of the Bot API: queued updates for `getUpdates`, recorded `sendMessage` and
    `sendChatAction` calls, and scripted failures (an exception or a response) per method."""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}  # by file id
        self.voices: list[tuple[str, bytes, str | None]] = []  # chat, recording, caption
        self.photos: list[tuple[str, bytes, str | None]] = []  # chat, picture, caption
        self.sent: list[tuple[int | str, str]] = []
        self.payloads: list[dict[str, Any]] = []
        self.actions: list[tuple[int, str]] = []
        self.polls = 0
        self.failures: dict[str, deque[httpx.Response | Exception]] = defaultdict(deque)
        self._next_update = 1
        self.transport = httpx.MockTransport(self.handle)

    def say(
        self, text: str | None, *, user: int = ADA, chat: int | None = None, name: str = "Ada", **files: Any
    ) -> None:
        """`files` as the Bot API puts them in a message: `photo`, `voice`, `audio`, `document`, `caption`."""
        message: dict[str, Any] = {"message_id": self._next_update, "date": 1_760_000_000}
        message |= {"chat": {"id": chat or user, "type": "private"}, "from": {"id": user, "first_name": name}}
        message |= files
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

    def file(self, data: bytes, **fields: Any) -> dict[str, Any]:
        """A file the bot may download, as a message describes it."""
        file_id = f"file-{len(self.files)}"
        self.files[file_id] = data
        return {"file_id": file_id, "file_unique_id": file_id, "file_size": len(data), **fields}

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/file/bot"):
            token, path = request.url.path.removeprefix("/file/bot").split("/", 1)
            if token != TOKEN or path.removeprefix("files/") not in self.files:
                return httpx.Response(404)
            return httpx.Response(200, content=self.files[path.removeprefix("files/")])
        token, method = request.url.path.removeprefix("/bot").split("/")
        if token != TOKEN:
            return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})
        if self.failures[method]:
            failure = self.failures[method].popleft()
            if isinstance(failure, Exception):
                raise failure
            return failure
        if method in ("sendVoice", "sendPhoto"):
            fields, file = multipart(request)
            sent = self.voices if method == "sendVoice" else self.photos
            sent.append((fields["chat_id"], file, fields.get("caption")))
            return ok({"message_id": len(sent)})
        payload = json.loads(request.content)
        if method == "getFile":
            known = payload["file_id"] in self.files
            return (
                ok({"file_id": payload["file_id"], "file_path": f"files/{payload['file_id']}"})
                if known
                else error(400, "Bad Request: invalid file_id")
            )
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


def multipart(request: httpx.Request) -> tuple[dict[str, str], bytes]:
    """The text fields of a multipart upload, and its file."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields, file = {}, b""
    for part in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = part.strip(b"\r\n").partition(b"\r\n\r\n")
        if b"filename=" in head:
            file = body
        elif named := re.search(rb'name="([^"]+)"', head):
            fields[named[1].decode()] = body.decode()
    return fields, file


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
    options = {"poll_timeout_s": 1, "retry_delay_s": 0.01} | options
    channel = TelegramChannel("telegram", token=token, transport=api.transport, **options)
    channel.typing_every_s = 0.02  # said again quickly, so that a test sees it repeated
    return channel


@asynccontextmanager
async def serving(
    api: FakeBotApi, assistant: Assistant, **options: Any
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
    assert [m.sender and m.sender.id for m in assistant.messages] == [str(ADA)]
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


async def test_another_instance_polling_is_waited_out_without_leaving_serve(
    api: FakeBotApi, caplog: pytest.LogCaptureFixture
) -> None:
    conflict = error(409, "Conflict: terminated by other getUpdates request")
    api.fail("getUpdates", conflict, conflict)
    with caplog.at_level(logging.WARNING):
        async with serving(api, ScriptedAssistant(echo)) as (_, task):
            api.say("still there?")
            await eventually(lambda: bool(api.sent))
            assert not task.done()
    assert api.sent == [(ADA, "echo: still there?")]
    assert caplog.text.count("409 Conflict") == 2
    assert "Traceback" not in caplog.text


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
        await channel.send(Address("telegram", str(ADA)), "Your task is done.", Medium.WRITTEN, ())
    assert api.sent == [(ADA, "Your task is done.")]


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
            await channel.send(Address("telegram", str(ADA)), "Your task is done.", Medium.WRITTEN, ())
    assert raised.value.transient is transient


async def test_send_to_another_channel_is_a_contract_error(api: FakeBotApi) -> None:
    async with channel_for(api) as channel:
        with pytest.raises(ContractError):
            await channel.send(Address("voice", "kitchen"), "hello", Medium.WRITTEN, ())
    assert api.sent == []


async def test_send_after_close_fails_permanently(api: FakeBotApi) -> None:
    channel = channel_for(api)
    await channel.close()
    with pytest.raises(ProviderError) as raised:
        await channel.send(Address("telegram", str(ADA)), "hello", Medium.WRITTEN, ())
    assert raised.value.transient is False


async def test_only_addresses_of_this_channel_are_reachable(api: FakeBotApi) -> None:
    async with channel_for(api) as channel:
        assert channel.reachable(Address("telegram", str(ADA)), Medium.WRITTEN)
        assert not channel.reachable(Address("family-bot", str(ADA)), Medium.WRITTEN)


async def test_the_plugin_names_the_channel_after_its_configured_instance(tmp_path: Path) -> None:
    channel = plugin.create(
        {"token": TOKEN}, "family-bot", Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    )
    assert isinstance(channel, TelegramChannel)
    assert channel.channel_id == "family-bot"
    assert TOKEN not in repr(plugin.settings.model_validate({"token": TOKEN}))
    await channel.close()


@pytest.mark.parametrize(
    ("configured", "said"), [({}, "channel-apology"), ({"apology": ""}, ""), ({"apology": "Oups."}, "Oups.")]
)
async def test_the_apology_is_the_households_language_unless_configured(
    tmp_path: Path, configured: dict[str, str], said: str
) -> None:
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    channel = plugin.create({"token": TOKEN, **configured}, "bot", services)
    assert isinstance(channel, TelegramChannel) and channel._apology == said
    await channel.close()


@pytest.mark.parametrize(("configured", "seconds"), [({}, None), ({"conversation_ends_after_s": 86400}, 86400.0)])
async def test_a_written_conversation_lasts_hours_unless_configured(
    tmp_path: Path, configured: dict[str, int], seconds: float
) -> None:
    services = Services(data_dir=tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    channel = plugin.create({"token": TOKEN, **configured}, "bot", services)
    assert channel.conversation_ends_after_s == seconds
    await channel.close()
    with pytest.raises(ContractError):
        plugin.create({"token": TOKEN, "conversation_ends_after_s": 0}, "bot", services)


class _LookingUp(Reply):
    """Says it is looking, then waits for its tool (`done`) before giving the result."""

    def __init__(self, done: asyncio.Event) -> None:
        self._done = done

    async def __aiter__(self) -> AsyncIterator[str | MessageEnd]:
        yield "Je regarde où en sont les tests."
        yield MessageEnd()
        await self._done.wait()
        yield "Tout est vert."
        yield MessageEnd()

    async def interrupt(self, heard: str) -> None: ...


class _LookingAssistant(Assistant):
    def __init__(self, done: asyncio.Event) -> None:
        self._done = done

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return PersonId(sender.id)

    def respond(self, message: InboundMessage) -> Reply:
        return _LookingUp(self._done)


async def test_each_message_of_an_answer_is_sent_as_soon_as_it_is_written(api: FakeBotApi) -> None:
    done = asyncio.Event()
    async with serving(api, _LookingAssistant(done)):
        api.say("Les tests ?")
        await eventually(lambda: api.texts(ADA) == ["Je regarde où en sont les tests."])
        typing = len(api.actions)
        await eventually(lambda: len(api.actions) > typing)  # still typing while the tool runs
        done.set()
        await eventually(lambda: len(api.sent) == 2)
    assert api.texts(ADA) == ["Je regarde où en sont les tests.", "Tout est vert."]


async def test_files_reach_the_assistant_downloaded_with_their_caption(api: FakeBotApi) -> None:
    assistant = ScriptedAssistant(lambda message: "vu")
    small, large = api.file(b"small", width=90, height=90), api.file(b"large jpeg", width=1280, height=960)
    async with serving(api, assistant):
        api.say(None, photo=[small, large], caption="la facture")
        api.say(None, voice=api.file(b"opus", mime_type="audio/ogg", duration=3))
        api.say(None, document=api.file(b"png", mime_type="image/png", file_name="plan.png"))
        api.say(None, document=api.file(b"%PDF", mime_type="application/pdf", file_name="devis.pdf"))
        await eventually(lambda: len(assistant.messages) == 4)
    photo, voice, image, pdf = assistant.messages
    assert photo.text == "la facture"
    assert [(a.kind, a.data, a.media_type) for a in photo.attachments] == [
        (AttachmentKind.IMAGE, b"large jpeg", "image/jpeg")
    ], "the largest size of a photo"
    assert [(a.kind, a.data, a.media_type) for a in voice.attachments] == [(AttachmentKind.VOICE, b"opus", "audio/ogg")]
    assert [(a.kind, a.name) for a in image.attachments] == [(AttachmentKind.IMAGE, "plan.png")]
    assert [(a.kind, a.name, a.media_type) for a in pdf.attachments] == [
        (AttachmentKind.FILE, "devis.pdf", "application/pdf")
    ]


async def test_a_voice_message_is_answered_with_one_captioned_with_its_text(api: FakeBotApi) -> None:
    assistant = ScriptedAssistant(lambda message: "Le pain est noté.", speaks=True)
    async with serving(api, assistant):
        api.say(None, voice=api.file(b"opus", mime_type="audio/ogg"))
        await eventually(lambda: bool(api.voices))
        api.say("et écrit ?")
        await eventually(lambda: bool(api.sent))
    assert api.voices == [(str(ADA), OGG + "Le pain est noté.".encode(), "Le pain est noté.")]
    assert api.sent == [(ADA, "Le pain est noté.")], "a typed message is answered in writing"


async def test_a_long_voice_answer_follows_its_recording_in_writing(api: FakeBotApi) -> None:
    long = "Une phrase. " * 120
    assistant = ScriptedAssistant(lambda message: long, speaks=True)
    async with serving(api, assistant):
        api.say(None, voice=api.file(b"opus"))
        await eventually(lambda: bool(api.sent))
    [(_, _, caption)] = api.voices
    assert caption is None, "over Telegram's caption limit"
    assert api.texts(ADA) == [long.strip()]


@pytest.mark.parametrize("text", ["Voilà ton dessin.", "Une phrase. " * 120], ids=["short", "over-the-caption"])
async def test_a_picture_goes_with_its_answer_as_caption_when_it_fits(api: FakeBotApi, text: str) -> None:
    picture = Attachment(kind=AttachmentKind.IMAGE, data=b"png bytes", media_type="image/png")
    assistant = ScriptedAssistant(lambda message: text, pictures=(picture,))
    async with serving(api, assistant):
        api.say("dessine-moi Nestor")
        await eventually(lambda: bool(api.photos))
    fits = len(text) < 1024
    assert api.photos == [(str(ADA), b"png bytes", text.strip() if fits else None)]
    assert api.texts(ADA) == ([] if fits else [text.strip()]), "written first when it is too long for a caption"


async def test_a_file_that_cannot_be_downloaded_is_left_out(api: FakeBotApi) -> None:
    assistant = ScriptedAssistant(
        lambda message: f"{len(message.attachments)} fichier",
    )
    too_big = api.file(b"x") | {"file_size": FILE_LIMIT + 1}
    gone = {"file_id": "missing", "file_unique_id": "missing"}
    async with serving(api, assistant, apology="Oups."):
        api.say(None, document=too_big, caption="regarde")
        api.say(None, voice=gone)
        await eventually(lambda: len(api.sent) == 2)
    assert [m.text for m in assistant.messages] == ["regarde"], "a message left with nothing never reaches it"
    assert api.texts(ADA) == ["0 fichier", "Oups."]


class TelegramPlatform(Platform):
    """The fake Bot API as a messaging platform: Ada writes in her private chat."""

    def __init__(self, api: FakeBotApi, channel: TelegramChannel) -> None:
        self.channel = channel
        self.api = api

    async def send(self, text: str, *attachments: Attachment) -> None:
        files: dict[str, Any] = {"caption": text} if text else {}
        for a in attachments:
            file = self.api.file(a.data, mime_type=a.media_type)
            match a.kind:
                case AttachmentKind.IMAGE:
                    files["photo"] = [file]
                case AttachmentKind.VOICE:
                    files["voice"] = file
                case AttachmentKind.AUDIO:
                    files["audio"] = file
                case AttachmentKind.FILE:
                    files["document"] = file
        self.api.say(None, **files)

    async def answered(self, count: int) -> None:
        await eventually(lambda: len(self.api.sent) + len(self.api.voices) >= count)

    def texts(self) -> list[str]:
        return [text for _, text in self.api.sent]

    def voices(self) -> list[bytes]:
        return [voice for _, voice, _ in self.api.voices]


class TestTelegramMessaging(MessagingChannelContract):
    @asynccontextmanager
    async def serving(self, assistant: Assistant) -> AsyncGenerator[Platform]:
        api = FakeBotApi()
        async with serving(api, assistant) as (channel, _):
            yield TelegramPlatform(api, channel)


async def test_an_answer_whose_picture_cannot_be_sent_still_says_its_words(api: FakeBotApi) -> None:
    picture = Attachment(kind=AttachmentKind.IMAGE, data=b"png bytes", media_type="image/png")
    assistant = ScriptedAssistant(lambda message: "Voilà ton dessin.", pictures=(picture,))
    api.failures["sendPhoto"].append(
        httpx.Response(400, json={"ok": False, "error_code": 400, "description": "Bad Request: file too big"})
    )
    async with serving(api, assistant):
        api.say("dessine-moi Nestor")
        await eventually(lambda: bool(api.sent))
    assert api.texts(ADA) == ["Voilà ton dessin."]
