"""ElevenLabs as two models of `models`: `elevenlabs-transcription` (Scribe, realtime) and `elevenlabs-speech`
(its voices). Discovering them imports no Pipecat: building one does, and needs the `voice` extra."""

from pydantic import Field

from nestor.core import Component
from nestor.runtime.plugins import AdapterSettings, Family, ModelType, Plugin, RequiredSecret, Services

VOICE_REQUIREMENT = "nestor-home[voice]"


class ElevenLabsTranscriptionSettings(AdapterSettings):
    api_key: RequiredSecret
    model: str = "scribe_v2_realtime"
    language: str = Field(default="en", min_length=2)  # what people speak, e.g. fr


class ElevenLabsSpeechSettings(AdapterSettings):
    api_key: RequiredSecret
    voice_id: str = Field(min_length=1)  # a voice of the account's library
    model: str = "eleven_v4_turbo"


def _transcriber(settings: ElevenLabsTranscriptionSettings, name: str, services: Services) -> Component:
    from nestor.adapters.channels.satellites.voice.providers import ElevenLabsTranscriber

    return ElevenLabsTranscriber(
        api_key=settings.api_key.get_secret_value(), model=settings.model, language=settings.language, name=name
    )


def _synthesizer(settings: ElevenLabsSpeechSettings, name: str, services: Services) -> Component:
    from nestor.adapters.channels.satellites.voice.providers import ElevenLabsSynthesizer

    return ElevenLabsSynthesizer(
        api_key=settings.api_key.get_secret_value(), model=settings.model, voice_id=settings.voice_id, name=name
    )


transcription = Plugin(
    Family.MODEL,
    "elevenlabs-transcription",
    ElevenLabsTranscriptionSettings,
    _transcriber,
    requires=VOICE_REQUIREMENT,
    model_type=ModelType.TRANSCRIPTION,
)
speech = Plugin(
    Family.MODEL,
    "elevenlabs-speech",
    ElevenLabsSpeechSettings,
    _synthesizer,
    requires=VOICE_REQUIREMENT,
    model_type=ModelType.SPEECH,
)
