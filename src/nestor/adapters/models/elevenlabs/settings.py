"""What configures ElevenLabs' transcription and speech models, and how they are built."""

from pydantic import Field

from nestor.adapters.models.elevenlabs.speech import ElevenLabsSpeech
from nestor.adapters.models.elevenlabs.transcription import ElevenLabsTranscription
from nestor.runtime.plugins import AdapterSettings, RequiredSecret, Services


class ElevenLabsTranscriptionSettings(AdapterSettings):
    api_key: RequiredSecret
    model: str = "scribe_v2_realtime"  # the voice's, live
    file_model: str = "scribe_v2"  # recordings' (a voice message)
    language: str = Field(default="en", min_length=2)  # what people speak, e.g. fr


def build_transcription(
    settings: ElevenLabsTranscriptionSettings, name: str, services: Services
) -> ElevenLabsTranscription:
    return ElevenLabsTranscription(
        api_key=settings.api_key.get_secret_value(),
        model=settings.model,
        file_model=settings.file_model,
        language=settings.language,
        name=name,
    )


class ElevenLabsSpeechSettings(AdapterSettings):
    api_key: RequiredSecret
    voice_id: str = Field(min_length=1)  # a voice of the account's library
    model: str = "eleven_v4_turbo"


def build_speech(settings: ElevenLabsSpeechSettings, name: str, services: Services) -> ElevenLabsSpeech:
    return ElevenLabsSpeech(
        api_key=settings.api_key.get_secret_value(), model=settings.model, voice_id=settings.voice_id, name=name
    )
