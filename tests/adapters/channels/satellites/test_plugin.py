from pathlib import Path

import pytest

from nestor.adapters.channels.satellites import plugin
from nestor.adapters.channels.satellites.channel import SatellitesChannel
from nestor.adapters.models.elevenlabs import speech, transcription
from nestor.core import ContractError, Model
from nestor.core.i18n import Locale
from nestor.modules.channels import Address, Medium
from nestor.runtime.plugins import Services
from nestor.testing.i18n import EchoLocalizer

SPEECH = {"api_key": "xi-test", "voice_id": "GPAQQPp9dazaB2bl4zg9"}
VOICE = {"transcription": "ears", "speech": "mouth"}


def services(tmp_path: Path) -> Services:
    bare = Services(tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"))
    models = {
        "ears": transcription.plugin.create({"api_key": "xi-test", "language": "fr"}, "ears", bare),
        "mouth": speech.plugin.create(SPEECH, "mouth", bare),
    }

    def model(key: str, wanted: type[Model], path: tuple[str | int, ...]) -> Model:
        return models[key]

    return Services(tmp_path, localizer=EchoLocalizer(), locale=Locale("fr-FR"), models=model)


def test_without_a_voice_satellites_only_write(tmp_path: Path) -> None:
    channel = plugin.create({}, "devices", services(tmp_path))
    assert isinstance(channel, SatellitesChannel)
    assert (channel.channel_id, channel.media, channel.style) == ("devices", {Medium.WRITTEN}, "")
    assert not channel.spoken and channel.details() == {}
    assert not channel.reachable(Address("devices", "salon"), Medium.WRITTEN), "nobody is connected yet"


def test_with_a_voice_satellites_also_speak_in_its_style(tmp_path: Path) -> None:
    raw = {"voice": {**VOICE, "style": "Use [laughs] sparingly."}}
    channel = plugin.create(raw, "satellites", services(tmp_path))
    assert isinstance(channel, SatellitesChannel)
    assert (channel.media, channel.style) == ({Medium.WRITTEN, Medium.SPOKEN}, "Use [laughs] sparingly.")
    assert not channel.reachable(Address("satellites", "salon"), Medium.SPOKEN), "nobody is connected yet"


@pytest.mark.parametrize(
    "raw",
    [
        {"voice": {"speech": "mouth"}},  # nothing to hear with
        {"voice": {**VOICE, "microphone": "usb"}},  # unknown key
        {"room": "salon"},  # rooms belong to devices
        {"port": 70000},
    ],
)
def test_an_incomplete_or_unknown_configuration_is_rejected(raw: dict, tmp_path: Path) -> None:
    with pytest.raises(ContractError):
        plugin.create(raw, "satellites", services(tmp_path))


@pytest.mark.parametrize(("configured", "said"), [({}, "voice-stt-down"), ({"stt_fallback": "Pardon ?"}, "Pardon ?")])
def test_the_transcription_fallback_is_in_the_households_language_unless_configured(
    tmp_path: Path, configured: dict[str, str], said: str
) -> None:
    channel = plugin.create({"voice": {**VOICE, **configured}}, "satellites", services(tmp_path))
    assert isinstance(channel, SatellitesChannel) and channel._voice is not None
    assert channel._voice._settings.stt_phrase == said


@pytest.mark.parametrize(("configured", "seconds"), [({}, None), ({"conversation_ends_after_s": 120}, 120.0)])
def test_each_turn_s_medium_decides_how_long_a_conversation_lasts_unless_configured(
    tmp_path: Path, configured: dict[str, int], seconds: float
) -> None:
    channel = plugin.create(configured, "satellites", services(tmp_path))
    assert isinstance(channel, SatellitesChannel) and channel.conversation_ends_after_s == seconds
