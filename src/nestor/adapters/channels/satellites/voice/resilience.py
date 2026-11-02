"""The assistant never goes silent without an explanation when a speech provider fails.

Model failures are the agent's business (it speaks its own fallback); the channel covers its own
providers: on a transcription error it says a phrase, and when the synthesis itself is down it
plays a clip prerecorded in the same voice instead.
"""

import logging
import wave
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    ErrorFrame,
    Frame,
    OutputAudioRawFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class Outage(StrEnum):
    """Which speech provider failed; also the clip's file name (`stt.wav`, `tts.wav`)."""

    STT = "stt"
    TTS = "tts"


def load_clips(folder: Path | None) -> dict[Outage, OutputAudioRawFrame]:
    """The prerecorded clips found in `folder` (16-bit mono WAV); a missing one is logged."""
    clips: dict[Outage, OutputAudioRawFrame] = {}
    for outage in Outage:
        path = folder / f"{outage}.wav" if folder else None
        if path is None or not path.exists():
            logger.warning("voice: no fallback clip for a %s outage%s", outage, f" ({path})" if path else "")
            continue
        with wave.open(str(path), "rb") as clip:
            if clip.getsampwidth() != 2:
                raise ValueError(f"{path}: expected 16-bit PCM")
            pcm = clip.readframes(clip.getnframes())
            clips[outage] = OutputAudioRawFrame(pcm, clip.getframerate(), clip.getnchannels())
    return clips


class Injector(FrameProcessor):
    """An injection point: passes everything along; `inject` pushes a frame downstream from here.

    Injecting at the head of the pipeline would not work: a processor busy with a turn handles its
    frames one by one, and the fallback would wait behind it.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

    async def inject(self, frame: Frame) -> None:
        await self.push_frame(frame)


class SpeechFallbacks(BaseObserver):
    """Watches provider errors and answers at most once per user turn.

    `say` sits before the synthesis (a phrase), `play` after it (a clip). Once the synthesis failed,
    later fallbacks use clips too.
    """

    def __init__(
        self,
        say: Injector,
        play: Injector,
        *,
        stt_phrase: str,
        clips: Mapping[Outage, OutputAudioRawFrame],
    ) -> None:
        super().__init__()
        self._say, self._play = say, play
        self._stt_phrase = stt_phrase
        self._clips = dict(clips)
        self._tts_down = False
        self._answered_this_turn = False

    async def on_push_frame(self, data: FramePushed) -> None:
        if not data.first_push:
            return
        frame = data.frame
        if isinstance(frame, ErrorFrame):
            if isinstance(frame.processor, TTSService):
                self._tts_down = True
                await self._fall_back(Outage.TTS)
            elif isinstance(frame.processor, STTService):
                await self._fall_back(Outage.STT)
        elif isinstance(frame, UserStartedSpeakingFrame):
            self._answered_this_turn = False
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._answered_this_turn = True

    async def _fall_back(self, outage: Outage) -> None:
        if self._answered_this_turn:
            return
        self._answered_this_turn = True
        if not self._tts_down:
            logger.warning("voice: %s outage, saying %r", outage, self._stt_phrase)
            await self._say.inject(TTSSpeakFrame(self._stt_phrase, append_to_context=False))
        elif clip := self._clips.get(outage):
            logger.warning("voice: %s outage with the synthesis down, playing the prerecorded clip", outage)
            await self._play.inject(clip)
        else:
            logger.error("voice: %s outage with the synthesis down and no clip: the assistant stays silent", outage)
