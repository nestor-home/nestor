"""ElevenLabs Scribe as a transcription model, realtime over WebSocket.

Retained on measurements (voice proof of concept): Scribe v2 Realtime with a manual commit, so that the local voice
activity detection and Smart Turn decide when a turn ends.
"""

from typing import TYPE_CHECKING

from pydantic import Field

from nestor.adapters.models.pipecat import SAMPLE_RATE, PipecatTranscription
from nestor.modules.channels import TranscriptionModel
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, RequiredSecret, Services

if TYPE_CHECKING:
    from pipecat.services.stt_service import STTService


class ElevenLabsTranscription(PipecatTranscription):
    brand = "elevenlabs"

    def __init__(self, *, api_key: str, model: str, language: str, name: str) -> None:
        self.name = name
        self._api_key, self._model, self._language = api_key, model, language

    def details(self) -> dict[str, str]:
        return {"model": self._model, "language": self._language}

    def stt(self) -> "STTService":
        from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
        from pipecat.transcriptions.language import Language

        return ElevenLabsRealtimeSTTService(
            api_key=self._api_key,
            sample_rate=SAMPLE_RATE,
            commit_strategy=CommitStrategy.MANUAL,
            settings=ElevenLabsRealtimeSTTService.Settings(model=self._model, language=Language(self._language)),
        )


class ElevenLabsTranscriptionSettings(AdapterSettings):
    api_key: RequiredSecret
    model: str = "scribe_v2_realtime"
    language: str = Field(default="en", min_length=2)  # what people speak, e.g. fr


def build(settings: ElevenLabsTranscriptionSettings, name: str, services: Services) -> ElevenLabsTranscription:
    return ElevenLabsTranscription(
        api_key=settings.api_key.get_secret_value(), model=settings.model, language=settings.language, name=name
    )


plugin = Plugin(
    Family.MODEL,
    "elevenlabs",
    ElevenLabsTranscriptionSettings,
    build,
    requires="nestor-home[voice]",
    serves=TranscriptionModel,
)
