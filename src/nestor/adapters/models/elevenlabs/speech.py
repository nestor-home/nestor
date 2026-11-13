"""ElevenLabs voices as a speech model.

Retained on measurements (voice proof of concept): v4 Turbo, which only the Text-to-Dialogue endpoint serves over
WebSocket (the text-to-speech WebSocket refuses it). Recordings (a voice message) come from the text-to-speech HTTP
endpoint, as OGG/Opus.
"""

from typing import TYPE_CHECKING

import httpx

from nestor.adapters.models.elevenlabs.api import elevenlabs_api
from nestor.adapters.models.pipecat import PipecatSpeech

if TYPE_CHECKING:
    from pipecat.services.tts_service import TTSService


class ElevenLabsSpeech(PipecatSpeech):
    brand = "elevenlabs"

    def __init__(
        self, *, api_key: str, model: str, voice_id: str, name: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.name = name
        self._api_key, self._model, self._voice_id = api_key, model, voice_id
        self._api = elevenlabs_api(api_key, transport=transport)

    async def synthesize(self, text: str) -> bytes:
        response = await self._api.request(
            "POST",
            f"/v1/text-to-speech/{self._voice_id}",
            params={"output_format": "opus_48000_64"},
            json={"model_id": self._model, "text": text},  # the model in the body, or it is ignored
        )
        return response.content

    async def close(self) -> None:
        await self._api.aclose()

    def details(self) -> dict[str, str]:
        return {"model": self._model, "voice": self._voice_id}

    def tts(self) -> "TTSService":
        from pipecat.services.elevenlabs.dialogue.tts import ElevenLabsDialogueTTSService

        from nestor.adapters.models.pipecat.eager import EagerSentenceFlush

        class EagerDialogue(EagerSentenceFlush, ElevenLabsDialogueTTSService):
            """Speaks a complete sentence without waiting for the rest of the stream."""

        return EagerDialogue(
            api_key=self._api_key,
            settings=ElevenLabsDialogueTTSService.Settings(voice=self._voice_id, model=self._model),
        )
