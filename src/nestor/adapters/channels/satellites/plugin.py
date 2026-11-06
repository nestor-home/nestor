"""The satellites channel as a Nestor adapter plugin. Discovering it imports no Pipecat: only building
a channel with a `voice` section does, and without the `voice` extra that fails with the requirement
to install."""

from nestor.adapters.channels.satellites.settings import SatellitesSettings
from nestor.adapters.models.pipecat import PipecatSpeech, PipecatTranscription
from nestor.core import Component, ContractError
from nestor.core.i18n import Message
from nestor.modules.channels import SpeechModel, TranscriptionModel
from nestor.runtime.plugins import Family, Plugin, Services

VOICE_REQUIREMENT = "nestor-home[voice]"


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


plugin = Plugin(Family.CHANNEL, "satellites", SatellitesSettings, build, requires=VOICE_REQUIREMENT)  # for `voice`
