"""Speech doubles with controlled latency, and an assistant whose answers take time to come.

Only STT and TTS are simulated: VAD, Smart Turn, aggregation, interruptions and the transport
buffers are Pipecat's real components.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator

import numpy as np
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.time import time_now_iso8601

from nestor.adapters.channels.voice import Speech
from nestor.adapters.channels.voice.eager import EagerSentenceFlush
from nestor.core import PersonId
from nestor.modules.channels import Address, Assistant, InboundMessage, Reply, Sender

from .replay import ReplayTransport, ScenarioClock


class ScriptedSTT(STTService):
    """A streaming STT that "hears" the script's words when they are spoken.

    Like Scribe with a manual commit: partial transcriptions as speech goes (`latency_s` late), then
    a final one after the VAD detects the end of speech. Words are spread evenly over each span.
    `fail_at_s` makes the provider fail once at that time and transcribe nothing.
    """

    def __init__(
        self,
        transport: ReplayTransport,
        texts: list[str],
        *,
        latency_s: float = 0.15,
        spans: list[tuple[float, float]] | None = None,
        fail_at_s: float | None = None,
    ) -> None:
        super().__init__(settings=STTSettings(model=None, language=None))
        self._clock = transport.clock
        self._words: list[tuple[float, str]] = []
        spans = spans or [(u.at_s, u.end_s) for u in transport.script]
        for (start, end), text in zip(spans, texts, strict=True):
            words = text.replace("...", " ").split()
            step = (end - start) / len(words)
            self._words += [(start + (i + 0.5) * step, w) for i, w in enumerate(words)]
        self._latency_s = latency_s
        self._fail_at_s = fail_at_s
        self._pending: list[str] = []

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if self._fail_at_s is not None:
            if self._clock.now() >= self._fail_at_s:
                self._fail_at_s = float("inf")
                await self.push_error("transcription unavailable")
            return
        if heard := self._take_words_until(self._clock.now() - self._latency_s):
            self._pending += heard
            yield InterimTranscriptionFrame(" ".join(self._pending), "user", time_now_iso8601())

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStoppedSpeakingFrame) and self._fail_at_s is None:
            self.create_task(self._finalize())

    async def _finalize(self) -> None:
        await asyncio.sleep(self._latency_s)
        self._pending += self._take_words_until(self._clock.now())
        text, self._pending = " ".join(self._pending), []
        if text:
            await self.push_frame(TranscriptionFrame(text, "user", time_now_iso8601(), finalized=True))

    def _take_words_until(self, t: float) -> list[str]:
        heard = [w for at, w in self._words if at <= t]
        self._words = [(at, w) for at, w in self._words if at > t]
        return heard


class ToneTTS(EagerSentenceFlush, TTSService):
    """A fake synthesis: an audible tone whose length follows the text; `down` refuses everything."""

    def __init__(
        self, clock: ScenarioClock, *, ttfb_s: float = 0.1, secs_per_char: float = 0.06, down: bool = False
    ) -> None:
        super().__init__(
            sample_rate=24000, push_stop_frames=True, settings=TTSSettings(model=None, voice=None, language=None)
        )
        self._clock = clock
        self._ttfb_s = ttfb_s
        self._secs_per_char = secs_per_char
        self._down = down
        self.spoken: list[tuple[float, str]] = []  # (when it was asked, text)

    @property
    def texts(self) -> list[str]:
        return [text for _, text in self.spoken]

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        if self._down:
            await self.push_error("synthesis unavailable", force_treat_as_permanent=True)
            return
        self.spoken.append((self._clock.now(), text))
        await self.start_ttfb_metrics()
        await asyncio.sleep(self._ttfb_s)
        await self.stop_ttfb_metrics()
        rate = self.sample_rate
        samples = int(len(text) * self._secs_per_char * rate)
        tone = (8000 * np.sin(2 * np.pi * 220 * np.arange(samples) / rate)).astype(np.int16)
        for i in range(0, samples, rate // 10):
            yield TTSAudioRawFrame(tone[i : i + rate // 10].tobytes(), rate, 1, context_id=context_id)


class FakeSpeech(Speech):
    def __init__(self, stt: STTService, tts: TTSService) -> None:
        self._stt, self._tts = stt, tts

    def stt(self) -> STTService:
        return self._stt

    def tts(self) -> TTSService:
        return self._tts


class TimedReply(Reply):
    """Streams `text` word by word after `ttft_s`, like a model; remembers what it was told was heard."""

    def __init__(self, text: str, *, ttft_s: float, token_interval_s: float, fail: bool) -> None:
        self.text = text
        self._ttft_s, self._token_interval_s, self._fail = ttft_s, token_interval_s, fail
        self.heard: str | None = None

    async def __aiter__(self) -> AsyncIterator[str]:
        await asyncio.sleep(self._ttft_s)
        if self._fail:
            raise RuntimeError("the agent crashed")
        for i, word in enumerate(self.text.split(" ")):
            if self.heard is not None:
                return
            yield word if i == 0 else f" {word}"
            await asyncio.sleep(self._token_interval_s)

    async def interrupt(self, heard: str) -> None:
        self.heard = heard


class FakeAssistant(Assistant):
    """Answers with `answers` in order; every sender is a household member except `strangers`."""

    def __init__(
        self,
        answers: list[str],
        *,
        clock: ScenarioClock | None = None,
        ttft_s: float = 0.3,
        token_interval_s: float = 0.02,
        strangers: frozenset[str] = frozenset(),
        fail: bool = False,
    ) -> None:
        self._answers = list(answers)
        self._clock = clock
        self._ttft_s, self._token_interval_s = ttft_s, token_interval_s
        self._strangers = strangers
        self._fail = fail
        self.messages: list[InboundMessage] = []
        self.arrivals: list[float] = []
        self.replies: list[TimedReply] = []

    def identify(self, address: Address, sender: Sender) -> PersonId | None:
        return None if sender.id in self._strangers else PersonId(sender.id)

    def respond(self, message: InboundMessage) -> TimedReply:
        self.messages.append(message)
        if self._clock:
            self.arrivals.append(self._clock.now())
        text = self._answers.pop(0) if self._answers else "D'accord."
        reply = TimedReply(text, ttft_s=self._ttft_s, token_interval_s=self._token_interval_s, fail=self._fail)
        self.replies.append(reply)
        return reply
