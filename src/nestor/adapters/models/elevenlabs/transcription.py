"""ElevenLabs Scribe as a transcription model: realtime over WebSocket for the voice, over HTTP for recordings.

Retained on measurements (voice proof of concept): Scribe v2 Realtime with a manual commit, so that the local voice
activity detection and Smart Turn decide when a turn ends. Recordings (a voice message) go to the speech-to-text
endpoint, whose models are not the realtime ones (`file_model`).
"""

from typing import TYPE_CHECKING

import httpx

from nestor.adapters.models.elevenlabs.api import elevenlabs_api
from nestor.adapters.models.pipecat import SAMPLE_RATE, PipecatTranscription
from nestor.core import ProviderError

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
        self._api = elevenlabs_api(api_key, transport=transport)

    async def close(self) -> None:
        await self._api.aclose()

    def details(self) -> dict[str, str]:
        return {"model": self._model, "file_model": self._file_model, "language": self._language}

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        response = await self._api.request(
            "POST",
            "/v1/speech-to-text",
            data={"model_id": self._file_model, "language_code": self._language, "tag_audio_events": "false"},
            files={"file": ("recording", audio, media_type)},
        )
        try:
            text = response.json().get("text")
        except ValueError:
            raise ProviderError("elevenlabs", "speech-to-text: the answer is not JSON", transient=True) from None
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
