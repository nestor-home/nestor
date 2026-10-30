"""Speech providers: what transcribes the user and what gives the assistant its voice.

Retained on measurements (voice proof of concept): ElevenLabs Scribe v2 Realtime with a manual
commit (the local VAD and Smart Turn decide when the turn ends), and ElevenLabs v4 Turbo, which is
only served over WebSocket by the Text-to-Dialogue endpoint (the text-to-speech WebSocket refuses
it). Another provider is another `Speech` implementation.
"""

from abc import ABC, abstractmethod
from typing import Literal

from pipecat.services.elevenlabs.dialogue.tts import ElevenLabsDialogueTTSService
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from pydantic import BaseModel, ConfigDict, SecretStr

from nestor.adapters.channels.voice.eager import EagerSentenceFlush

IN_SAMPLE_RATE = 16000


class Speech(ABC):
    """Builds fresh speech services for each voice session."""

    @abstractmethod
    def stt(self) -> STTService: ...

    @abstractmethod
    def tts(self) -> TTSService:
        """A synthesis that should mix in `EagerSentenceFlush`, or the first sentence waits for the next."""


class ElevenLabsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["elevenlabs"] = "elevenlabs"
    api_key: SecretStr
    voice_id: str
    language: str = "fr"  # transcription language; the synthesis detects it (checked with expression tags)
    stt_model: str = "scribe_v2_realtime"
    tts_model: str = "eleven_v4_turbo"


class ElevenLabsDialogueTTS(EagerSentenceFlush, ElevenLabsDialogueTTSService):
    """v4 Turbo, speaking a complete sentence without waiting for the rest of the stream."""


class ElevenLabsSpeech(Speech):
    def __init__(self, settings: ElevenLabsSettings) -> None:
        self._settings = settings

    def stt(self) -> STTService:
        return ElevenLabsRealtimeSTTService(
            api_key=self._settings.api_key.get_secret_value(),
            sample_rate=IN_SAMPLE_RATE,
            commit_strategy=CommitStrategy.MANUAL,
            settings=ElevenLabsRealtimeSTTService.Settings(
                model=self._settings.stt_model, language=Language(self._settings.language)
            ),
        )

    def tts(self) -> TTSService:
        return ElevenLabsDialogueTTS(
            api_key=self._settings.api_key.get_secret_value(),
            settings=ElevenLabsDialogueTTSService.Settings(
                voice=self._settings.voice_id, model=self._settings.tts_model
            ),
        )
