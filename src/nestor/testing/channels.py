"""Doubles for the channels module (an in-memory channel, a scripted assistant, transcription and speech models),
and the contracts of the transcription and speech models."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable

from nestor.core import ContractError, PersonId, ProviderError
from nestor.modules.channels import (
    Address,
    Assistant,
    Attachment,
    AttachmentKind,
    Channel,
    InboundMessage,
    Medium,
    MessageEnd,
    Reply,
    Sender,
    SpeechModel,
    TranscriptionModel,
)
from nestor.modules.identity import Heard

OGG = b"OggS"  # how an OGG recording starts


class ScriptedReply(Reply):
    """Streams `text` word by word, as one message, with `attachments`; stops as soon as it is interrupted."""

    def __init__(self, text: str, *, word_delay_s: float = 0.0, attachments: tuple[Attachment, ...] = ()) -> None:
        self._words = text.split()
        self._word_delay_s = word_delay_s
        self._attachments = attachments
        self.heard: str | None = None

    async def __aiter__(self) -> AsyncIterator[str | MessageEnd]:
        for i, word in enumerate(self._words):
            if self.heard is not None:
                return
            await asyncio.sleep(self._word_delay_s)
            yield word if i == 0 else f" {word}"
        yield MessageEnd(attachments=self._attachments)

    async def interrupt(self, heard: str) -> None:
        self.heard = heard


class ScriptedAssistant(Assistant):
    """Answers with `answer(message)` and keeps every message and reply for inspection.

    Every account is a household member unless `strangers` lists them; `voice`, when given, is what every speech
    handed to `hear` tells.
    """

    def __init__(
        self,
        answer: Callable[[InboundMessage], str],
        *,
        word_delay_s: float = 0.0,
        strangers: frozenset[str] = frozenset(),
        voice: Heard | None = None,
        speaks: bool = False,
        pictures: tuple[Attachment, ...] = (),
    ) -> None:
        """`speaks`: it answers a voice message with one, its text recorded as `OGG` followed by it. `pictures` go
        with every answer."""
        self._answer = answer
        self._pictures = pictures
        self._voice = voice
        self._speaks = speaks
        self.heard: list[bytes] = []
        self._strangers = strangers
        self._word_delay_s = word_delay_s
        self.messages: list[InboundMessage] = []
        self.replies: list[ScriptedReply] = []

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return None if sender.id in self._strangers else PersonId(sender.id)

    @property
    def voice_wait_s(self) -> float | None:
        return 0.5 if self._voice else None

    async def hear(self, audio: bytes) -> Heard | None:
        self.heard.append(audio)
        return self._voice

    def respond(self, message: InboundMessage) -> ScriptedReply:
        self.messages.append(message)
        text = self._answer(message)
        voiced = self._speaks and any(a.kind is AttachmentKind.VOICE for a in message.attachments)
        voice = Attachment(kind=AttachmentKind.VOICE, data=OGG + text.encode(), media_type="audio/ogg")
        attachments = ((voice,) if voiced else ()) + self._pictures
        reply = ScriptedReply(text, word_delay_s=self._word_delay_s, attachments=attachments)
        self.replies.append(reply)
        return reply


class InMemoryChannel(Channel):
    """A text channel driven by the test: `ask` plays a user message and returns the messages of the
    answer, or `None` when the assistant does not know the sender. A spoken one is heard in `room`."""

    name = "in-memory"
    room: str | None = None

    def __init__(self, channel_id: str = "memory") -> None:
        super().__init__(channel_id)
        self._inbox: asyncio.Queue[tuple[InboundMessage, asyncio.Future[tuple[str, ...] | None]] | None] = (
            asyncio.Queue()
        )
        self.sent: list[tuple[Address, str]] = []
        self.files: list[tuple[Attachment, ...]] = []  # what went with each of `sent`

    async def serve(self, assistant: Assistant) -> None:
        while (item := await self._inbox.get()) is not None:
            message, answered = item
            if message.sender is not None and assistant.identify(message.address, message.sender) is None:
                answered.set_result(None)
                continue
            try:
                answered.set_result(await assistant.respond(message).collect())
            except Exception as error:
                answered.set_exception(error)

    async def ask(self, text: str, *, sender: str = "user", conversation: str = "main") -> tuple[str, ...] | None:
        message = InboundMessage(address=Address(self.channel_id, conversation), sender=Sender(sender), text=text)
        answered: asyncio.Future[tuple[str, ...] | None] = asyncio.get_running_loop().create_future()
        await self._inbox.put((message, answered))
        return await answered

    @property
    def rooms(self) -> frozenset[str]:
        return frozenset({self.room}) if self.room else frozenset()

    async def send(self, to: Address, text: str, medium: Medium, attachments: tuple[Attachment, ...]) -> None:
        if to.channel != self.channel_id or medium not in self.media:
            raise ContractError(f"{to} is not on channel {self.channel_id!r} {medium}")
        self.sent.append((to, text))
        self.files.append(attachments)

    async def close(self) -> None:
        self._inbox.put_nowait(None)


class ScriptedTranscription(TranscriptionModel):
    """Hears in each recording its bytes, as text; `failing` raises `ProviderError` instead."""

    name = "scripted"

    def __init__(self, *, failing: bool = False) -> None:
        self.failing = failing

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        if self.failing:
            raise ProviderError(self.name, "transcription unavailable", transient=True)
        return audio.decode().strip()


class ScriptedSpeech(SpeechModel):
    """Records `text` as `OGG` followed by it; `failing` raises `ProviderError` instead."""

    name = "scripted"

    def __init__(self, *, failing: bool = False) -> None:
        self.failing = failing

    async def synthesize(self, text: str) -> bytes:
        if self.failing:
            raise ProviderError(self.name, "speech unavailable", transient=True)
        return OGG + text.encode()


class TranscriptionModelContract:
    """Behaviour every `TranscriptionModel` adapter must show for recordings. Mix into a `Test…` class and implement
    `model()`, `recording()` and `unavailable_model()`."""

    def model(self) -> TranscriptionModel:
        raise NotImplementedError

    def recording(self) -> tuple[bytes, str, str]:
        """A recording, its media type, and a word that is said in it."""
        raise NotImplementedError

    def unavailable_model(self) -> TranscriptionModel:
        """The same adapter when its provider fails (bad key, unreachable endpoint…)."""
        raise NotImplementedError

    async def test_a_recording_reads_as_what_is_said_in_it(self) -> None:
        audio, media_type, word = self.recording()
        async with self.model() as model:
            text = await model.transcribe(audio, media_type)
        assert word.lower() in text.lower()
        assert text == text.strip()

    async def test_provider_failure_is_a_provider_error(self) -> None:
        audio, media_type, _ = self.recording()
        async with self.unavailable_model() as model:
            try:
                await model.transcribe(audio, media_type)
            except ProviderError:
                return
        raise AssertionError("no ProviderError raised by an unavailable provider")


class SpeechModelContract:
    """Behaviour every `SpeechModel` adapter must show for recordings. Mix into a `Test…` class and implement
    `model()` and `unavailable_model()`."""

    def model(self) -> SpeechModel:
        raise NotImplementedError

    def unavailable_model(self) -> SpeechModel:
        raise NotImplementedError

    async def test_text_is_recorded_as_ogg(self) -> None:
        async with self.model() as model:
            audio = await model.synthesize("Bonjour, c'est un essai.")
        assert audio.startswith(OGG), "not an OGG recording, which messaging apps play as a voice message"

    async def test_provider_failure_is_a_provider_error(self) -> None:
        async with self.unavailable_model() as model:
            try:
                await model.synthesize("Bonjour.")
            except ProviderError:
                return
        raise AssertionError("no ProviderError raised by an unavailable provider")


class MessagingChannelContract:
    """Behaviour every messaging channel (Telegram, and those to come) must show with files. Mix into a `Test…` class
    and implement `serving(assistant)`: an async context that serves the channel against a stand-in for its
    platform, and yields a `Platform` driving that stand-in."""

    def serving(self, assistant: Assistant) -> "contextlib.AbstractAsyncContextManager[Platform]":
        raise NotImplementedError

    async def test_a_file_reaches_the_assistant_downloaded_with_its_kind(self) -> None:
        assistant = ScriptedAssistant(lambda message: "vu")
        photo = Attachment(kind=AttachmentKind.IMAGE, data=b"jpeg", media_type="image/jpeg")
        async with self.serving(assistant) as platform:
            await platform.send("la facture", photo)
            await platform.answered(1)
        [message] = assistant.messages
        assert message.text == "la facture"
        assert [(a.kind, a.data, a.media_type) for a in message.attachments] == [
            (photo.kind, photo.data, photo.media_type)
        ]

    async def test_a_voice_message_is_answered_with_one_when_the_assistant_has_a_voice(self) -> None:
        note = Attachment(kind=AttachmentKind.VOICE, data=b"opus", media_type="audio/ogg")
        for speaks in (True, False):
            assistant = ScriptedAssistant(lambda message: "Noté.", speaks=speaks)
            async with self.serving(assistant) as platform:
                await platform.send("", note)
                await platform.answered(1)
                voices, texts = platform.voices(), platform.texts()
            if speaks and AttachmentKind.VOICE in platform.channel.sends:
                assert voices == [OGG + b"Not\xc3\xa9."], "the answer, recorded"
            else:
                assert (voices, texts) == ([], ["Noté."]), "without a voice to send, the answer is written"


class Platform:
    """The stand-in for a messaging platform a `MessagingChannelContract` drives: someone of the household writes,
    and what the bot sent is read back. `channel` is the channel it serves."""

    channel: Channel

    async def send(self, text: str, *attachments: Attachment) -> None:
        raise NotImplementedError

    async def answered(self, count: int) -> None:
        """Wait until the bot sent `count` answers (texts and voice messages)."""
        raise NotImplementedError

    def texts(self) -> list[str]:
        raise NotImplementedError

    def voices(self) -> list[bytes]:
        raise NotImplementedError
