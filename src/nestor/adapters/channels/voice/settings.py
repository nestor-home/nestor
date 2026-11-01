"""Configuration of the voice channel. Pydantic only: plugin discovery and configuration forms read it
without the `voice` extra, which the channel itself needs once it is built."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nestor.runtime.plugins import ChannelSettings, RequiredSecret

PORT = 8471  # the admin's default plus one; clear of Gradio (7860), llama.cpp (8080) and other usual ports


class ElevenLabsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["elevenlabs"] = "elevenlabs"
    api_key: RequiredSecret
    voice_id: str
    language: str = "en"  # transcription language; the synthesis detects it (checked with expression tags)
    stt_model: str = "scribe_v2_realtime"
    tts_model: str = "eleven_v4_turbo"


class VoiceSettings(ChannelSettings):
    room: str = Field(min_length=1)  # the conversation: `<channel>:<room>`, kept across reconnections
    speech: ElevenLabsSettings
    style: str = ""  # how the assistant writes for this voice (e.g. the expression tags it performs)
    host: str = "localhost"
    port: int | None = Field(default=PORT, ge=0, le=65535)  # satellites and browser; `None` disables the server
    # The Pipecat browser client at /client, with no pairing: anyone who reaches the port talks to the
    # assistant. Development on a trusted LAN only; turn it off once real satellites are paired.
    allow_unpaired_browser: bool = True
    # How satellites reach this server ("http://nestor.local:8471"), for pairing URIs; by default its
    # host and port, or the admin's host name when it listens on every interface.
    public_url: str | None = Field(default=None, pattern=r"^https?://")
    stt_fallback: str | None = None  # said when the transcription fails; default: `voice-stt-down`
    fallback_clips: Path | None = None  # `stt.wav` and `tts.wav`, played when the synthesis is down
    quiet_s: float = Field(default=0.5, ge=0)  # silence before an unprompted message is spoken
    send_timeout_s: float = Field(default=30.0, gt=0)
