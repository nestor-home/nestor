"""Configuration of the voice channel, as a Nestor adapter plugin."""

from pathlib import Path

from pydantic import Field

from nestor.adapters.channels.voice.channel import VoiceChannel
from nestor.adapters.channels.voice.providers import ElevenLabsSettings, ElevenLabsSpeech
from nestor.adapters.channels.voice.session import SessionSettings
from nestor.core import Component
from nestor.core.i18n import Message
from nestor.runtime.plugins import AdapterSettings, Family, Plugin, Services


class VoiceSettings(AdapterSettings):
    room: str = Field(min_length=1)  # the conversation: `<channel>:<room>`, kept across reconnections
    speech: ElevenLabsSettings
    style: str = ""  # how the assistant writes for this voice (e.g. the expression tags it performs)
    host: str = "localhost"
    port: int | None = Field(default=7860, ge=0, le=65535)  # satellites and browser; `None` disables the server
    # The Pipecat browser client at /client, with no pairing: anyone who reaches the port talks to the
    # assistant. Development on a trusted LAN only; turn it off once real satellites are paired.
    allow_unpaired_browser: bool = True
    # How satellites reach this server ("http://nestor.local:7860"), for pairing URIs; by default its
    # host and port, or the admin's host name when it listens on every interface.
    public_url: str | None = Field(default=None, pattern=r"^https?://")
    stt_fallback: str | None = None  # said when the transcription fails; default: `voice-stt-down`
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
        allow_unpaired_browser=settings.allow_unpaired_browser,
        public_url=settings.public_url,
        session=SessionSettings(
            stt_phrase=settings.stt_fallback
            if settings.stt_fallback is not None
            else services.localizer.format(Message.of("voice-stt-down"), services.locale),
            quiet_s=settings.quiet_s,
        ),
        clips=settings.fallback_clips,
        send_timeout_s=settings.send_timeout_s,
    )


plugin = Plugin(Family.CHANNEL, "voice", VoiceSettings, build)
