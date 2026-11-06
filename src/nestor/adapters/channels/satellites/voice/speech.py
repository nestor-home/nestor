"""What a voice session hears and speaks through: fresh Pipecat services for each session."""

from abc import ABC, abstractmethod

from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService

from nestor.adapters.models.pipecat import PipecatSpeech, PipecatTranscription


class Speech(ABC):
    """Builds fresh speech services for each voice session."""

    @abstractmethod
    def stt(self) -> STTService: ...

    @abstractmethod
    def tts(self) -> TTSService: ...


class ModelSpeech(Speech):
    """The channel's transcription and speech models, together."""

    def __init__(self, transcription: PipecatTranscription, speech: PipecatSpeech) -> None:
        self.transcription, self.speech = transcription, speech

    def stt(self) -> STTService:
        return self.transcription.stt()

    def tts(self) -> TTSService:
        return self.speech.tts()
