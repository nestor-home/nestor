"""ElevenLabs Scribe as a transcription model: realtime over WebSocket for the voice, over HTTP for recordings.

Retained on measurements (voice proof of concept): Scribe v2 Realtime with a manual commit, so that the local voice
activity detection and Smart Turn decide when a turn ends. Recordings (a voice message) go to the speech-to-text
endpoint, whose models are not the realtime ones (`file_model`).
"""

from typing import TYPE_CHECKING

import httpx
from pydantic import Field

from nestor.adapters.models.elevenlabs.api import ElevenLabsApi
from nestor.adapters.models.pipecat import SAMPLE_RATE, PipecatTranscription
from nestor.modules.channels import TranscriptionModel
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, RequiredSecret, Services

if TYPE_CHECKING:
    from pipecat.services.stt_service import STTService


class ElevenLabsTranscription(PipecatTranscription):
    brand = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        language: str,
        name: str,
        file_model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self._api_key, self._model, self._language, self._file_model = api_key, model, language, file_model
        self._api = ElevenLabsApi(api_key, transport=transport)

    async def close(self) -> None:
        await self._api.aclose()

    def details(self) -> dict[str, str]:
        return {"model": self._model, "file_model": self._file_model, "language": self._language}

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        response = await self._api.post(
            "/v1/speech-to-text",
            data={"model_id": self._file_model, "language_code": self._language, "tag_audio_events": "false"},
            files={"file": ("recording", audio, media_type)},
        )
        text = response.json().get("text")
        return text.strip() if isinstance(text, str) else ""

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
    model: str = "scribe_v2_realtime"  # the voice's, live
    file_model: str = "scribe_v2"  # recordings' (a voice message)
    language: str = Field(default="en", min_length=2)  # what people speak, e.g. fr


def build(settings: ElevenLabsTranscriptionSettings, name: str, services: Services) -> ElevenLabsTranscription:
    return ElevenLabsTranscription(
        api_key=settings.api_key.get_secret_value(),
        model=settings.model,
        file_model=settings.file_model,
        language=settings.language,
        name=name,
    )


plugin = Plugin(
    Family.MODEL,
    "elevenlabs",
    ElevenLabsTranscriptionSettings,
    build,
    requires="nestor-home[voice]",
    serves=TranscriptionModel,
)
