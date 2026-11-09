"""Speech models as the voice pipeline runs them: Pipecat services, a fresh one for each session.

Not a provider: what every transcription or speech provider gives the satellites' voice, which runs on Pipecat. A
provider derives from `PipecatTranscription` or `PipecatSpeech` and wraps the Pipecat service for its API, so adding
one is a few lines. Importing this package imports no Pipecat: building a service does (the `voice` extra).
"""

from abc import abstractmethod
from typing import TYPE_CHECKING

from nestor.modules.channels import SpeechModel, TranscriptionModel

if TYPE_CHECKING:
    from pipecat.services.stt_service import STTService
    from pipecat.services.tts_service import TTSService

SAMPLE_RATE = 16000  # the audio a transcription service hears


class PipecatTranscription(TranscriptionModel):
    """A transcription model the voice pipeline runs."""

    @abstractmethod
    def stt(self) -> "STTService":
        """A new transcription service, for one session, hearing `SAMPLE_RATE` audio. The pipeline's own voice
        activity detection decides when a turn ends: a service that can should wait for it (a manual commit)."""


class PipecatSpeech(SpeechModel):
    """A speech model the voice pipeline runs."""

    @abstractmethod
    def tts(self) -> "TTSService":
        """A new synthesis service, for one session. It should mix in `eager.EagerSentenceFlush`, or the first
        sentence waits for the next."""


__all__ = ["SAMPLE_RATE", "PipecatSpeech", "PipecatTranscription"]
