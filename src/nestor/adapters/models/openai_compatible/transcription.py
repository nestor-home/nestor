"""TranscriptionModel over any OpenAI-compatible `/audio/transcriptions` endpoint: OpenAI, Groq, Mistral (Voxtral),
DeepInfra, a local speaches or whisper.cpp server.

Recordings (a voice message) go to the endpoint as they are. The voice of satellites runs Pipecat's segmented
service against the same endpoint: the pipeline's voice activity detection cuts each turn, and the whole turn is
transcribed at once. No realtime stream: the first words wait for the end of the turn."""

from typing import TYPE_CHECKING

from pydantic import Field, PositiveFloat

from nestor.adapters.common.http import HttpApi
from nestor.adapters.models.common import EndpointSettings, brand
from nestor.adapters.models.pipecat import SAMPLE_RATE, PipecatTranscription
from nestor.core import ProviderError
from nestor.modules.channels import TranscriptionModel
from nestor.runtime.plugins import Family, Plugin, Services

if TYPE_CHECKING:
    from pipecat.services.stt_service import STTService


class OpenAICompatibleTranscription(PipecatTranscription):
    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        language: str,
        timeout_s: float = 60.0,
        provider: str = "openai-compatible-transcription",
    ) -> None:
        self._base_url, self._api_key, self._model, self._language = base_url.rstrip("/"), api_key, model, language
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._api = HttpApi(provider, self._base_url, headers=headers, secret=api_key, timeout_s=timeout_s)
        self._provider = provider
        self.brand = brand(base_url)

    def details(self) -> dict[str, str]:
        return {"model": self._model, "language": self._language}

    async def close(self) -> None:
        await self._api.aclose()

    async def transcribe(self, audio: bytes, media_type: str) -> str:
        response = await self._api.request(
            "POST",
            "/audio/transcriptions",
            data={"model": self._model, "language": self._language, "response_format": "json"},
            files={"file": (_file_name(media_type), audio, media_type)},
        )
        try:
            text = response.json().get("text")
        except (ValueError, AttributeError):
            raise ProviderError(self._provider, "transcription: the answer is not JSON", transient=True) from None
        return text.strip() if isinstance(text, str) else ""

    def stt(self) -> "STTService":
        from pipecat.services.openai.stt import OpenAISTTService
        from pipecat.transcriptions.language import Language

        return OpenAISTTService(
            api_key=self._api_key or "none",  # a local server asks for none, the SDK for one
            base_url=self._base_url,
            sample_rate=SAMPLE_RATE,
            settings=OpenAISTTService.Settings(model=self._model, language=Language(self._language)),
        )


def _file_name(media_type: str) -> str:
    """A name whose extension tells the server the format, as some read it rather than the type."""
    base = media_type.split(";")[0].strip().lower()
    extension = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav", "audio/webm": "webm"}
    return f"recording.{extension.get(base, base.rpartition('/')[2] or 'bin')}"


class OpenAICompatibleTranscriptionSettings(EndpointSettings):
    model: str  # whisper-1, gpt-4o-transcribe, whisper-large-v3-turbo (Groq), voxtral-mini-latest (Mistral)…
    language: str | None = Field(default=None, min_length=2)  # what people speak, ISO 639-1; the household's
    timeout_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})


def build(
    settings: OpenAICompatibleTranscriptionSettings, name: str, services: Services
) -> OpenAICompatibleTranscription:
    return OpenAICompatibleTranscription(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        language=settings.language or services.locale.split("-")[0].lower(),
        timeout_s=settings.timeout_s,
        provider=name,
    )


plugin = Plugin(
    Family.MODEL,
    "openai-compatible",
    OpenAICompatibleTranscriptionSettings,
    build,
    requires="nestor-home[voice]",
    serves=TranscriptionModel,
)
