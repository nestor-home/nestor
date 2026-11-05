"""Who is speaking, told while the speech is still being transcribed.

`VoiceListener` sits right after the transport input. It keeps the last seconds of the microphone and follows the
speech detector (its frames come back upstream): each time someone stops speaking, it hands the turn's speech so
far to the assistant to recognise the voice. By the time the transcription is final and the turn starts, the
answer is usually there; the bridge waits for it a little at most, then goes on without.
"""

import asyncio
import contextlib
import time
from collections import deque

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from nestor.modules.channels import Assistant
from nestor.modules.identity import Heard

KEEP_S = 30.0  # of microphone audio: longer than any turn worth recognising
PAD_S = 0.15  # around what the detector found: the first and last syllables are soft


class VoiceListener(FrameProcessor):
    def __init__(self, assistant: Assistant, *, keep_s: float = KEEP_S, pad_s: float = PAD_S) -> None:
        super().__init__()
        self._assistant = assistant
        self._keep_s, self._pad_s = keep_s, pad_s
        self._audio: deque[tuple[float, bytes]] = deque()  # (when each chunk ended, wall clock), oldest first
        self._open: float | None = None  # when the speech being heard started
        self._spans: list[tuple[float, float]] = []  # the turn's speech so far
        self._hearing: asyncio.Task[Heard | None] | None = None

    async def heard(self, wait_s: float) -> Heard | None:
        """What the voice of the turn that just ended tells, waiting `wait_s` at most; then a new turn starts."""
        hearing, self._hearing, self._spans = self._hearing, None, []
        if hearing is None:
            return None
        try:
            return await asyncio.wait_for(hearing, wait_s)
        except TimeoutError:
            return None
        except Exception:  # recognition is a bonus: the turn goes on without it
            return None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self._keep(frame.audio)
        elif isinstance(frame, VADUserStartedSpeakingFrame) and direction is FrameDirection.UPSTREAM:
            self._open = frame.timestamp - frame.start_secs - self._pad_s
        elif isinstance(frame, VADUserStoppedSpeakingFrame) and direction is FrameDirection.UPSTREAM:
            if self._open is not None:
                self._spans.append((self._open, frame.timestamp - frame.stop_secs + self._pad_s))
                self._open = None
                self._listen()
        elif isinstance(frame, UserStartedSpeakingFrame) and direction is FrameDirection.UPSTREAM:
            self._spans.clear()  # a turn starts: what was heard before (an acknowledgement) is not part of it
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        if self._hearing is not None:
            self._hearing.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._hearing
        await super().cleanup()

    def _keep(self, audio: bytes) -> None:
        now = time.time()
        self._audio.append((now, audio))
        while self._audio and self._audio[0][0] < now - self._keep_s:
            self._audio.popleft()

    def _listen(self) -> None:
        """Recognise the turn's speech so far, replacing a recognition of less of it."""
        if self._hearing is not None:
            self._hearing.cancel()
        speech = b"".join(audio for ended, audio in self._audio if any(a <= ended <= b + 0.1 for a, b in self._spans))
        self._hearing = self.create_task(self._assistant.hear(speech)) if speech else None
