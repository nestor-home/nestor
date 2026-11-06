"""Speech as the voice pipeline runs it: what transcribes the user and what gives the assistant its voice.

Both are models of `models` (`transcription` and `speech`), chosen by the household. A model the voice channel
can run builds fresh Pipecat services for each session. Retained on measurements (voice proof of concept):
ElevenLabs Scribe v2 Realtime with a manual commit (the local VAD and Smart Turn decide when the turn ends), and
ElevenLabs v4 Turbo, which is only served over WebSocket by the Text-to-Dialogue endpoint (the text-to-speech
WebSocket refuses it).
"""

from abc import ABC, abstractmethod

from pipecat.services.elevenlabs.dialogue.tts import ElevenLabsDialogueTTSService
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language

from nestor.adapters.channels.satellites.voice.eager import EagerSentenceFlush
from nestor.modules.channels import Synthesizer, Transcriber

IN_SAMPLE_RATE = 16000


class PipecatTranscriber(Transcriber):
    """A transcription model the voice pipeline runs."""

    @abstractmethod
    def stt(self) -> STTService:
        """A new transcription service, for one session."""


class PipecatSynthesizer(Synthesizer):
    """A speech model the voice pipeline runs."""

    @abstractmethod
    def tts(self) -> TTSService:
        """A new synthesis service, for one session: it should mix in `EagerSentenceFlush`, or the first sentence
        waits for the next."""


class Speech(ABC):
    """Builds fresh speech services for each voice session."""

    @abstractmethod
    def stt(self) -> STTService: ...

    @abstractmethod
    def tts(self) -> TTSService: ...


class ModelSpeech(Speech):
    """The channel's transcription and speech models, together."""

    def __init__(self, transcriber: PipecatTranscriber, synthesizer: PipecatSynthesizer) -> None:
        self.transcriber, self.synthesizer = transcriber, synthesizer

    def stt(self) -> STTService:
        return self.transcriber.stt()

    def tts(self) -> TTSService:
        return self.synthesizer.tts()


class ElevenLabsTranscriber(PipecatTranscriber):
    brand = "elevenlabs"

    def __init__(self, *, api_key: str, model: str, language: str, name: str) -> None:
        self.name = name
        self._api_key, self._model, self._language = api_key, model, language

    def details(self) -> dict[str, str]:
        return {"model": self._model, "language": self._language}

    def stt(self) -> STTService:
        return ElevenLabsRealtimeSTTService(
            api_key=self._api_key,
            sample_rate=IN_SAMPLE_RATE,
            commit_strategy=CommitStrategy.MANUAL,
            settings=ElevenLabsRealtimeSTTService.Settings(model=self._model, language=Language(self._language)),
        )


class ElevenLabsDialogueTTS(EagerSentenceFlush, ElevenLabsDialogueTTSService):
    """v4 Turbo, speaking a complete sentence without waiting for the rest of the stream."""


class ElevenLabsSynthesizer(PipecatSynthesizer):
    brand = "elevenlabs"

    def __init__(self, *, api_key: str, model: str, voice_id: str, name: str) -> None:
        self.name = name
        self._api_key, self._model, self._voice_id = api_key, model, voice_id

    def details(self) -> dict[str, str]:
        return {"model": self._model, "voice": self._voice_id}

    def tts(self) -> TTSService:
        return ElevenLabsDialogueTTS(
            api_key=self._api_key,
            settings=ElevenLabsDialogueTTSService.Settings(voice=self._voice_id, model=self._model),
        )
