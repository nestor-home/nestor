from pathlib import Path

import pytest

from nestor.adapters.channels.voice import VoiceChannel, plugin
from nestor.adapters.channels.voice.eager import EagerSentenceFlush
from nestor.adapters.channels.voice.providers import ElevenLabsSettings, ElevenLabsSpeech
from nestor.core import ContractError
from nestor.modules.channels import Address, Medium
from nestor.runtime.plugins import Services

SPEECH = {"api_key": "xi-test", "voice_id": "GPAQQPp9dazaB2bl4zg9"}


def test_the_channel_is_named_after_its_instance_and_speaks_in_its_room(tmp_path: Path) -> None:
    channel = plugin.create(
        {"room": "salon", "speech": SPEECH, "style": "Use [laughs] sparingly."}, "voix", Services(tmp_path)
    )
    assert isinstance(channel, VoiceChannel)
    assert (channel.channel_id, channel.medium, channel.style) == ("voix", Medium.SPOKEN, "Use [laughs] sparingly.")
    assert not channel.reachable(Address("voix", "salon")), "nobody is connected yet"
    assert (channel.brand, channel.details()) == ("webrtc", {"speech": "elevenlabs"})


@pytest.mark.parametrize(
    "raw",
    [
        {"speech": SPEECH},  # no room
        {"room": "salon", "speech": {"voice_id": "v"}},  # no key
        {"room": "salon", "speech": SPEECH, "microphone": "usb"},  # unknown key
    ],
)
def test_an_incomplete_or_unknown_configuration_is_rejected(raw: dict, tmp_path: Path) -> None:
    with pytest.raises(ContractError):
        plugin.create(raw, "voice", Services(tmp_path))


def test_the_api_key_is_never_shown() -> None:
    assert "xi-test" not in repr(ElevenLabsSettings.model_validate(SPEECH))


def test_elevenlabs_speech_releases_a_complete_sentence_without_waiting_for_more_text() -> None:
    speech = ElevenLabsSpeech(ElevenLabsSettings.model_validate(SPEECH))
    assert isinstance(speech.tts(), EagerSentenceFlush)
    assert speech.stt() is not speech.stt(), "each session gets its own transcription"
