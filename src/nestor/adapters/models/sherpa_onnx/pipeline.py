"""The satellites' voice hearing through a sherpa-onnx model: Pipecat's segmented service, one turn at a time.
Imports Pipecat: only the voice pipeline loads it."""

from array import array
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601

from nestor.adapters.models.pipecat import SAMPLE_RATE
from nestor.core import ProviderError

if TYPE_CHECKING:
    from nestor.adapters.models.sherpa_onnx.transcription import SherpaOnnxTranscription


class SherpaSegmentedSTT(SegmentedSTTService):
    """Hears each turn the voice activity detection cut, as raw 16-bit PCM at `SAMPLE_RATE`."""

    def __init__(self, model: "SherpaOnnxTranscription") -> None:
        super().__init__(sample_rate=SAMPLE_RATE)
        self._model = model

    @property
    def wants_wav_segments(self) -> bool:
        return False

    @property
    def segment_sample_rate(self) -> int:
        return SAMPLE_RATE

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None]:
        pcm = array("h")
        pcm.frombytes(audio[: len(audio) - len(audio) % 2])
        try:
            text = await self._model.hear([s / 32768.0 for s in pcm])
        except ProviderError as error:
            yield ErrorFrame(str(error))
            return
        if text:
            yield TranscriptionFrame(text, self._user_id, time_now_iso8601())
