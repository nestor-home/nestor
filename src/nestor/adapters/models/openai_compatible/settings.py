"""What configures each type of model an OpenAI-compatible API serves, and how it is built."""

from typing import Any

from pydantic import Field, PositiveFloat, PositiveInt

from nestor.adapters.models.common import EndpointSettings
from nestor.adapters.models.openai_compatible.embedding import OpenAICompatibleEmbedding
from nestor.adapters.models.openai_compatible.image import OpenAICompatibleImage
from nestor.adapters.models.openai_compatible.language import OpenAICompatibleLanguage
from nestor.adapters.models.openai_compatible.speech import OpenAICompatibleSpeech
from nestor.adapters.models.openai_compatible.transcription import OpenAICompatibleTranscription
from nestor.adapters.models.openai_compatible.wire import ImageEndpoint
from nestor.runtime.plugins import Services


class OpenAICompatibleLanguageSettings(EndpointSettings):
    """Configuration of an OpenAI-compatible chat model."""

    model: str
    extra_body: dict[str, Any] = Field(default_factory=dict)
    connect_timeout_s: PositiveFloat = 5.0
    read_timeout_s: PositiveFloat = 30.0
    # mark the instructions' stable layers for the prompt cache; by default for OpenRouter and Anthropic
    cache_control: bool | None = Field(default=None, json_schema_extra={"advanced": True})
    vision: bool = False  # it looks at images (a photo sent in a message); without, it is told it cannot see them


def build_language(
    settings: OpenAICompatibleLanguageSettings, name: str, services: Services
) -> OpenAICompatibleLanguage:
    return OpenAICompatibleLanguage(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        extra_body=settings.extra_body,
        connect_timeout_s=settings.connect_timeout_s,
        read_timeout_s=settings.read_timeout_s,
        provider=name,
        cache_control=settings.cache_control,
        vision=settings.vision,
    )


class OpenAICompatibleEmbeddingSettings(EndpointSettings):
    """An embedding model's profile."""

    model: str
    dimensions: PositiveInt  # of the vectors it returns, or asks for with `send_dimensions`
    send_dimensions: bool = False  # ask the model for `dimensions` (Matryoshka models shorten their vectors)
    query_prefix: str = ""  # put before a question, when the model expects it ("query: ")
    document_prefix: str = ""  # put before a document ("passage: ")
    batch_size: PositiveInt = Field(default=64, json_schema_extra={"advanced": True})
    extra_body: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})
    connect_timeout_s: PositiveFloat = Field(default=5.0, json_schema_extra={"advanced": True})
    read_timeout_s: PositiveFloat = Field(default=30.0, json_schema_extra={"advanced": True})


def build_embedding(
    settings: OpenAICompatibleEmbeddingSettings, name: str, services: Services
) -> OpenAICompatibleEmbedding:
    return OpenAICompatibleEmbedding(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        dimensions=settings.dimensions,
        send_dimensions=settings.send_dimensions,
        query_prefix=settings.query_prefix,
        document_prefix=settings.document_prefix,
        batch_size=settings.batch_size,
        extra_body=settings.extra_body,
        connect_timeout_s=settings.connect_timeout_s,
        read_timeout_s=settings.read_timeout_s,
        provider=name,
    )


class OpenAICompatibleImageSettings(EndpointSettings):
    """An image model's profile."""

    model: str
    endpoint: ImageEndpoint = ImageEndpoint.IMAGES  # `chat` for OpenRouter's image models
    size: str | None = None  # `1024x1024`, `1536x1024`…, as the model takes it; its own default otherwise
    extra_body: dict[str, Any] = Field(default_factory=dict, json_schema_extra={"advanced": True})
    timeout_s: PositiveFloat = Field(default=120.0, json_schema_extra={"advanced": True})


def build_image(settings: OpenAICompatibleImageSettings, name: str, services: Services) -> OpenAICompatibleImage:
    return OpenAICompatibleImage(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        endpoint=settings.endpoint,
        size=settings.size,
        extra_body=settings.extra_body,
        timeout_s=settings.timeout_s,
        provider=name,
    )


class OpenAICompatibleTranscriptionSettings(EndpointSettings):
    model: str  # whisper-1, gpt-4o-transcribe, whisper-large-v3-turbo (Groq), voxtral-mini-latest (Mistral)…
    language: str | None = Field(default=None, min_length=2)  # what people speak, ISO 639-1; the household's
    timeout_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})


def build_transcription(
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


class OpenAICompatibleSpeechSettings(EndpointSettings):
    model: str  # gpt-4o-mini-tts, tts-1, kokoro…
    voice: str = Field(min_length=1)  # alloy, nova (OpenAI), ff_siwis (Kokoro, French)…
    timeout_s: PositiveFloat = Field(default=60.0, json_schema_extra={"advanced": True})


def build_speech(settings: OpenAICompatibleSpeechSettings, name: str, services: Services) -> OpenAICompatibleSpeech:
    return OpenAICompatibleSpeech(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        model=settings.model,
        voice=settings.voice,
        timeout_s=settings.timeout_s,
        provider=name,
    )
