"""Configuration of the satellites channel, and how it is built. Discovering it imports no Pipecat: only building a
channel with a `voice` section does, and without the `voice` extra that fails with the requirement to install."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from nestor.adapters.models.pipecat import PipecatSpeech, PipecatTranscription
from nestor.core import Component, ContractError
from nestor.core.i18n import Message
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.config import SPEECH_MODEL, TRANSCRIPTION_MODEL
from nestor.runtime.plugins import ChannelSettings, Services

VOICE_REQUIREMENT = "nestor-home[voice]"
PORT = 8471  # the admin's default plus one; clear of Gradio (7860), llama.cpp (8080) and other usual ports


class VoiceSettings(BaseModel):
    """How satellites allowed audio are heard and answered aloud (needs the `voice` extra)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transcription: str = Field(json_schema_extra=TRANSCRIPTION_MODEL)  # a model of `models` that hears people
    speech: str = Field(json_schema_extra=SPEECH_MODEL)  # a model of `models` that gives the assistant its voice
    style: str = ""  # how the assistant writes for this voice (e.g. the expression tags it performs)
    stt_fallback: str | None = None  # said when the transcription fails; default: `voice-stt-down`
    fallback_clips: Path | None = None  # `stt.wav` and `tts.wav`, played when the synthesis is down
    quiet_s: float = Field(default=0.5, ge=0)  # silence before an unprompted message is spoken


class SatellitesSettings(ChannelSettings):
    host: str = "localhost"
    port: int = Field(default=PORT, ge=0, le=65535)
    # How satellites reach this server ("http://nestor.local:8471"), for pairing URIs; by default its
    # host and port, or the admin's host name when it listens on every interface.
    public_url: str | None = Field(default=None, pattern=r"^https?://")
    voice: VoiceSettings | None = None  # without it, satellites talk in writing only
    send_timeout_s: float = Field(default=30.0, gt=0)  # how long an unprompted message waits to be said


def build(settings: SatellitesSettings, name: str, services: Services) -> Component:
    from nestor.adapters.channels.satellites.channel import SatellitesChannel

    voice = None
    if settings.voice is not None:
        from nestor.adapters.channels.satellites.voice.audio import SatelliteVoice
        from nestor.adapters.channels.satellites.voice.resilience import load_clips
        from nestor.adapters.channels.satellites.voice.session import SessionSettings
        from nestor.adapters.channels.satellites.voice.speech import ModelSpeech

        said = settings.voice
        transcription = services.model(said.transcription, TranscriptionModel, ("voice", "transcription"))
        speech = services.model(said.speech, SpeechModel, ("voice", "speech"))
        if not isinstance(transcription, PipecatTranscription) or not isinstance(speech, PipecatSpeech):
            raise ContractError(
                f"{name}: the voice runs Pipecat services; {said.transcription} or {said.speech} has none"
            )
        voice = SatelliteVoice(
            name,
            speech=ModelSpeech(transcription, speech),
            settings=SessionSettings(
                stt_phrase=said.stt_fallback
                if said.stt_fallback is not None
                else services.localizer.format(Message.of("voice-stt-down"), services.locale),
                quiet_s=said.quiet_s,
                clips=load_clips(said.fallback_clips),
            ),
        )
    return SatellitesChannel(
        name,
        host=settings.host,
        port=settings.port,
        public_url=settings.public_url,
        voice=voice,
        style=settings.voice.style if settings.voice else "",
        send_timeout_s=settings.send_timeout_s,
        conversation_ends_after_s=settings.conversation_ends_after_s,
    )
