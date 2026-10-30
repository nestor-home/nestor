"""Configuration of the voice channel, as a Nestor adapter plugin."""

from pathlib import Path

from pydantic import Field

from nestor.adapters.channels.voice.channel import VoiceChannel
from nestor.adapters.channels.voice.providers import ElevenLabsSettings, ElevenLabsSpeech
from nestor.adapters.channels.voice.session import DEFAULT_STT_PHRASE, SessionSettings
from nestor.core import Component
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services


class VoiceSettings(AdapterSettings):
    room: str = Field(min_length=1)  # the conversation: `<channel>:<room>`, kept across reconnections
    speech: ElevenLabsSettings
    style: str = ""  # how the assistant writes for this voice (e.g. the expression tags it performs)
    host: str = "localhost"
    port: int | None = Field(default=7860, ge=0, le=65535)  # development signalling server; `None` disables it
    stt_fallback: str = DEFAULT_STT_PHRASE  # said when the transcription fails
    fallback_clips: Path | None = None  # `stt.wav` and `tts.wav`, played when the synthesis is down
    quiet_s: float = Field(default=0.5, ge=0)  # silence before an unprompted message is spoken
    send_timeout_s: float = Field(default=30.0, gt=0)


def build(settings: VoiceSettings, name: str, services: Services) -> Component:
    return VoiceChannel(
        name,
        room=settings.room,
        speech=ElevenLabsSpeech(settings.speech),
        style=settings.style,
        host=settings.host,
        port=settings.port,
        session=SessionSettings(stt_phrase=settings.stt_fallback, quiet_s=settings.quiet_s),
        clips=settings.fallback_clips,
        send_timeout_s=settings.send_timeout_s,
    )


plugin = Plugin(Family.CHANNEL, "voice", VoiceSettings, build)
