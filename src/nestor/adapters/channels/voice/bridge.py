"""Where the voice pipeline meets the assistant.

The assistant is not a Pipecat service: it lives behind the `Assistant` port. `AssistantBridge`
takes its place in the pipeline. For each user turn it streams the assistant's reply as LLM text
frames, so that the synthesis and the eager sentence flush work as with a language model; when the
user cuts in, it tells the reply what was actually heard, as reported by `PlayedText` behind the
speaker.
"""

import asyncio
import logging
from dataclasses import dataclass

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSTextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor, FrameProcessorSetup

from nestor.core import ProviderError
from nestor.modules.channels import Address, Assistant, InboundMessage, Reply, Sender

logger = logging.getLogger(__name__)

PROVIDER = "voice"
_POLL_S = 0.05


class PlayedText(FrameProcessor):
    """Placed after the transport output, where text arrives only once its audio has been played.

    It follows one response at a time (from its start frame): the words played so far, and whether
    its end has been played too.
    """

    def __init__(self) -> None:
        super().__init__()
        self._response: int | None = None
        self._words: list[str] = []
        self._finished: int | None = None

    def heard(self, response: int) -> str:
        """What the user heard of `response` (its start frame's id)."""
        return " ".join(self._words) if response == self._response else ""

    def finished(self, response: int) -> bool:
        """Whether `response` was played to the end."""
        return response == self._finished

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMFullResponseStartFrame):
            self._response, self._words = frame.id, []
        elif isinstance(frame, TTSTextFrame) and (word := frame.text.strip()):
            self._words.append(word)
        elif isinstance(frame, LLMFullResponseEndFrame):
            self._finished = self._response
        await self.push_frame(frame, direction)


@dataclass(slots=True)
class _Answer:
    """The reply being spoken: `start` identifies it on its way to the speaker."""

    reply: Reply
    start: LLMFullResponseStartFrame
    stream: asyncio.Task[None]


class AssistantBridge(FrameProcessor):
    """Turns each user turn into a message for the assistant and streams its reply to the synthesis.

    - Strangers (`identify` returns `None`) are not answered.
    - One reply at a time: a new turn or the user cutting in drops the current one, and a reply cut
      before its end is interrupted with the text played so far.
    - `announce` speaks an unprompted message once nobody has spoken for `quiet_s`.
    """

    def __init__(
        self,
        assistant: Assistant,
        *,
        address: Address,
        sender: Sender,
        played: PlayedText,
        quiet_s: float = 0.5,
    ) -> None:
        super().__init__()
        self._assistant = assistant
        self._address, self._sender = address, sender
        self._played = played
        self._quiet_s = quiet_s
        self._answer: _Answer | None = None
        self._user_speaking = False
        self._bot_speaking = False
        self._told_stranger = False
        self._speaking = asyncio.Lock()  # a response's frames are never interleaved with another's
        self._announcements: asyncio.Queue[tuple[str, asyncio.Future[None]]] = asyncio.Queue()

    async def announce(self, text: str) -> None:
        """Speak `text` when nobody is speaking; returns once it is on its way to the synthesis."""
        spoken = asyncio.get_running_loop().create_future()
        self._announcements.put_nowait((text, spoken))
        await spoken

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            if not frame.speculation:
                await self._on_turn(frame.context)
            return
        if isinstance(frame, InterruptionFrame):
            answer = await self._drop()  # before the interruption goes on, so no text follows it
            await self.push_frame(frame, direction)
            await self._tell_heard(answer)
            return
        elif isinstance(frame, UserStartedSpeakingFrame | UserStoppedSpeakingFrame):
            self._user_speaking = isinstance(frame, UserStartedSpeakingFrame)
        elif isinstance(frame, BotStartedSpeakingFrame | BotStoppedSpeakingFrame):
            self._bot_speaking = isinstance(frame, BotStartedSpeakingFrame)
        await self.push_frame(frame, direction)

    async def setup(self, setup: FrameProcessorSetup) -> None:
        await super().setup(setup)
        self._announcer = self.create_task(self._announce_when_quiet())

    async def cleanup(self) -> None:
        await self.cancel_task(self._announcer)
        while not self._announcements.empty():
            _abandon(self._announcements.get_nowait()[1])
        await self._cut()
        await super().cleanup()

    async def _on_turn(self, context: LLMContext) -> None:
        text = _last_user_text(context)
        context.set_messages([])  # the conversation lives in the assistant, not in the pipeline
        if not text:
            return
        if self._assistant.identify(self._address, self._sender) is None:
            if not self._told_stranger:
                logger.info("voice: %s is not a known speaker in %s, ignoring speech", self._sender.id, self._address)
                self._told_stranger = True
            return
        await self._cut()
        reply = self._assistant.respond(InboundMessage(address=self._address, sender=self._sender, text=text))
        start = LLMFullResponseStartFrame()
        self._answer = _Answer(reply, start, self.create_task(self._stream(reply, start)))

    async def _stream(self, reply: Reply, start: LLMFullResponseStartFrame) -> None:
        async with self._speaking:
            await self.push_frame(start)
            try:
                async for chunk in reply:
                    await self.push_frame(LLMTextFrame(chunk))
            except Exception:
                logger.exception("voice: the assistant failed to answer in %s", self._address)
            await self.push_frame(LLMFullResponseEndFrame())

    async def _cut(self) -> None:
        await self._tell_heard(await self._drop())

    async def _drop(self) -> _Answer | None:
        """Stop streaming the current reply."""
        answer, self._answer = self._answer, None
        if answer is not None:
            await self.cancel_task(answer.stream)
        return answer

    async def _tell_heard(self, answer: _Answer | None) -> None:
        """A reply not played to its end learns what the user heard of it."""
        if answer is None or self._played.finished(answer.start.id):
            return
        heard = self._played.heard(answer.start.id)
        try:
            await answer.reply.interrupt(heard)
        except Exception:
            logger.exception("voice: the assistant failed to take an interruption in %s", self._address)

    def _quiet(self) -> bool:
        answering = self._answer is not None and not self._played.finished(self._answer.start.id)
        return not (self._user_speaking or self._bot_speaking or answering)

    async def _announce_when_quiet(self) -> None:
        while True:
            text, spoken = await self._announcements.get()
            try:
                await self._until_quiet()
                if spoken.done():
                    continue  # the sender gave up waiting: too late to say it
                async with self._speaking:  # free unless a reply is streaming, which is not quiet
                    await self.push_frame(LLMFullResponseStartFrame())
                    await self.push_frame(LLMTextFrame(text))
                    await self.push_frame(LLMFullResponseEndFrame())
                spoken.set_result(None)
            finally:
                _abandon(spoken)

    async def _until_quiet(self) -> None:
        quiet_for = 0.0
        while quiet_for < self._quiet_s:
            await asyncio.sleep(_POLL_S)
            quiet_for = quiet_for + _POLL_S if self._quiet() else 0.0


def _abandon(spoken: asyncio.Future[None]) -> None:
    if not spoken.done():
        spoken.set_exception(ProviderError(PROVIDER, "the voice session ended", transient=True))


def _last_user_text(context: LLMContext) -> str:
    """The user aggregator writes the turn as the last user message: plain text, or text parts."""
    for message in reversed(context.get_messages()):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        parts = content if isinstance(content, list) else []
        return " ".join(
            str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    return ""
