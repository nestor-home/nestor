"""Configuration of the satellites channel. Pydantic only: plugin discovery and configuration forms read
it without the `voice` extra, which only its `voice` section needs once the channel is built."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from nestor.runtime.config import SPEECH_MODEL, TRANSCRIPTION_MODEL
from nestor.runtime.plugins import ChannelSettings

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
