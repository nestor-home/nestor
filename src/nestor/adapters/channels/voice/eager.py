"""Speak the first sentence as soon as it is complete.

Pipecat's sentence aggregator waits for the next character to confirm a sentence end ("Dr." is not
one). When the assistant says "Je regarde ça." and then calls a tool, no text follows for a while:
the sentence stayed held back until the end of the stream (about 0.5 s measured). The watcher,
right after the assistant's text, notices a stream gone quiet after a sentence end and asks the
synthesis to release the pending sentence.
"""

import asyncio
import re

from pipecat.frames.frames import DataFrame, Frame, LLMFullResponseEndFrame, LLMTextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.tts_service import TTSService

_SENTENCE_END = re.compile(r"[.!?…]\s*$")


class SentenceFlushFrame(DataFrame):
    """Asks the synthesis to speak its pending text (ordered with the assistant's text)."""


class ResponseWatcher(FrameProcessor):
    """Pushes a `SentenceFlushFrame` when the text stream stays quiet `stall_s` after a sentence end."""

    def __init__(self, *, stall_s: float = 0.15) -> None:
        super().__init__()
        self._stall_s = stall_s
        self._timer: asyncio.Task[None] | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            await self._cancel_timer()
            if _SENTENCE_END.search(frame.text):
                self._timer = self.create_task(self._flush_if_stalled())
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._cancel_timer()
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        await self._cancel_timer()
        await super().cleanup()

    async def _flush_if_stalled(self) -> None:
        await asyncio.sleep(self._stall_s)
        self._timer = None
        await self.push_frame(SentenceFlushFrame())

    async def _cancel_timer(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None:
            await self.cancel_task(timer)


class EagerSentenceFlush(TTSService):
    """Synthesis mixin that honours `SentenceFlushFrame`: `class MyTTS(EagerSentenceFlush, VendorTTS)`.

    It uses `TTSService`'s internal aggregator (Pipecat 1.14.0, pinned); the channel's tests detect a
    break.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, SentenceFlushFrame):
            pending = await self._text_aggregator.flush()
            if pending and pending.text.strip():
                await self.stop_text_aggregation_metrics()
                await self._handle_aggregated_text(self._aggregated_text_frame(pending))
            return
        await super().process_frame(frame, direction)
