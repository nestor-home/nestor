"""SpeechModel over any OpenAI-compatible `/audio/speech` endpoint: OpenAI, a local Kokoro-FastAPI or speaches server.

Recordings (a voice message) come back as OGG/Opus (`response_format: opus`). The voice of satellites streams PCM
through Pipecat's OpenAI service against the same endpoint."""

from typing import TYPE_CHECKING

from pydantic import Field, PositiveFloat

from nestor.adapters.common.http import HttpApi
from nestor.adapters.models.common import EndpointSettings, brand
from nestor.adapters.models.pipecat import PipecatSpeech
from nestor.modules.channels import SpeechModel
from nestor.runtime.plugins import Family, Plugin, Services

if TYPE_CHECKING:
    from pipecat.services.tts_service import TTSService


class OpenAICompatibleSpeech(PipecatSpeech):
    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        voice: str,
        timeout_s: float = 60.0,
        provider: str = "openai-compatible-speech",
    ) -> None:
        self._base_url, self._api_key, self._model, self._voice = base_url.rstrip("/"), api_key, model, voice
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._api = HttpApi(provider, self._base_url, headers=headers, secret=api_key, timeout_s=timeout_s)
        self.brand = brand(base_url)

    def details(self) -> dict[str, str]:
        return {"model": self._model, "voice": self._voice}

    async def close(self) -> None:
        await self._api.aclose()

    async def synthesize(self, text: str) -> bytes:
        body = {"model": self._model, "input": text, "voice": self._voice, "response_format": "opus"}
        return (await self._api.request("POST", "/audio/speech", json=body)).content

    def tts(self) -> "TTSService":
        from pipecat.services.openai.tts import OpenAITTSService

        from nestor.adapters.models.pipecat.eager import EagerSentenceFlush

        class EagerOpenAI(EagerSentenceFlush, OpenAITTSService):
            """Speaks a complete sentence without waiting for the rest of the stream."""

        return EagerOpenAI(
            api_key=self._api_key or "none",  # a local server asks for none, the SDK for one
            base_url=self._base_url,
            settings=OpenAITTSService.Settings(model=self._model, voice=self._voice),
        )


class OpenAICompatibleSpeechSettings(EndpointSettings):
    model: str  # gpt-4o-mini-tts, tts-1, kokoro…
    voice: str = Field(min_length=1)  # alloy, nova (OpenAI), ff_siwis (Kokoro, French)…
    timeout_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})


def build(settings: OpenAICompatibleSpeechSettings, name: str, services: Services) -> OpenAICompatibleSpeech:
    return OpenAICompatibleSpeech(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        voice=settings.voice,
        timeout_s=settings.timeout_s,
        provider=name,
    )


plugin = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleSpeechSettings,
    build,
    requires="nestor-home[voice]",
    serves=SpeechModel,
)
