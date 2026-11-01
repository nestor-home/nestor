"""The voice channel as a Nestor adapter plugin. Discovering it imports no Pipecat: only building the
channel does, and without the `voice` extra that fails with the requirement to install."""

from nestor.adapters.channels.voice.settings import VoiceSettings
from nestor.core import Component
from nestor.core.i18n import Message
from nestor.runtime.plugins import Family, Plugin, Services

REQUIREMENT = "nestor-home[voice]"


def build(settings: VoiceSettings, name: str, services: Services) -> Component:
    from nestor.adapters.channels.voice.channel import VoiceChannel
    from nestor.adapters.channels.voice.providers import ElevenLabsSpeech
    from nestor.adapters.channels.voice.session import SessionSettings

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
        conversation_ends_after_s=settings.conversation_ends_after_s,
    )


plugin = Plugin(Family.CHANNEL, "voice", VoiceSettings, build, requires=REQUIREMENT)
